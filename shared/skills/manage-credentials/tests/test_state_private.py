"""The agent's state file is published only into a folder and a file proved private (follow-up plan R15,
fix 1, and R16); shutdown as a barrier is tested in test_agent_barrier.py, the POSIX proof in
test_state_private_posix.py.
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
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime as runtime  # noqa: E402
from vault_agent_runtime import NotPrivate  # noqa: E402

if sys.platform == "win32":
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
        self.exits = mock.Mock(name="_exit_now")  # no test may end the test process (plan R18)
        for patch in (mock.patch.object(runtime, "runtime_base", lambda: self.folder),
                      mock.patch.object(vault_agent, "_exit_now", self.exits)):
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


if __name__ == "__main__":
    unittest.main()
