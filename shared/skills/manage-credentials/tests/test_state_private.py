"""The agent's state file is published only into a folder and a file proved private (follow-up plan R15,
fix 1, and R16), and shutdown is a barrier (R16, rule 3); the POSIX proof is in test_state_private_posix.py.
Everything runs in real temporary folders, never the user's runtime folder; no real agent or
tray is started (an agent here listens on a pipe of its own, in-process)."""
from __future__ import annotations

import io
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from multiprocessing.connection import Client
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime as runtime  # noqa: E402
from vault_agent_runtime import NotPrivate  # noqa: E402

if sys.platform == "win32":
    from multiprocessing.connection import PipeConnection  # noqa: E402

    import vault_tray  # noqa: E402

TOKEN = "fictional-token-" + "c0de" * 12  # no real token; searched for in every file left behind
EVERYONE = "*S-1-1-0"  # a SID, so no account name in the system's language


def grant_everyone(path: Path) -> None:
    rights = "(OI)(CI)(R)" if path.is_dir() else "(R)"
    result = subprocess.run(["icacls", str(path), "/grant", f"{EVERYONE}:{rights}"], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


class TemporaryRuntime(unittest.TestCase):
    """A runtime folder inside a fresh temporary folder, as the real one sits inside the profile."""

    def setUp(self) -> None:
        self.parent = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.parent, ignore_errors=True)
        self.folder = self.parent / "vault-agent"
        self.folder.mkdir()
        patch = mock.patch.object(runtime, "runtime_base", lambda: self.folder)
        patch.start()
        self.addCleanup(patch.stop)

    def payload(self) -> dict:
        return {"pid": os.getpid(), "address": "fictional-address", "authkey": "ab" * 32, "token": TOKEN,
                "vault_path": "fictional.vault", "protocol": runtime.AGENT_PROTOCOL_VERSION}

    def assert_nothing_holds_the_token(self) -> None:
        self.assertFalse((self.folder / "agent-state.json").exists())
        self.assertEqual(list(self.folder.glob("agent-state*.tmp")), [])
        for path in self.folder.rglob("*"):
            if path.is_file():
                self.assertNotIn(TOKEN, path.read_text(encoding="utf-8", errors="ignore"), path.name)


