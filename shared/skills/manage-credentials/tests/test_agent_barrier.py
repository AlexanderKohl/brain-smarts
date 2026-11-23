"""Shutdown is a barrier, and the stop path ends the agent (follow-up plans R16 to R20): moved whole
out of test_state_private.py, whose temporary runtime base class it uses. Everything runs in real
temporary folders on the real pipe under a throwaway name, with the test's own in-process agent, never
the user's runtime folder; no real agent or tray is started, and every test replaces _exit_now."""
from __future__ import annotations

import contextlib
import io
import secrets
import sys
import threading
import time
import unittest
from multiprocessing.connection import Client
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime as runtime  # noqa: E402
from test_state_private import TemporaryRuntime  # noqa: E402
from vault_agent_runtime import NotPrivate  # noqa: E402

if sys.platform == "win32":
    from multiprocessing.connection import PipeConnection  # noqa: E402


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

    def hold_the_answer(self) -> tuple[threading.Event, list]:
        """PipeConnection.send that holds the agent's answer under the barrier until the test ends:
        a client that does not read. Returns the event set when the send began, and the event log."""
        sending, events = threading.Event(), []
        real_send = PipeConnection.send

        def send(connection, obj):
            if isinstance(obj, dict) and "ok" in obj:
                sending.set()
                self.release.wait(20)
                real_send(connection, obj)
                events.append("answer sent")
            else:
                real_send(connection, obj)

        patch = mock.patch.object(PipeConnection, "send", send)
        patch.start()
        self.addCleanup(patch.stop)
        return sending, events

    def test_a_send_that_never_ends_makes_shutdown_end_the_process(self) -> None:
        agent, _thread = self.start()
        sending, _events = self.hold_the_answer()
        with mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5), \
                mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            register = set(agent._connections)
            began = time.monotonic()
            agent.shutdown()  # returns only because the test replaced _exit_now
            took = time.monotonic() - began
        # Without the barrier shutdown touches nothing it protects (R17) and ends the process (R18).
        self.exits.assert_called_once_with(2)
        self.assertLess(took, 2.0)
        self.assertIn("could not take the barrier", stderr.getvalue())
        self.assertEqual(self.flag_changes, [], "the stopping flag changed without the barrier")
        self.assertIs(agent._stopping, False)
        self.assertEqual(agent._connections, register)
        self.assertTrue(register, "the held connection is not registered")
        # The process ends without the clean-up (R20, rule 2): the exit releases the singleton, and the
        # state file left behind names a process that is gone.
        self.assertIsNotNone(agent._singleton_handle)
        self.assertTrue((self.folder / "agent-state.json").exists())
        self.assertTrue(agent._shutdown_requested.is_set())

    def test_repeated_accept_errors_during_a_held_send_end_the_process_before_anything_more(self) -> None:
        # The reviewer's sequence (round 18): a send held under the barrier, then the accept loop's
        # repeated-error limit. The replaced exit stands for the end of the process: it records and
        # keeps its thread there, as a real exit would end every thread.
        agent, thread = self.start()
        sending, events = self.hold_the_answer()
        real_admit = agent._admit

        def admit():
            admitted = real_admit()
            events.append("admitted" if admitted else "refused")
            return admitted

        def end(code):
            events.append(f"exit {code}")
            self.release.wait(10)

        self.exits.side_effect = end
        with mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5), \
                mock.patch.object(agent, "_admit", admit), mock.patch.object(sys, "stderr", io.StringIO()):
            self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            register = set(agent._connections)
            agent._listener.accept = mock.Mock(side_effect=OSError("fictional accept failure"))
            try:
                Client(self.address).close()  # ends the accept that waits, so the failing one is used
            except Exception:  # noqa: BLE001
                pass
            deadline = time.time() + 15
            while time.time() < deadline and "exit 2" not in events:
                time.sleep(0.05)
            self.assertEqual(events, ["admitted", "exit 2"], "anything but the held answer before the exit")
            self.assertIs(agent._stopping, False)
            self.assertEqual(agent._connections, register)
            self.assertTrue(thread.is_alive(), "the accept loop went on past the exit")

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

    def test_keep_state_ends_the_process_before_any_wake_up_when_shutdown_did_not_drain(self) -> None:
        state, order = self.folder / "agent-state.json", []
        self.exits.side_effect = lambda code: order.append(f"exit {code}")
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(sys, "stderr", io.StringIO()) as stderr:
            agent, _thread = self.start()
            real_shutdown = agent.shutdown

            def not_drained():
                real_shutdown()
                return False  # operations still in flight at the end of the wait

            with mock.patch.object(agent, "shutdown", not_drained), \
                    mock.patch.object(vault_agent, "Client", side_effect=lambda address: order.append("wake-up")), \
                    mock.patch.object(vault_agent, "write_state", side_effect=NotPrivate(state, "fictional failure")):
                state.unlink()
                deadline = time.time() + 10
                while time.time() < deadline and "exit 2" not in order:
                    time.sleep(0.02)
                time.sleep(0.3)  # time enough for a wake-up that should not come
        self.assertEqual(order, ["exit 2"])
        self.assertIn("still in flight", stderr.getvalue())

    # -- plan R19: ending does not depend on standard error (the tray runs under pythonw) -----------
    def streams(self, kind: str):
        """No terminal streams at all ("none", as under pythonw), or a standard error whose write
        raises ("broken"). mock.patch restores both streams when the test leaves the block."""
        class Broken:
            def write(self, _text):
                raise OSError("fictional broken stream")

            def flush(self):
                raise OSError("fictional broken stream")

        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(sys, "stderr", None if kind == "none" else Broken()))
        if kind == "none":
            stack.enter_context(mock.patch.object(sys, "stdout", None))
        return stack

    def test_end_process_exits_whatever_the_streams_do(self) -> None:
        for kind in ("broken", "none"):
            with self.subTest(kind):
                self.exits.reset_mock()
                with self.streams(kind):
                    vault_agent._end_process(f"fictional reason {kind}")
                self.exits.assert_called_once_with(2)
                self.assertIn(f"agent ends its process: fictional reason {kind}",
                              (self.folder / "tray.log").read_text(encoding="utf-8"))

    def shutdown_without_the_barrier(self, kind: str) -> None:
        agent, _thread = self.start()
        sending, _events = self.hold_the_answer()
        with mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5):
            self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            with self.streams(kind):
                agent.shutdown()  # returns only because the test replaced _exit_now
        self.exits.assert_called_once_with(2)
        self.assertIs(agent._stopping, False)

    def test_a_shutdown_without_the_barrier_exits_with_a_broken_standard_error(self) -> None:
        self.shutdown_without_the_barrier("broken")

    def test_a_shutdown_without_the_barrier_exits_with_no_streams(self) -> None:
        self.shutdown_without_the_barrier("none")

    def keep_state_after_a_failed_proof(self, kind: str) -> None:
        state, order = self.folder / "agent-state.json", []
        self.exits.side_effect = lambda code: order.append(f"exit {code}")
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05):
            agent, _thread = self.start()
            real_shutdown = agent.shutdown

            def not_drained():
                order.append("shutdown")
                real_shutdown()
                return False

            with mock.patch.object(agent, "shutdown", not_drained), \
                    mock.patch.object(vault_agent, "write_state", side_effect=NotPrivate(state, "fictional failure")), \
                    self.streams(kind):
                state.unlink()
                deadline = time.time() + 10
                while time.time() < deadline and "exit 2" not in order:
                    time.sleep(0.02)
        self.assertEqual(order, ["shutdown", "exit 2"])
        self.assertIn("agent stopped", (self.folder / "tray.log").read_text(encoding="utf-8"))

    def test_keep_state_reaches_shutdown_and_the_exit_with_a_broken_standard_error(self) -> None:
        self.keep_state_after_a_failed_proof("broken")

    def test_keep_state_reaches_shutdown_and_the_exit_with_no_streams(self) -> None:
        self.keep_state_after_a_failed_proof("none")

    # -- plan R20: the fence first, visible at once, on every way out ---------------------------------
    @staticmethod
    def fenced(agent) -> bool:
        event = getattr(agent, "_shutdown_requested", None)
        return agent._stopping or (event is not None and event.is_set())

    def test_an_operation_holding_the_lock_does_not_hold_up_the_fence(self) -> None:
        # The reviewer's sequence (round 20): an admitted operation holds _lock when shutdown is called.
        agent, _thread = self.start()
        holding, order = threading.Event(), []
        real_admit = agent._admit

        def admit():
            admitted = real_admit()
            order.append(("admission tried", self.fenced(agent), admitted))
            return admitted

        def handle(request):
            if request["op"] == "status":
                with agent._lock:  # work without a bound, under the agent's lock
                    holding.set()
                    self.release.wait(10)
            return {"ok": True, "id": 1, "result": "fictional"}

        self.exits.side_effect = lambda code: order.append(("exit", code))
        second = self.client(agent)
        with mock.patch.object(agent, "handle", handle), mock.patch.object(agent, "_admit", admit), \
                mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            second.send(self.request(agent))
            self.assertIs(second.recv()["ok"], True)  # the second connection is registered and served
            self.ask_in_thread(self.client(agent), self.request(agent, "status"))
            self.assertTrue(holding.wait(5))
            order.append("shutdown called")
            stopping, _drained = self.shutdown_in_thread(agent)
            deadline = time.time() + 2
            while time.time() < deadline and not agent._stopping:
                time.sleep(0.01)
            self.assertTrue(agent._stopping, "the fence waited for the operation that holds _lock")
            asking, answer = self.ask_in_thread(second, self.request(agent))
            asking.join(3)
            stopping.join(5)
        self.assertEqual(answer[0][0], "no answer")
        after = order[order.index("shutdown called") + 1:]
        self.assertTrue(all(entry[1] and not entry[2] for entry in after if entry[0] == "admission tried"), after)
        self.assertIn(("exit", 2), after)  # the bound passed without _lock

    def test_end_process_reaches_the_exit_within_its_bound_when_standard_error_never_returns(self) -> None:
        release = self.release

        class Hanging:
            def write(self, _text):
                release.wait(10)

            def flush(self):
                release.wait(10)

        with mock.patch.object(vault_agent, "DIAGNOSTICS_SECONDS", 0.3, create=True), \
                mock.patch.object(sys, "stderr", Hanging()):
            ending = threading.Thread(target=vault_agent._end_process, args=("fictional reason",), daemon=True)
            ending.start()
            ending.join(3)
        self.exits.assert_called_once_with(2)

    def failed_proof(self, agent, order: list) -> None:
        state = self.folder / "agent-state.json"
        with mock.patch.object(vault_agent, "write_state", side_effect=NotPrivate(state, "fictional failure")):
            state.unlink()
            deadline = time.time() + 10
            while time.time() < deadline and not any(entry in ("exit 2", "loop ended") for entry in order) \
                    and not agent._serve_ended.is_set():
                time.sleep(0.02)
            time.sleep(0.1)

    def test_keep_state_puts_the_fence_up_before_any_diagnostics(self) -> None:
        order: list = []
        real_diagnose = vault_agent._diagnose

        def diagnose(message, tray_line):
            order.append(("diagnose", self.fenced(agent), agent._stopping))
            real_diagnose(message, tray_line)

        self.exits.side_effect = lambda code: order.append(f"exit {code}")
        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(vault_agent, "_diagnose", diagnose), mock.patch.object(sys, "stderr", io.StringIO()):
            agent, _thread = self.start()
            self.failed_proof(agent, order)
        self.assertEqual(order[0], ("diagnose", True, True), order)

    def test_after_a_failed_proof_the_event_is_set_before_the_lock_is_released(self) -> None:
        releases: list = []

        class Recording:
            def __init__(self, inner):
                self.inner = inner

            def acquire(self, *args, **kwargs):
                return self.inner.acquire(*args, **kwargs)

            def release(self):
                if threading.current_thread().name == "vault-agent-state":
                    event = getattr(agent, "_shutdown_requested", None)
                    releases.append((event is not None and event.is_set(), agent._stopping))
                self.inner.release()

            def __enter__(self):
                self.acquire()
                return self

            def __exit__(self, *_exc):
                self.release()

        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            agent, _thread = self.start()
            agent._lock = Recording(agent._lock)
            self.failed_proof(agent, [])
        before_the_fence = [event for event, stopping in releases if not stopping]
        self.assertTrue(before_the_fence, releases)
        self.assertTrue(before_the_fence[-1], "the lock was released after the failed proof before the event")

    def test_a_send_holding_the_barrier_does_not_let_anything_in_while_shutdown_waits(self) -> None:
        agent, _thread = self.start()
        second = self.client(agent)
        second.send(self.request(agent))
        self.assertIs(second.recv()["ok"], True)  # registered before
        order, sending = [], threading.Event()
        real_send = PipeConnection.send

        def send(connection, obj):
            if isinstance(obj, dict) and "ok" in obj:
                order.append("answer begins")
                if not sending.is_set():
                    sending.set()
                    self.release.wait(10)  # the first answer holds the barrier
            real_send(connection, obj)

        self.exits.side_effect = lambda code: order.append(f"exit {code}")
        with mock.patch.object(PipeConnection, "send", send), \
                mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 3.0), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            self.ask_in_thread(self.client(agent), self.request(agent))
            self.assertTrue(sending.wait(5))
            order.append("shutdown called")
            stopping, _drained = self.shutdown_in_thread(agent)
            time.sleep(0.2)
            asking, answer = self.ask_in_thread(second, self.request(agent))
            asking.join(2)
            self.assertEqual(answer, [("no answer", answer[0][1])] if answer else ["missing"],
                             "a request was not refused while shutdown waited for the barrier")
            third, third_answer = self.ask_in_thread(self.client(agent), self.request(agent))
            third.join(2)
            self.assertEqual(third_answer[0][0] if third_answer else "missing", "no answer")
            self.release.set()
            stopping.join(5)
        self.assertNotIn("answer begins", order[order.index("shutdown called"):])

    def test_a_diagnostics_thread_that_cannot_start_does_not_stop_the_exit(self) -> None:
        order: list = []
        self.exits.side_effect = lambda code: order.append(f"exit {code}")
        real_start = threading.Thread.start

        def start(thread):
            if thread.name == "vault-agent-diagnostics":
                raise RuntimeError("fictional: can't start new thread")
            real_start(thread)

        with mock.patch.object(vault_agent.VaultAgent, "STATE_CHECK_SECONDS", 0.05), \
                mock.patch.object(sys, "stderr", io.StringIO()):
            agent, _thread = self.start()
            real_shutdown = agent.shutdown

            def not_drained():
                real_shutdown()
                return False

            with mock.patch.object(agent, "shutdown", not_drained), mock.patch.object(threading.Thread, "start", start):
                self.failed_proof(agent, order)
        self.assertEqual(order, ["exit 2"])


    # -- plan R21: every abnormal end of serve_forever is fenced by the agent itself ------------------
    def test_a_worker_thread_that_cannot_start_fences_the_agent_before_serve_forever_raises(self) -> None:
        agent = vault_agent.VaultAgent(self.folder / "fictional.vault")
        outcome: list = []

        def serve():
            try:
                agent.serve_forever()
            except BaseException as exc:  # noqa: BLE001
                outcome.append((exc, self.fenced(agent)))

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        state = self.folder / "agent-state.json"
        deadline = time.time() + 5
        while time.time() < deadline and not state.is_file():
            time.sleep(0.02)
        self.addCleanup(self._stop, agent, thread)
        self.addCleanup(self.release.set)
        second = self.client(agent)
        second.send(self.request(agent))
        self.assertIs(second.recv()["ok"], True)  # registered before
        real_start = threading.Thread.start

        def start(worker):
            if getattr(worker, "_target", None) == agent._serve_connection:
                raise RuntimeError("fictional: can't start new thread")
            real_start(worker)

        with mock.patch.object(threading.Thread, "start", start), mock.patch.object(sys, "stderr", io.StringIO()):
            third = self.client(agent)  # accepted and registered; its worker cannot start
            thread.join(5)
        self.assertEqual(len(outcome), 1, "serve_forever did not end")
        self.assertIsInstance(outcome[0][0], RuntimeError)
        self.assertTrue(outcome[0][1], "serve_forever raised before the fence was up")
        asking, answer = self.ask_in_thread(second, self.request(agent))
        asking.join(3)
        self.assertEqual(answer[0][0], "no answer")
        third.close()

if __name__ == "__main__":
    unittest.main()
