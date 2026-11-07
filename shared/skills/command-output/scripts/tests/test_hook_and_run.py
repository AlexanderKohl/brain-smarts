"""Behaviour of the host hook and the wrapper: each host's reply shape, failing open, and exit codes.

Every fixture is invented test-runner output (SMART-RULE-0008).
"""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import filtering  # noqa: E402
import hook  # noqa: E402
from test_filtering import failing_pytest  # noqa: E402


class Isolated(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / "out"
        env = {filtering.FOLDER: str(self.folder)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        os.environ.pop(filtering.SWITCH, None)
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def run_hook(self, host, payload):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        out = io.StringIO()
        code = hook.main([host], stdin=io.BytesIO(raw), stdout=out)
        self.assertEqual(code, 0)
        return json.loads(out.getvalue()) if out.getvalue() else None


class ClaudeCode(Isolated):
    def payload(self, **response):
        base = {"stdout": failing_pytest(), "stderr": "", "exit_code": 1, "interrupted": False}
        base.update(response)
        return {"tool_name": "Bash", "tool_input": {"command": "pytest", "description": "Run tests"},
                "tool_response": base, "cwd": "C:/work/example"}

    def test_long_output_is_replaced_in_the_tools_own_shape(self):
        reply = self.run_hook("claude-code", self.payload())
        output = reply["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PostToolUse")
        updated = output["updatedToolOutput"]
        self.assertEqual(set(updated), {"stdout", "stderr", "exit_code", "interrupted"})
        self.assertIn("E       assert 5 == 6", updated["stdout"])
        self.assertIn("exit code 1", updated["stdout"])
        self.assertEqual(updated["exit_code"], 1)

    def test_powershell_is_handled_like_bash(self):
        payload = self.payload()
        payload["tool_name"] = "PowerShell"
        self.assertIsNotNone(self.run_hook("claude-code", payload))

    def test_short_output_gets_no_reply(self):
        self.assertIsNone(self.run_hook("claude-code", self.payload(stdout="ok\n")))

    def test_output_claude_code_saved_itself_gets_no_reply(self):
        payload = self.payload(persistedOutputPath="C:/work/tool-results/abc.txt", persistedOutputSize=90000)
        self.assertIsNone(self.run_hook("claude-code", payload))
        self.assertFalse(self.folder.exists())

    def test_real_response_shape_without_an_exit_code(self):
        payload = self.payload()
        for key in ("exit_code",):
            payload["tool_response"].pop(key)
        payload["tool_response"].update({"isImage": False, "noOutputExpected": False})
        updated = self.run_hook("claude-code", payload)["hookSpecificOutput"]["updatedToolOutput"]
        self.assertEqual(set(updated), {"stdout", "stderr", "interrupted", "isImage", "noOutputExpected"})
        self.assertNotIn("exit code", updated["stdout"].splitlines()[-1])

    def test_interrupted_or_background_commands_get_no_reply(self):
        self.assertIsNone(self.run_hook("claude-code", self.payload(interrupted=True)))
        payload = self.payload()
        payload["tool_input"]["run_in_background"] = True
        self.assertIsNone(self.run_hook("claude-code", payload))

    def test_other_tools_get_no_reply(self):
        payload = self.payload()
        payload["tool_name"] = "Read"
        self.assertIsNone(self.run_hook("claude-code", payload))

    def test_bad_input_fails_open_and_is_logged(self):
        self.assertIsNone(self.run_hook("claude-code", b"{not json"))
        self.assertIn("claude-code", (self.folder / "errors.log").read_text(encoding="utf-8"))


class OtherHosts(Isolated):
    def test_codex_replaces_the_result_with_the_reason(self):
        reply = self.run_hook("codex", {"tool_name": "Bash", "tool_input": {"command": "pytest"},
                                        "tool_response": {"output": failing_pytest(), "exit_code": 1}})
        self.assertEqual(reply["decision"], "block")
        self.assertTrue(reply["reason"].startswith(hook.RAN_NOTE))
        self.assertIn("E       assert 5 == 6", reply["reason"])
        self.assertIn("exit code 1", reply["reason"])

    def test_gemini_cli_replaces_the_result_with_the_reason(self):
        reply = self.run_hook("gemini-cli", {"tool_name": "run_shell_command",
                                             "tool_input": {"command": "pytest"},
                                             "tool_response": {"llmContent": failing_pytest()}})
        self.assertEqual(reply["decision"], "deny")
        self.assertIn("E       assert 5 == 6", reply["reason"])

    def test_copilot_cli_returns_a_modified_result(self):
        reply = self.run_hook("copilot-cli", {"toolName": "bash", "toolArgs": json.dumps({"command": "pytest"}),
                                              "toolResult": {"resultType": "failure",
                                                             "textResultForLlm": failing_pytest()}})
        self.assertEqual(reply["modifiedResult"]["resultType"], "failure")
        self.assertIn("E       assert 5 == 6", reply["modifiedResult"]["textResultForLlm"])

    def test_settings_name_this_hook_for_each_host(self):
        for host, marker in (("claude-code", '"PostToolUse"'), ("codex", "[[hooks.PostToolUse]]"),
                             ("copilot-cli", '"postToolUse"'), ("gemini-cli", '"AfterTool"')):
            with self.subTest(host=host):
                out = io.StringIO()
                self.assertEqual(hook.main(["settings", host], stdin=io.BytesIO(b""), stdout=out), 0)
                self.assertIn(marker, out.getvalue())
                self.assertIn(f"command-output/scripts/hook.py {host}", out.getvalue())

    def test_unknown_host_is_refused(self):
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(hook.main(["notepad"], stdin=io.BytesIO(b"{}"), stdout=io.StringIO()), 2)


class Wrapper(Isolated):
    def wrap(self, *command):
        return subprocess.run([sys.executable, str(SCRIPTS / "run.py"), "--", *command],
                              capture_output=True, text=True, encoding="utf-8", env=os.environ.copy())

    def test_exit_code_is_the_commands_own(self):
        script = "import sys; print('\\n'.join('line %d' % i for i in range(400))); sys.exit(3)"
        done = self.wrap(sys.executable, "-c", script)
        self.assertEqual(done.returncode, 3)
        self.assertIn("exit code 3", done.stdout)
        self.assertIn("line 399", done.stdout)
        self.assertNotIn("line 200\n", done.stdout)

    def test_short_output_is_printed_unchanged(self):
        done = self.wrap(sys.executable, "-c", "print('hello')")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout.strip(), "hello")

    def test_a_missing_program_is_reported_with_127(self):
        done = self.wrap("no-such-program-for-command-output")
        self.assertEqual(done.returncode, 127)


if __name__ == "__main__":
    unittest.main()