@unittest.skipUnless(os.name == "nt", "Windows access lists")
class WindowsProofTest(TemporaryRuntime):
    def test_an_entry_for_everyone_on_a_folder_is_seen_and_removed(self) -> None:
        runtime.make_private(self.folder)
        grant_everyone(self.folder)
        self.assertFalse(runtime.is_private(self.folder))
        runtime.make_private(self.folder)
        self.assertTrue(runtime.is_private(self.folder))

    def test_an_entry_for_everyone_on_a_file_is_seen_and_removed(self) -> None:
        file = self.folder / "fictional.txt"
        file.write_text("x", encoding="utf-8")
        runtime.make_private(file)
        grant_everyone(file)
        self.assertFalse(runtime.is_private(file))
        runtime.make_private(file)
        self.assertTrue(runtime.is_private(file))

    def test_a_folder_with_inherited_entries_is_not_private(self) -> None:
        self.assertFalse(runtime.is_private(self.folder))  # it inherits the temporary folder's list

    def test_a_missing_path_is_refused_naming_it(self) -> None:
        with self.assertRaises(NotPrivate) as caught:
            runtime.make_private(self.folder / "missing")
        self.assertIn("missing", str(caught.exception))
        self.assertNotIsInstance(caught.exception, OSError)

    def test_without_username_and_user_the_published_file_is_private(self) -> None:
        # The reviewer's first scenario: no USERNAME, and the folder lets Everyone read what is made in it.
        grant_everyone(self.folder)
        environment = {key: value for key, value in os.environ.items() if key not in ("USERNAME", "USER")}
        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(subprocess, "Popen", side_effect=AssertionError("a subprocess ran")):
            runtime.write_state(self.payload())
        state = self.folder / "agent-state.json"
        self.assertTrue(runtime.is_private(state), "the published state file is not private")
        self.assertTrue(runtime.is_private(self.folder), "the folder is not private")
        self.assertEqual(runtime.read_state(), self.payload())

    def test_a_set_step_that_fails_leaves_nothing(self) -> None:
        real_set = runtime._windows_set

        def raise_on_temporary(path):
            if path.suffix == ".tmp":
                raise NotPrivate(path, "fictional failure")
            real_set(path)

        cases = {"raises for every path": mock.Mock(side_effect=NotPrivate("x", "fictional failure")),
                 "raises for the temporary file": raise_on_temporary,
                 "does nothing": lambda path: None}
        for name, set_step in sorted(cases.items()):
            with self.subTest(name):
                grant_everyone(self.folder)
                with mock.patch.object(runtime, "_windows_set", set_step):
                    with self.assertRaises(NotPrivate):
                        runtime.write_state(self.payload())
                self.assert_nothing_holds_the_token()

    def test_a_proof_that_fails_on_the_temporary_file_only_leaves_nothing(self) -> None:
        real_prove = runtime._windows_prove

        def prove(path):
            if path.suffix == ".tmp":
                raise NotPrivate(path, "fictional failure")
            real_prove(path)

        with mock.patch.object(runtime, "_windows_prove", prove):
            with self.assertRaises(NotPrivate):
                runtime.write_state(self.payload())
        self.assert_nothing_holds_the_token()

    # -- rule 4 of plan R16: the payload only into the published file, proved in place ---------------
    def held_proof(self, answers: list[bool] | None = None):
        """is_private that, at its first call (step (e)), opens the published file without delete
        sharing, as another process could, so the file cannot be unlinked afterwards."""
        real = runtime.is_private
        state = self.folder / "agent-state.json"

        def proof(path):
            if not self.held:
                self.held.append(open(state, "rb"))  # noqa: SIM115 - closed in cleanup
            return answers.pop(0) if answers else real(path)

        self.held: list = []
        self.addCleanup(lambda: [handle.close() for handle in self.held])
        return proof

    def assert_published_file_empty(self) -> None:
        state = self.folder / "agent-state.json"
        self.assertTrue(state.exists(), "the held file was unlinked after all")
        self.assertEqual(state.stat().st_size, 0)
        self.assertEqual(list(self.folder.glob("agent-state*.tmp")), [])

    def test_a_proof_failing_before_the_payload_leaves_no_file_and_writes_nothing(self) -> None:
        with mock.patch.object(runtime, "is_private", return_value=False), \
                mock.patch.object(runtime._Unbuffered, "write") as write:
            with self.assertRaises(NotPrivate):
                runtime.write_state(self.payload())
        write.assert_not_called()
        self.assert_nothing_holds_the_token()

    def test_a_proof_failing_after_the_payload_empties_a_file_that_cannot_be_deleted(self) -> None:
        with mock.patch.object(runtime, "is_private", self.held_proof([True, False])):
            with self.assertRaises(NotPrivate):
                runtime.write_state(self.payload())
        self.assert_published_file_empty()

    def test_a_json_dump_failing_after_part_of_the_payload_empties_the_file(self) -> None:
        payload = {**self.payload(), "zz-not-json": object()}  # sorted last: the token is written first
        written: list[str] = []
        real_write = runtime._Unbuffered.write

        def record(self_inner, text):
            written.append(text)
            real_write(self_inner, text)

        with mock.patch.object(runtime, "is_private", self.held_proof()), \
                mock.patch.object(runtime._Unbuffered, "write", record):
            with self.assertRaises(TypeError):
                runtime.write_state(payload)
        self.assertIn(f'"{TOKEN}"', "".join(written), "the payload was not partly written first")
        self.assert_published_file_empty()

    def test_a_failing_sync_empties_the_file(self) -> None:
        real_sync = os.fsync
        calls: list[int] = []

        def sync(descriptor):
            calls.append(descriptor)
            if len(calls) == 1:
                raise OSError("fictional sync failure")
            real_sync(descriptor)

        with mock.patch.object(runtime, "is_private", self.held_proof()), mock.patch.object(runtime.os, "fsync", sync):
            with self.assertRaises(OSError):
                runtime.write_state(self.payload())
        self.assert_published_file_empty()

    def test_a_failing_truncation_says_content_remains(self) -> None:
        with mock.patch.object(runtime, "is_private", side_effect=[True, False]), \
                mock.patch.object(runtime.os, "ftruncate", side_effect=OSError("fictional failure")):
            with self.assertRaises(NotPrivate) as caught:
                runtime.write_state(self.payload())
        self.assertIn("content remains", str(caught.exception))
        self.assertIn("agent-state.json", str(caught.exception))

    def test_prepare_runtime_dir_lets_not_private_out(self) -> None:
        grant_everyone(self.folder)
        with mock.patch.object(runtime, "_windows_set", lambda path: None):
            with self.assertRaises(NotPrivate):
                runtime.prepare_runtime_dir()

    def test_restrict_to_current_user_swallows_a_failure(self) -> None:
        with mock.patch.object(runtime, "_windows_set", side_effect=NotPrivate("x", "fictional failure")):
            runtime.restrict_to_current_user(self.folder)
        with mock.patch.object(runtime, "_windows_set", side_effect=OSError("fictional failure")):
            runtime.restrict_to_current_user(self.folder)


