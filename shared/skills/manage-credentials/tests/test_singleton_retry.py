"""A busy singleton lock is retried; only a lock held for the whole wait means another agent.

Everything runs in a temporary runtime folder, never the owner's running agent."""
from __future__ import annotations

import errno
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vault_agent  # noqa: E402
import vault_agent_runtime  # noqa: E402
from portable_vault import CredentialError  # noqa: E402

if sys.platform == "win32":
    import vault_tray  # noqa: E402


class SingletonRetryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp())
        for patch in (
            mock.patch.object(vault_agent_runtime, "runtime_dir", lambda: self.folder),
            mock.patch.object(vault_agent, "restrict_to_current_user", lambda path: None),
            mock.patch.object(vault_agent.VaultAgent, "LOCK_RETRY_SECONDS", 0.01),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def agent(self) -> vault_agent.VaultAgent:
        agent = vault_agent.VaultAgent(self.folder / "fictional.vault")
        self.addCleanup(agent._release_singleton)
        return agent

    def test_a_busy_lock_is_retried_until_it_is_free(self) -> None:
        agent = self.agent()
        busy = OSError(errno.EACCES, "locked")
        attempts = [busy, busy, None]

        def try_lock(handle):
            outcome = attempts.pop(0)
            if outcome is not None:
                raise outcome

        with mock.patch.object(vault_agent.VaultAgent, "_try_lock", staticmethod(try_lock)):
            agent._acquire_singleton(wait_seconds=5)
        self.assertEqual(attempts, [])
        self.assertIsNotNone(agent._singleton_handle)

    def test_a_lock_held_for_the_whole_wait_means_another_agent(self) -> None:
        first = self.agent()
        first._acquire_singleton(wait_seconds=0)
        second = self.agent()
        with self.assertRaises(vault_agent.AgentAlreadyRunning):
            second._acquire_singleton(wait_seconds=0.2)
        self.assertIsNone(second._singleton_handle)

    def test_any_other_failure_is_reported_with_its_cause_and_without_waiting(self) -> None:
        agent = self.agent()
        failure = OSError(errno.ENOSPC, "No space left on device")
        with mock.patch.object(vault_agent.VaultAgent, "_try_lock", staticmethod(mock.Mock(side_effect=failure))) as m:
            with mock.patch.object(vault_agent.time, "sleep") as sleep:
                with self.assertRaises(CredentialError) as caught:
                    agent._acquire_singleton(wait_seconds=30)
        self.assertNotIsInstance(caught.exception, vault_agent.AgentAlreadyRunning)
        self.assertIn("No space left", str(caught.exception))
        sleep.assert_not_called()

    def test_a_lock_file_that_cannot_be_opened_names_the_file(self) -> None:
        agent = self.agent()
        with mock.patch.object(Path, "open", side_effect=PermissionError(errno.EACCES, "denied")):
            with self.assertRaises(CredentialError) as caught:
                agent._acquire_singleton(wait_seconds=0)
        self.assertIn("agent.singleton", str(caught.exception))
        self.assertNotIsInstance(caught.exception, vault_agent.AgentAlreadyRunning)


class TrayLogTest(unittest.TestCase):
    def test_a_line_is_appended_and_a_failure_never_raises(self) -> None:
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        with mock.patch.object(vault_agent_runtime, "runtime_dir", lambda: folder):
            vault_agent_runtime.log_tray("first")
            vault_agent_runtime.log_tray("second")
            lines = (folder / "tray.log").read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[1].endswith("second"))
        with mock.patch.object(vault_agent_runtime, "runtime_dir", side_effect=OSError("gone")):
            vault_agent_runtime.log_tray("nowhere")


@unittest.skipUnless(sys.platform == "win32", "the tray is a Windows program")
class TrayStartTest(unittest.TestCase):
    def make_app(self, another_running: bool):
        class FakeAgent:
            def serve_forever(self_inner):
                raise vault_agent.AgentAlreadyRunning("Another Vault Agent instance is already running")

        with mock.patch.object(vault_tray, "_require_tray_deps", return_value=(None, None, None)), \
                mock.patch.object(vault_tray, "build_agent", lambda path=None: FakeAgent()), \
                mock.patch.object(vault_tray, "default_vault_path", lambda: "x"):
            app = vault_tray.VaultTrayApp()
        return app

    def run_app(self, healthy: bool):
        app = self.make_app(healthy)
        with mock.patch.object(vault_tray, "prepare_runtime_dir"), \
                mock.patch.object(vault_tray, "log_tray"), \
                mock.patch.object(vault_tray, "broker_available", return_value=healthy), \
                mock.patch.object(vault_tray, "_show_error") as show_error, \
                mock.patch.object(vault_tray.VaultAgent, "LOCK_WAIT_SECONDS", 0, create=True):
            code = app.run(prompt_on_start=False)
        return code, show_error

    def test_a_healthy_agent_already_running_ends_quietly(self) -> None:
        code, show_error = self.run_app(healthy=True)
        self.assertEqual(code, 0)
        show_error.assert_not_called()

    def test_a_lock_held_by_something_that_does_not_answer_is_reported(self) -> None:
        code, show_error = self.run_app(healthy=False)
        self.assertEqual(code, 2)
        show_error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
