"""state.py: superseded handover entries leave a state file unchanged and nothing is lost."""
from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import state  # noqa: E402

FRONT = """---
id: example-state
title: Example State
type: state
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-01-01T09:00:00+10:00
updated: 2026-01-02T09:00:00+10:00
owner: brain-owner
---

# Example State

## Current position

Building.

"""
HEADED = FRONT + """## Handover

### Thread one, third checkpoint

- newest of thread one

### Thread two, only checkpoint

- thread two

### Thread one, second checkpoint

- older

### Thread one, first checkpoint

- oldest

## Handover prompt

Read the entry.
"""
BOLD = FRONT + """## Handover

**Checkpoint of day three:** newest.

**Checkpoint of day two:** older.

A plain paragraph that belongs to day two.

**Checkpoint of day one:** oldest.
"""
NOW = "2026-01-03T10:00:00+10:00"


def run(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = state.main(list(argv))
    return code, out.getvalue()


class StateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_keep_moves_every_other_entry_unchanged_and_in_order(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_text(HEADED, encoding="utf-8", newline="\n")
        assert run("history", str(path), "--keep", "1,2", "--now", NOW)[0] == 0
        kept = path.read_text(encoding="utf-8")
        history = (tmp_path / state.HISTORY).read_text(encoding="utf-8")
        assert "### Thread one, third checkpoint" in kept and "### Thread two, only checkpoint" in kept
        assert "second checkpoint" not in kept and "first checkpoint" not in kept
        assert history.index("### Thread one, second checkpoint\n\n- older") < history.index("### Thread one, first checkpoint\n\n- oldest")
        assert "id: example-state-history" in history and "type: state_history" in history
        assert f"## Moved from the state file at {NOW}" in history
        assert f"updated: {NOW}" in kept and "created: 2026-01-01T09:00:00+10:00" in kept
        # what is outside the section is untouched, and the section says where the rest went, once
        assert "## Current position\n\nBuilding." in kept and kept.rstrip().endswith("Read the entry.")
        assert kept.count(state.POINTER) == 1 and kept.index(state.POINTER) < kept.index("## Handover prompt")

    def test_a_second_move_appends_to_the_same_history_and_adds_no_second_pointer(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_text(HEADED, encoding="utf-8", newline="\n")
        run("history", str(path), "--move", "4", "--now", NOW)
        run("history", str(path), "--move-matching", "second checkpoint", "--now", "2026-01-04T10:00:00+10:00")
        history = (tmp_path / state.HISTORY).read_text(encoding="utf-8")
        assert history.count("\n---\n") == 1 and history.count("## Moved from the state file at") == 2
        assert history.index("- oldest") < history.index("- older")
        assert "updated: 2026-01-04T10:00:00+10:00" in history and f"created: {NOW}" in history
        assert path.read_text(encoding="utf-8").count(state.POINTER) == 1

    def test_bold_paragraph_entries_take_their_following_text_with_them(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_text(BOLD, encoding="utf-8", newline="\n")
        assert len(state.Handover(BOLD).entries) == 3
        run("history", str(path), "--keep", "1", "--now", NOW)
        kept = path.read_text(encoding="utf-8")
        history = (tmp_path / state.HISTORY).read_text(encoding="utf-8")
        assert "day three" in kept and "day two" not in kept and "plain paragraph" not in kept
        assert "**Checkpoint of day two:** older.\n\nA plain paragraph that belongs to day two.\n\n**Checkpoint of day one:**" in history

    def test_line_endings_are_kept_and_every_character_is_in_one_of_the_two_files(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_bytes(HEADED.replace("\n", "\r\n").encode("utf-8"))
        run("history", str(path), "--keep", "1", "--now", NOW)
        raw, history = path.read_bytes(), (tmp_path / state.HISTORY).read_bytes()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"") and b"\r\n" in history
        both = raw.decode("utf-8") + history.decode("utf-8")
        for line in HEADED.splitlines():
            if line and not line.startswith("updated:"):
                assert line in both, line

    def test_detail_leaves_the_first_line_and_a_pointer(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_text(HEADED, encoding="utf-8", newline="\n")
        assert run("detail", str(path), "--entry", "1", "--name", "thread-one", "--now", NOW)[0] == 0
        kept = path.read_text(encoding="utf-8")
        detail = (tmp_path / "HANDOVER-thread-one.md").read_text(encoding="utf-8")
        assert "### Thread one, third checkpoint\n\n- Detail: `HANDOVER-thread-one.md`" in kept and "newest of thread one" not in kept
        assert "- newest of thread one" in detail and "id: example-state-handover-thread-one" in detail
        assert "### Thread two, only checkpoint\n\n- thread two" in kept
        assert run("detail", str(path), "--entry", "2", "--name", "thread-one", "--now", NOW)[0] == 2  # never overwrites

    def test_check_names_the_files_over_the_limit_largest_first(self):
        tmp_path = Path(self.tmp.name)
        for name, size in (("small", 100), ("large", 900), ("larger", 1200)):
            folder = tmp_path / "memory" / "projects" / name
            folder.mkdir(parents=True)
            (folder / "STATE.md").write_text("x" * size, encoding="utf-8")
        generated = tmp_path / "memory" / "tasks"
        generated.mkdir()
        (generated / "STATE.md").write_text("x" * 5000, encoding="utf-8")  # a task store's generated list
        code, out = run("check", "--root", str(tmp_path), "--limit", "500")
        assert code == 1
        lines = out.splitlines()
        assert "larger" in lines[0] and "large" in lines[1] and "larger" not in lines[1]
        assert "small" not in out and "tasks" not in out and "2 of 3 state files" in out
        assert run("check", "--root", str(tmp_path), "--limit", "5000")[0] == 0

    def test_a_file_without_the_section_is_refused_and_left_alone(self):
        tmp_path = Path(self.tmp.name)
        path = tmp_path / "STATE.md"
        path.write_text(FRONT, encoding="utf-8", newline="\n")
        assert run("history", str(path), "--keep", "1")[0] == 2
        assert path.read_text(encoding="utf-8") == FRONT and not (tmp_path / state.HISTORY).exists()

    def test_the_size_validators_name_what_is_too_long_and_nothing_else(self):
        root = Path(self.tmp.name)
        node = root / "memory" / "projects" / "long"
        node.mkdir(parents=True)
        (node / "STATE.md").write_text("x" * (state.LIMIT + 1), encoding="utf-8")
        (node / "KNOWLEDGE.md").write_text("y" * state.LIMIT, encoding="utf-8")
        (root / "memory" / "tasks").mkdir()
        (root / "memory" / "tasks" / "STATE.md").write_text("x" * (state.LIMIT * 2), encoding="utf-8")
        errors: list[str] = []
        state.validate_state_sizes(root, errors)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("/memory/projects/long/STATE.md: 28,001 characters"))
        self.assertIn("state.py history", errors[0])
        errors = []
        state.validate_knowledge_sizes(root, errors)
        self.assertEqual(errors, [])
        (node / "KNOWLEDGE.md").write_text("y" * (state.LIMIT + 5), encoding="utf-8")
        state.validate_knowledge_sizes(root, errors)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("/memory/projects/long/KNOWLEDGE.md: 28,005 characters"))
        code, out = run("check", "--knowledge", "--root", str(root))
        self.assertEqual(code, 1)
        self.assertIn("1 of 1 knowledge files", out)

    def test_since_prints_the_commits_made_after_the_file_last_changed(self):
        import os
        import subprocess
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()

        def commit(message: str, when: str, *lines: str) -> None:
            env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when)
            subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q",
                            "-m", message, *[arg for line in lines for arg in ("-m", line)]], check=True, capture_output=True, env=env)

        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True)
        (repo / "STATE.md").write_text("position one\n", encoding="utf-8")
        commit("State: checkpoint", "2026-01-01T09:00:00+10:00")
        (repo / "a.txt").write_text("a\n", encoding="utf-8")
        commit("Add the first thing", "2026-01-02T09:00:00+10:00", "Release-note: first-thing")
        (repo / "b.txt").write_text("b\n", encoding="utf-8")
        commit("Fix the second thing", "2026-01-03T09:00:00+10:00")
        code, out = run("since", str(repo / "STATE.md"))
        self.assertEqual(code, 0)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("2 commits in repo since 2026-01-01T09:00:00+10:00"))
        self.assertIn("Fix the second thing", lines[1])
        self.assertIn("Add the first thing  [note: first-thing]", lines[2])
        self.assertNotIn("State: checkpoint", out)
        code, out = run("since", str(repo / "STATE.md"), "--from", "2026-01-02T12:00:00+10:00")
        self.assertTrue(out.startswith("1 commits in repo since 2026-01-02T12:00:00+10:00"))