@unittest.skipUnless(sys.platform == "win32", "the agent's pipe here is a Windows named pipe")
class AgentCallersTest(TemporaryRuntime):
    def setUp(self) -> None:
        super().setUp()
        address = rf"\\.\pipe\PortableAIBrainVaultAgentTest-{secrets.token_hex(6)}"
        for patch in (mock.patch.object(vault_agent, "ipc_address", lambda: address),
                      mock.patch.object(vault_agent.VaultAgent, "LOCK_WAIT_SECONDS", 0)):
            patch.start()
            self.addCleanup(patch.stop)

    def agent(self) -> vault_agent.VaultAgent:
        agent = vault_agent.VaultAgent(self.folder / "fictional.vault")
        self.addCleanup(agent.shutdown)
        return agent

    def test_a_folder_that_cannot_be_proved_private_stops_the_start_before_a_listener(self) -> None:
        grant_everyone(self.folder)
        agent = self.agent()
        with mock.patch.object(runtime, "_windows_set", lambda path: None), \
                mock.patch.object(vault_agent, "Listener", side_effect=AssertionError("a listener was made")):
            with self.assertRaises(NotPrivate):
                agent.serve_forever()
        self.assertIsNone(agent._singleton_handle)
        self.assertIsNone(agent._listener)

    def test_a_state_file_that_cannot_be_proved_private_closes_the_listener_and_the_lock(self) -> None:
        real_prove = runtime._windows_prove

        def prove(path):
            if path.suffix == ".tmp":
                raise NotPrivate(path, "fictional failure")
            real_prove(path)

        agent = self.agent()
        with mock.patch.object(runtime, "_windows_prove", prove):
            with self.assertRaises(NotPrivate):
                agent.serve_forever()
        self.assertIsNone(agent._listener)
        self.assertIsNone(agent._singleton_handle)
        self.assert_nothing_holds_the_token()
        again = self.agent()
        again._acquire_singleton(wait_seconds=0)  # the lock was released
        self.assertIsNotNone(again._singleton_handle)

    def test_a_rewrite_that_cannot_be_proved_private_shuts_the_agent_down(self) -> None:
        agent = self.agent()
        outcome: list[BaseException] = []

        def serve():
            try:
                agent.serve_forever()
            except BaseException as exc:  # noqa: BLE001
                outcome.append(exc)

        state = self.folder / "agent-state.json"
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            deadline = time.time() + 5
            while time.time() < deadline and not state.is_file():
                time.sleep(0.02)
            self.assertTrue(state.is_file(), "the agent did not start")
            with mock.patch.object(vault_agent, "write_state", side_effect=NotPrivate(state, "fictional failure")):
                state.unlink()
                thread.join(5)
        self.assertFalse(thread.is_alive(), "the agent went on listening")
        self.assertIsNone(agent._listener)
        self.assertIsNone(agent._singleton_handle)
        self.assertEqual(len(outcome), 1)
        self.assertIsInstance(outcome[0], NotPrivate)
        self.assertIn("fictional failure", stderr.getvalue())
        self.assertIn("agent stopped", (self.folder / "tray.log").read_text(encoding="utf-8"))

    def test_serve_ends_non_zero_with_the_reason_on_standard_error(self) -> None:
        agent = mock.Mock()
        agent.serve_forever.side_effect = NotPrivate("fictional-folder", "fictional failure")
        with mock.patch.object(vault_agent, "build_agent", return_value=agent), \
                mock.patch.object(sys, "argv", ["vault_agent.py", "serve"]), \
                mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            code = vault_agent.main()
        self.assertEqual(code, 2)
        self.assertIn("fictional-folder cannot be proved private", stderr.getvalue())

    def test_the_tray_reports_a_folder_that_cannot_be_proved_private_as_a_failed_start(self) -> None:
        class FakeAgent:
            def serve_forever(self_inner):
                raise AssertionError("the agent started")

        with mock.patch.object(vault_tray, "_require_tray_deps", return_value=(None, None, None)), \
                mock.patch.object(vault_tray, "build_agent", lambda path=None: FakeAgent()), \
                mock.patch.object(vault_tray, "default_vault_path", lambda: "x"):
            app = vault_tray.VaultTrayApp()
        failure = NotPrivate("fictional-folder", "fictional failure")
        with mock.patch.object(vault_tray, "prepare_runtime_dir", side_effect=failure), \
                mock.patch.object(vault_tray, "log_tray") as log, \
                mock.patch.object(vault_tray, "_show_error") as show_error:
            code = app.run(prompt_on_start=False)
        self.assertEqual(code, 2)
        show_error.assert_called_once()
        self.assertIn("fictional failure", show_error.call_args.args[0])
        self.assertTrue(any("start failed" in call.args[0] for call in log.call_args_list))


