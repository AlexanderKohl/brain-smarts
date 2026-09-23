"""Behavioural tests for skill_exchange.py on a fictional brain and a fictional upstream.

Run from the brain root:
    python -m unittest discover -s shared/skills/skill-exchange/scripts/tests -v

Every name and value here is invented (SMART-RULE-0008).
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import skill_exchange as sx  # noqa: E402

HAS_GIT = shutil.which("git") is not None
NOW = "2026-03-02T09:00:00+10:00"

OWNER = """---
id: owner-profile
owner_name: Robin Example-Tester
owner_short_name: Robin
github_account: robin-example
brain_root: {root}
project_repos_root: {repos}
active_skills:
  - garden-access
---
# Owner
"""


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(" ".join(args) + ": " + out.stderr)
    return out.stdout.strip()


def commit_all(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Fixture:
    """An upstream smarts repository, a brain cloned from it, and a memory folder."""

    def __init__(self, with_git: bool = True):
        self.base = Path(tempfile.mkdtemp(prefix="skill-exchange-"))
        self.upstream = self.base / "upstream"
        self.root = self.base / "brain"
        if with_git:
            self.upstream.mkdir()
            git(self.upstream, "init", "-q", "-b", "main")
            self.identity(self.upstream)
            write(self.upstream / "CONTRACT.md", "---\nid: c\n---\n# contract\n")
            write(self.upstream / "RULES.md", "Always use `/shared/skills/tidy-files/`.\n")
            write(self.upstream / ".gitignore", "memory/\n")
            for skill in ("garden-access", "tidy-files", "weather-access"):
                write(self.upstream / "shared/skills" / skill / "SKILL.md", "# " + skill + "\n")
            commit_all(self.upstream, "start")
            subprocess.run(["git", "clone", "-q", "-o", "upstream", str(self.upstream), str(self.root)],
                           check=True, capture_output=True)
            self.identity(self.root)
        else:
            self.root.mkdir()
            write(self.root / "CONTRACT.md", "---\nid: c\n---\n# contract\n")
        self.memory = self.root / "memory"
        write(self.memory / "OWNER.md", OWNER.format(root=self.root, repos=self.base))
        (self.memory / "projects" / "orchard-planner").mkdir(parents=True)

    @staticmethod
    def identity(repo: Path) -> None:
        git(repo, "config", "user.email", "tester@example.com")
        git(repo, "config", "user.name", "Tester")

    def brain(self, now: str = NOW) -> sx.Brain:
        return sx.Brain(str(self.root), now)

    def close(self) -> None:
        shutil.rmtree(self.base, ignore_errors=True)


@unittest.skipUnless(HAS_GIT, "git is not installed")
class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()
        up = self.f.upstream
        write(up / "shared/skills/garden-access/SKILL.md", "# garden-access v2\n")
        write(up / "shared/skills/tidy-files/SKILL.md", "# tidy-files v2\n")
        write(up / "shared/skills/weather-access/SKILL.md", "# weather v2\n")
        write(up / "shared/skills/compost-log/SKILL.md", "# compost-log\n")
        write(up / "RULES.md", "Always use `/shared/skills/tidy-files/`. And one more rule.\n")
        commit_all(up, "improvements")

    def tearDown(self):
        self.f.close()

    def test_changes_are_grouped_by_what_the_owner_uses(self):
        changes = sx.upstream_changes(self.f.brain())
        self.assertEqual(len(changes["commits"]), 1)
        self.assertEqual(changes["skills"], {"active": ["garden-access"], "always_on": ["tidy-files"],
                                             "new": ["compost-log"], "other": ["weather-access"]})
        self.assertEqual(changes["governance"], ["RULES.md"])

    def test_digest_is_ordered_capped_and_not_repeated(self):
        brain = self.f.brain()
        changes = sx.upstream_changes(brain)
        lines = sx.digest(brain, changes)
        self.assertEqual(lines[1], "1. changed skill you use: garden-access")
        self.assertEqual(lines[2], "2. changed skill every brain uses: tidy-files")
        self.assertIn("needs your acceptance", lines[3])
        self.assertEqual(lines[4], "4. new skill offered: compost-log")
        self.assertIn("1 other change", lines[5])
        sx.mark_reported(brain, changes)
        self.assertEqual(sx.digest(brain, sx.upstream_changes(brain, fetch=False)), [])

    def test_check_is_due_by_cadence(self):
        brain = self.f.brain()
        self.assertTrue(sx.due(brain)[0])
        sx.mark_reported(brain, sx.upstream_changes(brain))
        self.assertFalse(sx.due(self.f.brain("2026-03-05T09:00:00+10:00"))[0])
        self.assertTrue(sx.due(self.f.brain("2026-03-09T09:00:01+10:00"))[0])

    def test_provenance_is_recorded_and_local_edits_are_noticed(self):
        brain = self.f.brain()
        source = git(self.f.upstream, "rev-parse", "HEAD")
        entry = sx.record_install(brain, "weather-access", "https://example.com/someone/brain-smarts", source)
        self.assertEqual(entry["source_commit"], source)
        record = json.loads((self.f.memory / "skills" / "installed.json").read_text(encoding="utf-8"))
        self.assertEqual([e["skill"] for e in record["installed"]], ["weather-access"])
        self.assertIn("matches source", sx.verify_installs(brain)[0][1])
        write(self.f.root / "shared/skills/weather-access/SKILL.md", "# edited here\n")
        commit_all(self.f.root, "local edit")
        self.assertEqual(sx.verify_installs(brain)[0][1], "changed since install")


class ScrubTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture(with_git=False)
        self.skill = self.f.root / "shared/skills/garden-access"

    def tearDown(self):
        self.f.close()

    def test_owner_terms_and_patterns_are_found(self):
        write(self.skill / "SKILL.md", "Built for Robin by robin-example.\nSee C:" + "\\Users\\robin\\notes.txt\n"
                                       # Assembled at run time so this file itself passes a scrub.
                                       "Mail robin" + "@" + "realmail.test or call +61 7 " + "3000 0199.\n"
                                       "The orchard-planner node.\n")
        kinds = sorted({h[2] for h in sx.scrub(self.f.brain(), [str(self.skill)])})
        self.assertEqual(kinds, ["absolute-path", "email", "owner-term", "phone"])

    def test_clean_generic_text_passes_and_allow_list_is_honoured(self):
        write(self.skill / "SKILL.md", "Contact support@example.com. Version 1.2.3 on 2026-03-02.\n"
                                       "Account loc_EXAMPLE123 for Example Plumbing Pty Ltd.\n"
                                       "Call +1 555 010 0199 (reserved for fiction). Sent at 1700000000000 ms.\n")
        self.assertEqual(sx.scrub(self.f.brain(), [str(self.skill)]), [])
        write(self.skill / "extra.md", "Robin\n")
        write(self.f.memory / "skills/skill-exchange/scrub-allow.txt", "Robin\n")
        self.assertEqual(sx.scrub(self.f.brain(), [str(self.skill)]), [])


class CandidateTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture(with_git=False)

    def tearDown(self):
        self.f.close()

    def test_declined_candidate_returns_only_with_new_evidence(self):
        path = "/memory/projects/orchard-planner/skills/frost-alert"
        sx.candidate_add(self.f.brain(), path, "used by a second node")
        self.assertEqual([c["path"] for c in sx.candidates_to_suggest(self.f.brain())], [path])
        sx.candidate_mark(self.f.brain("2026-03-03T09:00:00+10:00"), path, "declined", "too specific")
        self.assertEqual(sx.candidates_to_suggest(self.f.brain()), [])
        sx.candidate_add(self.f.brain("2026-03-10T09:00:00+10:00"), path, "copied into a third node")
        self.assertEqual(len(sx.candidates_to_suggest(self.f.brain())), 1)

    def test_command_line_scrub_exit_code(self):
        skill = self.f.root / "shared/skills/garden-access"
        write(skill / "SKILL.md", "Owner: Robin\n")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = sx.main(["--root", str(self.f.root), "scrub", str(skill)])
        self.assertEqual(code, 1)
        self.assertIn("1 hit(s)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