class BulletEntriesTest(unittest.TestCase):
    def test_top_level_bullets_that_open_in_bold_are_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "STATE.md"
            path.write_text(FRONT + "## Handover\n\n- **Day three:** newest\n  - a detail of day three\n- **Day two:** older\n\n"
                            "  A paragraph of day two.\n\n- **Day one:** oldest\n\n## Handover prompt\n\nRead it.\n",
                            encoding="utf-8", newline="\n")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = state.main(["history", str(path), "--keep", "1", "--now", "2026-02-01T09:00:00+10:00"])
            self.assertEqual(code, 0, out.getvalue())
            text = path.read_text(encoding="utf-8")
            history = (Path(tmp) / "STATE-HISTORY.md").read_text(encoding="utf-8")
            self.assertIn("- **Day three:** newest\n  - a detail of day three\n", text)
            self.assertNotIn("Day two", text)
            self.assertIn("- **Day two:** older\n\n  A paragraph of day two.\n\n- **Day one:** oldest\n", history)
            self.assertIn("## Handover prompt\n\nRead it.\n", text)


KNOWLEDGE = """---
id: example-knowledge
title: Example Knowledge
type: knowledge
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-01-01T09:00:00+10:00
updated: 2026-01-02T09:00:00+10:00
owner: brain-owner
---

# Example Knowledge

Read `/CONTRACT.md` first.

## Terms

- A term.

## Terms for every product

- Longer terms.

### A part of the longer terms

- Detail.

## Prices

```text
## not a heading
```

- A price.

## Who we serve

- People.
"""


class SubjectsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.knowledge = self.dir / "KNOWLEDGE.md"
        self.knowledge.write_text(KNOWLEDGE, encoding="utf-8", newline="\n")
        self.plan = self.dir / "plan.json"

    def run_state(self, *argv: str) -> tuple[int, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = state.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def plan_of(self, *subjects: tuple[str, list[str]]) -> None:
        import json
        self.plan.write_text(json.dumps({"subjects": [
            {"name": name, "title": name.title(), "holds": f"what {name} holds", "sections": heads}
            for name, heads in subjects]}), encoding="utf-8")

    def test_sections_move_unchanged_and_the_index_lists_them(self) -> None:
        self.plan_of(("terms", ["Terms", "Terms for every product"]), ("prices", ["Prices"]))
        code, out = self.run_state("subjects", str(self.knowledge), "--plan", str(self.plan), "--now", "2026-02-01T09:00:00+10:00")
        self.assertEqual(code, 0, out)
        index = self.knowledge.read_text(encoding="utf-8")
        terms = (self.dir / "knowledge" / "terms.md").read_text(encoding="utf-8")
        prices = (self.dir / "knowledge" / "prices.md").read_text(encoding="utf-8")
        self.assertIn("## Terms\n\n- A term.\n\n## Terms for every product\n\n- Longer terms.\n\n### A part of the longer terms\n\n- Detail.\n", terms)
        self.assertIn("## Prices\n\n```text\n## not a heading\n```\n\n- A price.\n", prices)
        self.assertIn("id: example-knowledge-terms\n", terms)
        self.assertIn("type: knowledge\n", terms)
        self.assertNotIn("- A term.", index)
        self.assertNotIn("- A price.", index)
        self.assertIn("## Who we serve\n\n- People.\n", index)
        self.assertLess(index.index("- `knowledge/prices.md` – what prices holds"), index.index("- `knowledge/terms.md` – what terms holds"))
        self.assertLess(index.index("## Subjects"), index.index("## Who we serve"))
        self.assertIn("updated: 2026-02-01T09:00:00+10:00", index)
        self.assertIn("name it in the node's README.md", out)

    def test_a_second_run_adds_to_the_subject_file_and_the_list(self) -> None:
        self.plan_of(("terms", ["Terms"]))
        self.run_state("subjects", str(self.knowledge), "--plan", str(self.plan))
        self.plan_of(("terms", ["Terms for every product"]), ("people", ["Who we serve"]))
        code, out = self.run_state("subjects", str(self.knowledge), "--plan", str(self.plan))
        self.assertEqual(code, 0, out)
        terms = (self.dir / "knowledge" / "terms.md").read_text(encoding="utf-8")
        index = self.knowledge.read_text(encoding="utf-8")
        self.assertEqual(terms.count("# Terms\n"), 2)  # the title and the first section
        self.assertIn("- A term.\n\n## Terms for every product\n", terms)
        self.assertEqual(index.count("## Subjects"), 1)
        self.assertEqual(index.count("- `knowledge/"), 2)

    def test_an_unclear_name_changes_nothing(self) -> None:
        for heads in (["Term"], ["Nothing headed so"], ["Terms for every product", "A part of the longer terms"]):
            self.plan_of(("terms", heads))
            code, out = self.run_state("subjects", str(self.knowledge), "--plan", str(self.plan))
            self.assertEqual(code, 2, out)
            self.assertEqual(self.knowledge.read_text(encoding="utf-8"), KNOWLEDGE)
            self.assertFalse((self.dir / "knowledge").exists())

    def test_a_dry_run_changes_nothing(self) -> None:
        self.plan_of(("terms", ["Terms"]))
        code, out = self.run_state("subjects", str(self.knowledge), "--plan", str(self.plan), "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("would write terms.md", out)
        self.assertEqual(self.knowledge.read_text(encoding="utf-8"), KNOWLEDGE)

    def test_a_state_file_keeps_a_line_and_the_knowledge_file_lists_the_subject(self) -> None:
        path = self.dir / "STATE.md"
        path.write_text(HEADED.replace("## Handover\n", "## What works today\n\n### The list sorts\n\n- by name\n\n### The page prints\n\n- on A4\n\n## Handover\n", 1), encoding="utf-8", newline="\n")
        self.plan_of(("behaviour", ["The list sorts", "The page prints"]))
        code, out = self.run_state("subjects", str(path), "--plan", str(self.plan), "--now", "2026-02-01T09:00:00+10:00")
        self.assertEqual(code, 0, out)
        text = path.read_text(encoding="utf-8")
        self.assertIn("## What works today\n\nKept as knowledge since 2026-02-01, moved unchanged: `knowledge/behaviour.md` beside this file – what behaviour holds.\n\n## Handover\n", text)
        self.assertIn("### The list sorts\n\n- by name\n\n### The page prints\n\n- on A4\n", (self.dir / "knowledge" / "behaviour.md").read_text(encoding="utf-8"))
        self.assertIn("- `knowledge/behaviour.md` – what behaviour holds", self.knowledge.read_text(encoding="utf-8"))

    def test_a_section_that_is_history_moves_whole(self) -> None:
        path = self.dir / "STATE.md"
        path.write_text(HEADED.replace("## Handover\n", "## Earlier snapshots (historical)\n\n### August\n\n- then\n\n## Handover\n", 1), encoding="utf-8", newline="\n")
        code, out = self.run_state("history", str(path), "--section", "Earlier snapshots", "--now", "2026-02-01T09:00:00+10:00")
        self.assertEqual(code, 0, out)
        text = path.read_text(encoding="utf-8")
        history = (self.dir / "STATE-HISTORY.md").read_text(encoding="utf-8")
        self.assertNotIn("Earlier snapshots", text)
        self.assertIn("## Earlier snapshots (historical)\n\n### August\n\n- then\n", history)
        self.assertIn("### Thread one, third checkpoint", text)
        self.assertIn(state.POINTER, text)
        code, out = self.run_state("history", str(path), "--section", "Handover")
        self.assertEqual(code, 2, out)


if __name__ == "__main__":
    unittest.main()
