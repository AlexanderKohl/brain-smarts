"""Tests for host_wiring.py with a temporary home and a temporary brain root."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import tempfile
import tomllib
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import host_wiring  # noqa: E402

REAL_TEMPLATES = SCRIPTS.parents[2] / "templates" / "host-pointers"
STAMP = date.today().strftime("%Y%m%d")


class HostWiringTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "work" / "brainy"
        self.home = self.tmp / "home"
        dest = self.root / "shared" / "templates" / "host-pointers"
        dest.mkdir(parents=True)
        for name in REAL_TEMPLATES.iterdir():
            if name.is_file():
                shutil.copy(name, dest / name.name)
        (self.root / "CONTRACT.md").write_text("contract\n", encoding="utf-8")
        (self.root / "memory").mkdir()
        (self.root / "memory" / "OWNER.md").write_text("---\nproject_repos_root: D:\\repos\n---\n", encoding="utf-8")
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "worker-test-low.md").write_text("---\nname: worker-test-low\n---\nBody\n", encoding="utf-8")
        self.home.mkdir()

    def cli(self, command: str, *extra: str) -> tuple[int, str]:
        argv = [command, "--home", str(self.home), "--root", str(self.root), *extra]
        out = io.StringIO()
        with mock.patch.object(host_wiring.setup_guard, "refusal", return_value=None), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = host_wiring.main(argv)
        return code, out.getvalue()

    def settings(self) -> dict:
        return json.loads((self.home / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def test_create_all_hosts(self) -> None:
        code, out = self.cli("apply", "--host", "claude-code", "--host", "codex", "--host", "cursor-cli")
        self.assertEqual(code, 0, out)
        pointer = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(f"{self.root.as_posix()}/CONTRACT.md", pointer)
        self.assertIn("D:/repos", pointer)
        self.assertNotIn("<BRAIN_ROOT>", pointer)
        self.assertFalse(pointer.startswith("---"))
        self.assertTrue((self.home / ".claude" / "agents" / "worker-test-low.md").is_file())
        self.assertEqual(self.settings()["permissions"]["defaultMode"], "acceptEdits")
        local = json.loads((self.root / ".claude" / "settings.local.json").read_text(encoding="utf-8"))
        self.assertEqual(local["permissions"]["additionalDirectories"], ["D:/repos"])
        cursor = json.loads((self.home / ".cursor" / "cli-config.json").read_text(encoding="utf-8"))
        self.assertEqual(cursor["approvalMode"], "allowlist")
        config = tomllib.loads((self.home / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(config["approval_policy"], "on-request")
        self.assertEqual(config["projects"][str(self.root)]["trust_level"], "trusted")
        self.assertTrue((self.home / ".codex" / "AGENTS.md").is_file())

    def test_merge_keeps_values_and_reports_conflicts(self) -> None:
        target = self.home / ".claude" / "settings.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"theme": "dark", "permissions": {
            "defaultMode": "plan", "deny": ["Bash(zzz)"], "allow": ["Bash(mine)"]}}), encoding="utf-8")
        code, out = self.cli("apply", "--host", "claude-code")
        self.assertEqual(code, 0, out)
        merged = self.settings()
        self.assertEqual(merged["theme"], "dark")
        self.assertEqual(merged["permissions"]["defaultMode"], "plan")
        self.assertIn("Bash(zzz)", merged["permissions"]["deny"])
        self.assertIn("Bash(git reset --hard*)", merged["permissions"]["deny"])
        self.assertEqual(merged["permissions"]["deny"], sorted(merged["permissions"]["deny"]))
        self.assertIn("Bash(mine)", merged["permissions"]["allow"])
        self.assertIn("conflict", out)
        self.assertIn("defaultMode", out)

    def test_user_settings_carry_the_context_check_with_an_absolute_script_path(self) -> None:
        target = self.home / ".claude" / "settings.json"
        target.parent.mkdir(parents=True)
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "example-filter"}]}
        target.write_text(json.dumps({"hooks": {"PostToolUse": [mine]}}), encoding="utf-8")
        self.assertEqual(self.cli("apply", "--host", "claude-code")[0], 0)
        hooks = self.settings()["hooks"]
        self.assertEqual(hooks["PostToolUse"], [mine])                       # the person's hook is kept
        command = f'python "{self.root.as_posix()}/shared/skills/repository-preflight/scripts/hooks.py" context-check'
        self.assertEqual(hooks["UserPromptSubmit"], [{"hooks": [{"type": "command", "command": command}]}])
        self.assertTrue(Path(command.split('"')[1]).is_absolute())
        code, out = self.cli("apply", "--host", "claude-code")
        self.assertEqual(code, 0)
        self.assertEqual(len(self.settings()["hooks"]["UserPromptSubmit"]), 1)   # never added twice
        self.assertNotIn("settings.json", " ".join(l for l in out.splitlines() if "merge" in l))

    def test_second_apply_unchanged_and_backup_once(self) -> None:
        pointer = self.home / ".claude" / "CLAUDE.md"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("old pointer\n", encoding="utf-8")
        code, out = self.cli("apply", "--host", "claude-code")
        self.assertEqual(code, 0)
        backup = pointer.with_name(f"CLAUDE.md.bak-{STAMP}")
        self.assertEqual(backup.read_text(encoding="utf-8"), "old pointer\n")
        self.assertIn("replace", out)
        code, out = self.cli("apply", "--host", "claude-code", "--host", "codex")
        self.assertEqual(code, 0)
        self.assertNotIn("replace", out)
        self.assertNotIn("merge ", out.replace("done unchanged", ""))
        self.assertEqual(backup.read_text(encoding="utf-8"), "old pointer\n")
        before = pointer.read_text(encoding="utf-8")
        pointer.write_text("edited again\n", encoding="utf-8")
        self.cli("apply", "--host", "claude-code")
        self.assertEqual(pointer.read_text(encoding="utf-8"), before)
        self.assertEqual(backup.read_text(encoding="utf-8"), "old pointer\n")   # the first backup is never overwritten

    def test_codex_toml_with_existing_table(self) -> None:
        config = self.home / ".codex" / "config.toml"
        config.parent.mkdir(parents=True)
        config.write_text('model = "x"\n\n[windows]\nsandbox = "unelevated"\n\n'
                          '[sandbox_workspace_write]\nnetwork_access = true\n', encoding="utf-8")
        code, out = self.cli("apply", "--host", "codex")
        self.assertEqual(code, 0, out)
        text = config.read_text(encoding="utf-8")
        data = tomllib.loads(text)
        self.assertEqual(data["model"], "x")
        self.assertEqual(data["windows"]["sandbox"], "unelevated")
        self.assertIs(data["sandbox_workspace_write"]["network_access"], True)    # kept, reported
        self.assertEqual(data["sandbox_workspace_write"]["writable_roots"], [str(Path("D:/repos")) if sys.platform == "win32" else "D:\\repos"])
        self.assertEqual(text.count("[sandbox_workspace_write]"), 1)
        self.assertLess(text.index("approval_policy"), text.index("[windows]"))
        self.assertIn("network_access", out)
        self.assertEqual(self.cli("apply", "--host", "codex")[0], 0)
        self.assertEqual(config.read_text(encoding="utf-8"), text)

    def test_defaults_level_writes_pointers_and_codex_trust_only(self) -> None:
        code, out = self.cli("apply", "--host", "claude-code", "--host", "codex", "--host", "cursor-cli",
                             "--level", "defaults")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.home / ".claude" / "settings.json").exists())
        self.assertFalse((self.root / ".claude" / "settings.local.json").exists())
        self.assertFalse((self.home / ".cursor").exists())
        data = tomllib.loads((self.home / ".codex" / "config.toml").read_text(encoding="utf-8"))
        self.assertEqual(list(data), ["projects"])
        self.assertEqual(data["projects"][str(self.root)]["trust_level"], "trusted")

    def test_edits_level_skips_local_allow_list(self) -> None:
        self.assertEqual(self.cli("apply", "--host", "claude-code", "--level", "edits")[0], 0)
        self.assertTrue((self.home / ".claude" / "settings.json").is_file())
        self.assertFalse((self.root / ".claude" / "settings.local.json").exists())

    def test_plan_writes_nothing(self) -> None:
        pointer = self.home / ".claude" / "CLAUDE.md"
        pointer.parent.mkdir(parents=True)
        pointer.write_text("old\n", encoding="utf-8")
        code, out = self.cli("plan", "--host", "claude-code", "--host", "codex")
        self.assertEqual(code, 0)
        self.assertIn("replace", out)
        self.assertIn("create", out)
        self.assertIn(f".bak-{STAMP}", out)
        self.assertEqual(pointer.read_text(encoding="utf-8"), "old\n")
        self.assertEqual([p.name for p in pointer.parent.iterdir()], ["CLAUDE.md"])
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse((self.root / ".claude" / "settings.local.json").exists())

    def test_refusal_in_session_copy_exits_2(self) -> None:
        err = io.StringIO()
        with mock.patch.object(host_wiring.setup_guard, "refusal", return_value="session copy"), \
                contextlib.redirect_stderr(err):
            code = host_wiring.main(["plan", "--host", "codex", "--home", str(self.home), "--root", str(self.root)])
        self.assertEqual(code, 2)
        self.assertIn("session copy", err.getvalue())

    def test_project_repos_root_falls_back_to_parent(self) -> None:
        (self.root / "memory" / "OWNER.md").unlink()
        self.assertEqual(self.cli("apply", "--host", "claude-code")[0], 0)
        pointer = (self.home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn(self.root.parent.as_posix(), pointer)


if __name__ == "__main__":
    unittest.main()
