"""The tray's ways out reach the agent's fence (follow-up plan R20, amendments): the quit and the end of run
call shutdown directly, and a start the tray gives up on is shut down before it is reported. No real tray
icon, dialog or agent of the user is used: the icon and the dialogs are replaced, the agent is the test's
own, unstarted or fake, in a temporary runtime folder, and the process exit is replaced."""
from __future__ import annotations

import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime  # noqa: E402

if sys.platform == "win32":
    import vault_tray  # noqa: E402


@unittest.skipUnless(sys.platform == "win32", "the tray is a Windows program")
class TrayStopTest(unittest.TestCase):
    def setUp(self) -> None:
        parent = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, parent, ignore_errors=True)
        self.folder = parent / "vault-agent"
        self.exits = mock.Mock(name="_exit_now")
        self.release = threading.Event()
        self.addCleanup(self.release.set)
        for patch in (mock.patch.object(vault_agent_runtime, "runtime_base", lambda: self.folder),
                      mock.patch.object(vault_agent, "_exit_now", self.exits),
                      mock.patch.object(vault_agent.VaultAgent, "DRAIN_SECONDS", 0.5),
                      mock.patch.object(vault_tray, "log_tray"),
                      mock.patch.object(vault_agent, "_diagnose")):
            patch.start()
            self.addCleanup(patch.stop)

    def app(self, agent):
        with mock.patch.object(vault_tray, "_require_tray_deps", return_value=(mock.Mock(), None, None)), \
                mock.patch.object(vault_tray, "build_agent", lambda path=None: agent), \
                mock.patch.object(vault_tray, "default_vault_path", lambda: "x"):
            return vault_tray.VaultTrayApp()

    def agent(self) -> vault_agent.VaultAgent:
        agent = vault_agent.VaultAgent(self.folder / "fictional.vault")
        self.addCleanup(agent.shutdown)
        return agent

    def hold_the_lock(self, agent) -> None:
        """An admitted operation that holds the agent's lock through work without a bound."""
        held = threading.Event()

        def hold():
            with agent._lock:
                held.set()
                self.release.wait(10)

        threading.Thread(target=hold, daemon=True).start()
        self.assertTrue(held.wait(5))

    def test_quit_with_an_operation_holding_the_lock_reaches_the_fence(self) -> None:
        agent = self.agent()
        app = self.app(agent)
        self.hold_the_lock(agent)
        quitting = threading.Thread(target=app._do_quit, args=(mock.Mock(),), daemon=True)
        quitting.start()
        quitting.join(3)
        self.assertTrue(agent._stopping, "the quit did not reach the fence")
        self.exits.assert_called_once_with(2)  # the lock could not be taken within the bound

    def test_the_end_of_run_with_an_operation_holding_the_lock_reaches_the_fence(self) -> None:
        agent = self.agent()
        app = self.app(agent)
        app.pystray.Icon.return_value.run.side_effect = lambda: self.hold_the_lock(agent)
        with mock.patch.object(app, "_start_broker"), mock.patch.object(vault_tray, "_make_icon"):
            running = threading.Thread(target=app.run, kwargs={"prompt_on_start": False}, daemon=True)
            running.start()
            running.join(5)
        self.assertTrue(agent._stopping, "the end of run did not reach the fence")
        self.exits.assert_called_once_with(2)

    def test_a_readiness_wait_that_times_out_shuts_the_agent_down_before_it_is_reported(self) -> None:
        order: list[str] = []
        release = self.release

        class Serving:
            _store = None

            def serve_forever(self_inner):
                release.wait(10)  # serves, but its state file is never seen

            def shutdown(self_inner):
                order.append("shutdown")
                return True

        app = self.app(Serving())
        with mock.patch.object(vault_tray.VaultAgent, "LOCK_WAIT_SECONDS", -4.7), \
                mock.patch.object(vault_tray, "prepare_runtime_dir"), \
                mock.patch.object(vault_tray, "_show_error", lambda _message: order.append("reported")):
            code = app.run(prompt_on_start=False)
        self.assertEqual(code, 2)
        self.assertEqual(order, ["shutdown", "reported"])


if __name__ == "__main__":
    unittest.main()
