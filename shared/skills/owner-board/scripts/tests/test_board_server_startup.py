"""The board server at start-up (design 04, increment 5): the install script registers one
scheduled task that starts the server at log-on, bound to this machine only, and `-Uninstall`
removes it. The script is read, never run: a test must not register a task on the machine it
runs on. The same file checks what the task starts: a second start while the port is taken says so
and exits 0 instead of sharing the port, and a process with no stderr (pythonw) still answers.
Every name is invented (SMART-RULE-0008). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -p "test_board_server_startup.py" -v
"""
from __future__ import annotations

import contextlib
import http.client
import io
import re
import shutil
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from board_fixtures import Brain  # noqa: E402  (puts the scripts folder on sys.path)

import serve_boards  # noqa: E402

SCRIPT = Path(serve_boards.__file__).resolve().parent / "install_board_server.ps1"
TEXT = SCRIPT.read_text(encoding="utf-8")
CODE = "\n".join(line for line in TEXT.splitlines() if not line.lstrip().startswith("#"))
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


class InstallScriptTests(unittest.TestCase):
    def test_it_starts_serve_boards_bound_to_this_machine_only_on_port_8765(self):
        self.assertIn("shared\\skills\\owner-board\\scripts\\serve_boards.py", CODE)
        self.assertRegex(CODE, r'\$bindAddress = "127\.0\.0\.1"')
        self.assertRegex(CODE, r"\$port = 8765\b")
        self.assertRegex(CODE, r"--port \$port --bind \$bindAddress")
        self.assertNotRegex(CODE, r"0\.0\.0\.0|\[::\]|--bind\s+(?!\$bindAddress)")
        self.assertEqual(re.findall(r"\d+\.\d+\.\d+\.\d+", CODE), ["127.0.0.1"], "no other address appears in the script's code")

    def test_the_trigger_is_log_on_of_the_current_user_and_nothing_else(self):
        self.assertEqual(re.findall(r"New-ScheduledTaskTrigger\s+(-\w+)", CODE), ["-AtLogOn"])
        self.assertIn('-User "$env:USERDOMAIN\\$env:USERNAME"', CODE)
        self.assertNotIn("-AtStartup", CODE)
        self.assertNotIn("-RunLevel Highest", CODE, "the task is not elevated")
        self.assertIn("-RunLevel Limited", CODE)
        self.assertIn("-LogonType Interactive", CODE)

    def test_one_mechanism_no_startup_folder_shortcut(self):
        self.assertEqual(len(re.findall(r"Register-ScheduledTask\b", CODE)), 1)
        for word in ("Startup", "CreateShortcut", "WScript.Shell", "HKCU"):
            self.assertNotIn(word, CODE)

    def test_it_has_an_uninstall_switch_that_removes_the_one_task_and_exits_first(self):
        self.assertRegex(CODE, r"param\(\s*\[switch\]\$Uninstall\s*\)")
        self.assertIn('$taskName = "BrainBoardServer"', CODE)
        self.assertEqual(len(re.findall(r"Unregister-ScheduledTask -TaskName \$taskName\b", CODE)), 1)
        self.assertLess(CODE.index("if ($Uninstall)"), CODE.index("Register-ScheduledTask"), "-Uninstall never reaches the registration")
        uninstall = CODE[CODE.index("if ($Uninstall)"):CODE.index("$repoRoot =")]
        self.assertIn("exit 0", uninstall)

    def test_the_task_restarts_a_failed_server_runs_one_copy_and_has_no_time_limit(self):
        for setting in ("-RestartCount 3", "-MultipleInstances IgnoreNew", "-ExecutionTimeLimit ([TimeSpan]::Zero)", "-DontStopIfGoingOnBatteries"):
            self.assertIn(setting, CODE)

    def test_it_refuses_a_session_copy_and_a_folder_that_is_not_the_brain(self):
        self.assertIn('Join-Path $repoRoot ".git"', CODE)
        self.assertIn("-PathType Container", CODE)
        self.assertIn('Join-Path $repoRoot "CONTRACT.md"', CODE)

    def test_it_does_not_start_the_server_itself_and_names_no_machine_path_or_person(self):
        acts = chr(10).join(l for l in CODE.splitlines() if not l.lstrip().startswith("Write-Host"))     # the hints may name the command
        self.assertNotIn("Start-ScheduledTask", acts)
        self.assertNotIn("Start-Process", acts)
        self.assertNotRegex(TEXT, r"[A-Za-z]:\\(Users|dev)\b")
        self.assertNotIn(chr(0x2014), TEXT, "en dashes only")

    @unittest.skipUnless(POWERSHELL, "no PowerShell on this machine to parse the script")
    def test_the_script_parses(self):
        command = ("$e = $null; [void][System.Management.Automation.Language.Parser]::ParseFile('%s', [ref]$null, [ref]$e); "
                   "if ($e -and $e.Count) { $e | ForEach-Object { $_.Message }; exit 1 }" % str(SCRIPT).replace("'", "''"))
        run = subprocess.run([POWERSHELL, "-NoProfile", "-NonInteractive", "-Command", command], capture_output=True, text=True, timeout=60)
        self.assertEqual((run.returncode, run.stdout.strip()), (0, ""), run.stdout + run.stderr)


class SecondStartTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.addCleanup(self.brain.close)

    def start(self, quiet: bool = True):
        handler = serve_boards.make_handler(self.brain.config())
        if quiet:
            handler.log_message = lambda *a: None
        server = serve_boards.BoardServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_a_second_server_cannot_share_the_port_of_the_first(self):
        first = self.start()
        with self.assertRaises(OSError) as caught:
            serve_boards.BoardServer(("127.0.0.1", first.server_address[1]), serve_boards.Handler)
        self.assertIn(caught.exception.errno, serve_boards.PORT_TAKEN)

    def test_a_second_start_says_the_server_already_runs_and_exits_0(self):
        first = self.start()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = serve_boards.main(["--port", str(first.server_address[1]), "--root", str(self.brain.root)])
        self.assertEqual(code, 0)
        self.assertEqual(out.getvalue().strip(), "the board server already runs on port %d" % first.server_address[1])

    def test_the_default_bind_is_this_machine_only_on_port_8765(self):
        seen = {}

        class Spy:
            def __init__(self, address, handler):
                seen["address"] = address
                raise OSError(serve_boards.errno.EADDRINUSE, "taken")

        with mock.patch.object(serve_boards, "BoardServer", Spy), contextlib.redirect_stdout(io.StringIO()):
            serve_boards.main(["--root", str(self.brain.root)])
        self.assertEqual(seen["address"], ("127.0.0.1", 8765))

    def test_a_request_is_answered_when_the_process_has_no_stderr(self):
        """pythonw gives a process no stderr: the per-request log line must not break the answer."""
        server = self.start(quiet=False)
        with mock.patch.object(sys, "stderr", None):
            conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
            conn.request("GET", "/_board-server.json")
            self.assertEqual(conn.getresponse().status, 200)
            conn.close()


if __name__ == "__main__":
    unittest.main()
