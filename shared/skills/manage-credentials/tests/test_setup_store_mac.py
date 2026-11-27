"""setup_store.py on a computer without the tray (macOS, and Linux): the agent is started as
vault_agent.py serve, unlocked through vaultctl.py in the terminal, stopped with SIGTERM instead of
the person's Quit, and on macOS started at every login by a launchd login item. The tray's packages
are not installed there, and a Python without tkinter stops at once. The outside world is replaced as
in test_setup_store.py; every name is fictional. These tests run on every system."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import plistlib
import signal
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import setup_store  # noqa: E402
from test_setup_store import STORE, FakeGitHub, FakeSetup, SetupCase  # noqa: E402

LOCKED = {"backend": "vault", "unlocked": False}
UNLOCKED = {"backend": "vault", "unlocked": True}


class MacSetup(FakeSetup):
    def __init__(self, root, unlock_code=0, **kw):
        self.unlock_code = unlock_code
        super().__init__(root, platform="darwin", **kw)

    def unlock_in_terminal(self):
        self.log.append(("unlock_in_terminal",))
        return self.unlock_code

    def stop_agent(self):
        self.log.append(("stop_agent",))

    def login_item(self):
        self.log.append(("login_item",))


class MacCutOverTests(SetupCase):
    def test_the_agent_is_unlocked_in_the_terminal_and_stopped_without_the_tray(self):
        setup = MacSetup(self.root, statuses=[None, LOCKED, UNLOCKED, UNLOCKED, UNLOCKED, None, STORE],
                         old_vault=True, github=FakeGitHub())
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        steps = [e for e in setup.log if e[0] != "run"]
        self.assertEqual(steps, [("start_agent", None), ("unlock_in_terminal",), ("migrate", ("--dry-run",)),
                                 ("migrate", ()), ("stop_agent",), ("login_item",), ("start_agent", True)])
        self.assertFalse(any("tray" in line or "Quit" in line for line in setup.lines))
        self.assertTrue(any("every login" in line for line in setup.lines))

    def test_a_failed_terminal_unlock_stops_before_anything_moves(self):
        setup = MacSetup(self.root, unlock_code=1, statuses=[None, LOCKED], old_vault=True, github=FakeGitHub())
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn("old vault was not unlocked", self.err.getvalue())
        self.assertFalse(any(e[0] == "migrate" for e in setup.log))

    def test_linux_gets_no_login_item(self):
        setup = FakeSetup(self.root, statuses=[UNLOCKED] * 4 + [None, STORE], platform="linux",
                          old_vault=True, github=FakeGitHub())
        setup.stop_agent = lambda: setup.log.append(("stop_agent",))
        setup.login_item = lambda: self.fail("a login item on Linux")
        self.assertEqual(setup_store.main(["--no-sync"], setup), 0, self.err.getvalue())
        self.assertIn(("stop_agent",), setup.log)


class MacRequirementTests(SetupCase):
    def missing(self, platform):
        from importlib import metadata

        def version(name):
            raise metadata.PackageNotFoundError(name)
        with mock.patch.object(metadata, "version", version):
            return setup_store.Setup(self.root, platform=platform).missing_requirements()

    def test_the_tray_packages_are_installed_only_on_windows(self):
        names = lambda lines: sorted(line.split(">")[0] for line in lines)  # noqa: E731
        self.assertEqual(names(self.missing("darwin")), ["cryptography", "keyring"])
        self.assertEqual(names(self.missing("win32")), ["Pillow", "cryptography", "keyring", "pystray"])

    def test_a_marker_setup_cannot_read_stops(self):
        with self.assertRaises(setup_store.SetupError):
            setup_store._applies(' python_version >= "3.12"', "darwin")

    def test_a_python_without_tkinter_stops_with_the_homebrew_command(self):
        setup = MacSetup(self.root, github=FakeGitHub())
        setup.has_tk = lambda: False
        self.assertEqual(setup_store.main(["--no-sync"], setup), 1)
        self.assertIn(f"brew install python-tk@{sys.version_info.major}.{sys.version_info.minor}",
                      self.err.getvalue())
        self.assertEqual(setup.log, [])


class MacAgentTests(SetupCase):
    def test_the_login_item_starts_the_agent_at_login(self):
        home = self.root / "home"
        with mock.patch.object(setup_store.Path, "home", return_value=home), \
                mock.patch("vault_agent_runtime.tray_log_path", return_value=self.root / "tray & log"):
            setup_store.Setup(self.root, platform="darwin").login_item()
        path = home / "Library" / "LaunchAgents" / f"{setup_store.LOGIN_ITEM}.plist"
        item = plistlib.loads(path.read_bytes())
        self.assertEqual(item["Label"], setup_store.LOGIN_ITEM)
        self.assertEqual(item["ProgramArguments"][0], sys.executable)
        self.assertEqual(Path(item["ProgramArguments"][1]).name, "vault_agent.py")
        self.assertEqual(item["ProgramArguments"][2], "serve")
        self.assertIs(item["RunAtLoad"], True)
        self.assertEqual(item["StandardErrorPath"], str(self.root / "tray & log"))

    def test_the_agent_starts_in_a_session_of_its_own(self):
        with mock.patch.object(setup_store.child_process, "popen") as popen, \
                mock.patch("vault_agent_runtime.tray_log_path", return_value=self.root / "tray.log"):
            setup_store.Setup(self.root, platform="darwin").start_agent()
        command, options = popen.call_args.args[0], popen.call_args.kwargs
        self.assertEqual([Path(command[1]).name, command[2]], ["vault_agent.py", "serve"])
        self.assertIs(options["start_new_session"], True)

    def stop(self, command: bytes, pid=4242, error=None):
        shown = mock.Mock(stdout=command)
        with mock.patch("vault_agent_runtime.read_state", return_value={"pid": pid}), \
                mock.patch.object(setup_store.child_process, "run", return_value=shown) as ps, \
                mock.patch("os.kill", side_effect=error) as kill:
            setup_store.Setup(self.root, platform="darwin").stop_agent()
        return ps, kill

    def test_the_agent_is_stopped_with_sigterm(self):
        ps, kill = self.stop(b"/usr/bin/python3 /fictional/scripts/vault_agent.py serve\n")
        self.assertEqual(ps.call_args.args[0], ["ps", "-ww", "-p", "4242", "-o", "command="])
        kill.assert_called_once_with(4242, signal.SIGTERM)

    def test_a_pid_that_is_not_the_agent_is_never_signalled(self):
        _ps, kill = self.stop(b"/Applications/Fictional.app/Contents/MacOS/Fictional\n")
        kill.assert_not_called()

    def test_a_process_that_cannot_be_signalled_is_left_alone(self):
        for error in (PermissionError(1, "not permitted"), ProcessLookupError(3, "no such process")):
            with self.subTest(error):
                _ps, kill = self.stop(b"python3 vault_agent.py serve", error=error)
                kill.assert_called_once()

    def test_an_agent_that_ends_at_once_is_reported_with_its_own_words(self):
        log = self.root / "tray.log"
        log.write_text("an earlier line\n", "utf-8")
        ended = mock.Mock(returncode=2)
        ended.poll.return_value = 2
        setup = setup_store.Setup(self.root, platform="darwin")
        with mock.patch.object(setup_store.child_process, "popen", return_value=ended), \
                mock.patch("vault_agent_runtime.tray_log_path", return_value=log):
            setup.start_agent()
        log.write_text("an earlier line\nVault Agent failed: fictional cannot be proved private\n", "utf-8")
        with self.assertRaises(setup_store.SetupError) as caught:
            setup.agent_up()
        self.assertIn("code 2): Vault Agent failed: fictional cannot be proved private", str(caught.exception))
        self.assertNotIn("an earlier line", str(caught.exception))

    def test_sigterm_shuts_the_agent_down_and_wakes_its_accept_loop(self):
        import vault_agent
        agent = mock.Mock()
        agent.shutdown.return_value = True
        with mock.patch.object(vault_agent.os, "name", "posix"), \
                mock.patch.object(vault_agent, "ipc_address", return_value="fictional.sock"), \
                mock.patch("signal.signal") as install:
            vault_agent._stop_on_terminate(agent)
        signum, handler = install.call_args.args
        self.assertEqual(signum, signal.SIGTERM)
        handler(signum, None)
        for thread in [t for t in __import__("threading").enumerate() if t.name == "vault-agent-terminate"]:
            thread.join(5)
        agent._after_the_fence.assert_called_once_with(True, "fictional.sock")

    def test_no_state_file_sends_no_signal(self):
        with mock.patch("vault_agent_runtime.read_state", return_value=None), mock.patch("os.kill") as kill:
            setup_store.Setup(self.root, platform="darwin").stop_agent()
        kill.assert_not_called()


if __name__ == "__main__":
    unittest.main()