@unittest.skipUnless(sys.platform == "win32", "the agent's pipe here is a Windows named pipe")
class BarrierTest(TemporaryRuntime):
    """Shutdown is a barrier (plan R16, rule 3, with both amendments), on the real pipe under a
    throwaway name, with the test's own in-process agent."""

    def setUp(self) -> None:
        super().setUp()
        self.address = rf"\\.\pipe\PortableAIBrainVaultAgentTest-{secrets.token_hex(6)}"
        for patch in (mock.patch.object(vault_agent, "ipc_address", lambda: self.address),
                      mock.patch.object(vault_agent.VaultAgent, "LOCK_WAIT_SECONDS", 0),
                      mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 5.0)):
            patch.start()
            self.addCleanup(patch.stop)
        self.release = threading.Event()  # set at cleanup, so nothing blocked outlives the test

    def start(self) -> tuple[vault_agent.VaultAgent, threading.Thread]:
        # Each change of the stopping flag records whether this thread owned the barrier (plan R17).
        self.flag_changes: list[bool] = []
        changes = self.flag_changes

        class Watched(vault_agent.VaultAgent):
            def __setattr__(self_inner, name, value):
                if name == "_stopping" and "_barrier" in self_inner.__dict__:
                    changes.append(self_inner._barrier._is_owned())
                super().__setattr__(name, value)

        agent = Watched(self.folder / "fictional.vault")
        changes.clear()  # the value __init__ gives it
        thread = threading.Thread(target=self._serve, args=(agent,), daemon=True)
        thread.start()
        state = self.folder / "agent-state.json"
        deadline = time.time() + 5
        while time.time() < deadline and not state.is_file():
            time.sleep(0.02)
        self.assertTrue(state.is_file(), "the agent did not start")
        self.addCleanup(self._stop, agent, thread)
        self.addCleanup(self.release.set)
        return agent, thread

    @staticmethod
    def _serve(agent) -> None:
        try:
            agent.serve_forever()
        except Exception:  # noqa: BLE001 - the tests look at the agent, not at this
            pass

    def _stop(self, agent, thread) -> None:
        agent.shutdown()
        if thread.is_alive():
            agent._wake_accept(self.address)
        thread.join(5)

    def client(self, agent):
        return Client(self.address, authkey=agent._authkey)

    @staticmethod
    def request(agent, op: str = "ping") -> dict:
        return {"v": runtime.AGENT_PROTOCOL_VERSION, "token": agent._auth_token, "op": op, "id": 1}

    def ask_in_thread(self, connection, request) -> tuple[threading.Thread, list]:
        outcome: list = []

        def ask():
            try:
                connection.send(request)
                outcome.append(("answer", connection.recv()))
            except Exception as exc:  # noqa: BLE001
                outcome.append(("no answer", exc))

        thread = threading.Thread(target=ask, daemon=True)
        thread.start()
        return thread, outcome

    def shutdown_in_thread(self, agent) -> tuple[threading.Thread, list]:
        outcome: list = []
        thread = threading.Thread(target=lambda: outcome.append((agent.shutdown(), time.monotonic())), daemon=True)
        thread.start()
        return thread, outcome

    def test_an_authenticated_client_after_shutdown_is_closed_unserved(self) -> None:
        agent, thread = self.start()
        with mock.patch.object(agent, "_serve_connection") as serve:
            self.assertTrue(agent.shutdown())
            connection = self.client(agent)  # the handshake succeeds: the key is right
            with self.assertRaises((EOFError, OSError)):
                connection.send(self.request(agent))
                connection.recv()
            thread.join(5)
        self.assertFalse(thread.is_alive(), "the accept loop did not end")
        serve.assert_not_called()

    def test_a_request_on_an_open_connection_after_shutdown_gets_no_answer(self) -> None:
        agent, _thread = self.start()
        connection = self.client(agent)
        with mock.patch.object(agent, "handle", wraps=agent.handle) as handle:
            connection.send(self.request(agent))
            self.assertIs(connection.recv()["ok"], True)
            self.assertTrue(agent.shutdown())
            with self.assertRaises((EOFError, OSError)):
                connection.send(self.request(agent))
                connection.recv()
        self.assertEqual(handle.call_count, 1)

    def test_an_operation_in_flight_ends_before_shutdown_returns_and_its_answer_is_not_delivered(self) -> None:
        agent, _thread = self.start()
        started, ended = threading.Event(), []

        def slow(request):
            started.set()
            self.release.wait(5)
            ended.append(time.monotonic())
            return {"ok": True, "id": 1, "result": "fictional"}

        with mock.patch.object(agent, "handle", slow):
            asking, answer = self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(started.wait(5))
            stopping, drained = self.shutdown_in_thread(agent)
            time.sleep(0.3)
            self.assertTrue(stopping.is_alive(), "shutdown returned while an operation was in flight")
            self.release.set()
            stopping.join(5)
            asking.join(5)
        self.assertTrue(drained[0][0])
        self.assertLessEqual(ended[0], drained[0][1])
        self.assertEqual(answer[0][0], "no answer")

    def test_shutdown_from_inside_an_operation_does_not_hang(self) -> None:
        agent, _thread = self.start()
        inside, done = [], threading.Event()

        def stop_from_inside(request):
            began = time.monotonic()
            inside.append((agent.shutdown(), time.monotonic() - began))
            done.set()
            return {"ok": True, "id": 1, "result": "fictional"}

        with mock.patch.object(agent, "handle", stop_from_inside):
            asking, answer = self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(done.wait(10), "shutdown from inside the operation did not return")
            asking.join(5)
        self.assertIs(inside[0][0], False)  # its own operation has not finished: never "drained" (plan R17)
        self.assertLess(inside[0][1], 2.0)
        self.assertEqual(answer[0][0], "no answer")
        self.assertEqual(self.flag_changes, [True])

    def test_a_shutdown_from_inside_an_operation_waits_for_the_others_and_returns_not_drained(self) -> None:
        agent, _thread = self.start()
        other_started, returned, inside, other_ended = threading.Event(), threading.Event(), [], []

        def handle(request):
            if request["op"] == "ping":  # the other operation, in flight when shutdown begins
                other_started.set()
                self.release.wait(5)
                other_ended.append(time.monotonic())
            else:
                inside.append(agent.shutdown())
                inside.append(time.monotonic())
                returned.set()
            return {"ok": True, "id": 1, "result": "fictional"}

        with mock.patch.object(agent, "handle", handle):
            other, other_answer = self.ask_in_thread(self.client(agent), self.request(agent, "ping"))
            self.assertTrue(other_started.wait(5))
            own, own_answer = self.ask_in_thread(self.client(agent), self.request(agent, "status"))
            deadline = time.time() + 2
            while time.time() < deadline and not agent._stopping:
                time.sleep(0.01)
            time.sleep(0.2)
            self.assertEqual(inside, [], "shutdown returned before the other operation ended")
            self.release.set()
            self.assertTrue(returned.wait(10), "shutdown from inside the operation did not return")
            own.join(5)
            other.join(5)
        self.assertIs(inside[0], False)
        self.assertLessEqual(other_ended[0], inside[1])  # the others drained first
        self.assertEqual((other_answer[0][0], own_answer[0][0]), ("no answer", "no answer"))
        self.assertEqual(self.flag_changes, [True])

    def test_an_answer_ready_when_shutdown_begins_is_suppressed_before_shutdown_drains(self) -> None:
        agent, _thread = self.start()
        ready, finished = threading.Event(), []
        real_finish = agent._finish

        def answer_ready():
            ready.set()
            self.release.wait(5)

        def finish():
            real_finish()
            finished.append(time.monotonic())

        with mock.patch.object(agent, "_answer_ready", answer_ready), mock.patch.object(agent, "_finish", finish):
            asking, answer = self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(ready.wait(5))
            stopping, drained = self.shutdown_in_thread(agent)
            deadline = time.time() + 2
            while time.time() < deadline and not agent._stopping:
                time.sleep(0.01)
            self.assertTrue(agent._stopping)
            self.assertTrue(stopping.is_alive(), "shutdown drained before the answer was suppressed")
            self.release.set()
            stopping.join(5)
            asking.join(5)
        self.assertTrue(drained[0][0])
        self.assertLessEqual(finished[0], drained[0][1])  # the thread passed the suppression first
        self.assertEqual(answer[0][0], "no answer")

    def test_shutdown_waits_for_a_send_under_way(self) -> None:
        agent, _thread = self.start()
        sending, sent = threading.Event(), []
        real_send = PipeConnection.send

        def send(connection, obj):
            if isinstance(obj, dict) and "ok" in obj:  # the agent's answer, not the client's request
                sending.set()
                self.release.wait(5)
                real_send(connection, obj)
                sent.append(time.monotonic())
            else:
                real_send(connection, obj)

        with mock.patch.object(PipeConnection, "send", send):
            asking, answer = self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            stopping, drained = self.shutdown_in_thread(agent)
            time.sleep(0.3)
            self.assertTrue(stopping.is_alive(), "shutdown did not wait for the send")
            self.release.set()
            stopping.join(5)
            asking.join(5)
        self.assertTrue(drained[0][0])
        self.assertLessEqual(sent[0], drained[0][1])
        self.assertEqual(answer[0][0], "answer")  # sent before stopping began

    def test_a_send_that_never_ends_leaves_shutdown_not_drained_within_its_bound(self) -> None:
        agent, _thread = self.start()
        sending = threading.Event()
        real_send = PipeConnection.send

        def send(connection, obj):
            if isinstance(obj, dict) and "ok" in obj:  # the answer: a client that does not read, until the test ends
                sending.set()
                self.release.wait(10)
            else:
                real_send(connection, obj)

        with mock.patch.object(PipeConnection, "send", send), \
                mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5):
            self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            register = set(agent._connections)
            began = time.monotonic()
            drained = agent.shutdown()
            took = time.monotonic() - began
            # Without the barrier shutdown touches nothing it protects (plan R17, rule 1).
            self.assertIs(drained, False)
            self.assertLess(took, 2.0)
            self.assertEqual(self.flag_changes, [], "the stopping flag changed without the barrier")
            self.assertIs(agent._stopping, False)
            self.assertEqual(agent._connections, register)
            self.assertTrue(register, "the held connection is not registered")
            self.release.set()
            time.sleep(0.2)
            self.assertIs(agent._stopping, False)
        self.assertNotIn(False, self.flag_changes)

    def test_a_failed_first_wake_up_is_retried_and_the_accept_loop_ends(self) -> None:
        agent, thread = self.start()
        real_client, calls = vault_agent.Client, []

        def client(address):
            calls.append(address)
            if len(calls) == 1:
                raise OSError("fictional failure")
            return real_client(address)

        self.assertTrue(agent.shutdown())
        with mock.patch.object(vault_agent, "Client", client):
            self.assertTrue(agent._wake_accept(self.address))
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(calls), 2)

    def test_an_accept_loop_that_never_ends_reaches_the_last_resort(self) -> None:
        state = self.folder / "agent-state.json"
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(vault_agent.VaultAgent, "WAKE_ATTEMPTS", 3), \
                mock.patch.object(vault_agent.VaultAgent, "WAKE_WAIT_SECONDS", 0.05), \
                mock.patch.object(vault_agent, "_exit_now") as exit_now, \
                mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            agent, _thread = self.start()
            with mock.patch.object(vault_agent, "Client", side_effect=OSError("fictional failure")), \
                    mock.patch.object(vault_agent, "write_state", side_effect=NotPrivate(state, "fictional failure")):
                state.unlink()
                deadline = time.time() + 5
                while time.time() < deadline and not exit_now.called:
                    time.sleep(0.02)
        exit_now.assert_called_once_with(2)
        self.assertIn("ends its process", stderr.getvalue())
        self.assertIsNone(agent._listener)
        self.assertIsNone(agent._singleton_handle)


if __name__ == "__main__":
    unittest.main()
