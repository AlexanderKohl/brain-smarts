"""Behavioural tests for the owner-board scripts, on a fictional brain built in a temporary folder.

Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

Every name, product and identifier here is invented (SMART-RULE-0008).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import apply_verdicts  # noqa: E402
import board_config  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import card as card_cli  # noqa: E402
import cards  # noqa: E402
import reconcile  # noqa: E402
import task_board  # noqa: E402
import verdicts  # noqa: E402

HAS_GIT = shutil.which("git") is not None

BOARD_MD = """---
id: example-garden-board
title: The board
type: reference
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-01-05T09:00:00+10:00
updated: 2026-01-05T09:00:00+10:00
owner: Sam
---

# The board

```json
{
  "id": "garden",
  "label": "Garden Planner",
  "generated": "2026-01-05T09:00:00+10:00",
  "mainVersion": "1.1.0",
  "tracks": {
    "beds": {"label": "Beds", "task": "TASK-2026-0901", "done": 2, "of": 5},
    "seeds": {"label": "Seeds", "task": "TASK-2026-0902", "done": 0, "of": 3}
  },
  "appId": "exampleappid",
  "abandoned": {"spike/old-layout": "superseded by 1.0.0"},
  "closed": {"1.0.0": "first release"}
}
```
"""

CARD = """---
id: {id}
title: {title}
type: board_card
schema_version: 0.2
contract: /CONTRACT.md
parent: /memory/projects/example-garden
created: 2026-01-05T09:00:00+10:00
updated: 2026-01-05T09:00:00+10:00
owner: Sam
track: {track}
state: {state}
version: {version}
branch: {branch}
asked: 2026-01-0{n}
area:
where_text: Garden Planner - Beds
where_view: {view}
where_href:
---

# {title}

## What landed

Raised beds now show their soil depth: 0 of 12 beds unlabelled, was 7.

## To check

Open Beds and look at the depth column.
"""


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError(" ".join(args) + ": " + out.stderr)
    return out.stdout


class Brain:
    """A fictional brain: CONTRACT.md, memory/OWNER.md, one or two boards, optional product repo."""

    def __init__(self, with_repo: bool = False, second_board: bool = False):
        self.root = Path(tempfile.mkdtemp(prefix="owner-board-"))
        (self.root / "CONTRACT.md").write_text("---\nid: c\n---\n# contract\n", encoding="utf-8")
        self.memory = self.root / "memory"
        self.repos = self.root.parent / (self.root.name + "-repos")
        self.memory.mkdir()
        (self.memory / "OWNER.md").write_text(
            "---\nid: owner-profile\nowner_short_name: Sam\nproject_repos_root: "
            + str(self.repos) + "\n---\n# Owner\n", encoding="utf-8")
        tasks = self.memory / "tasks" / "open"
        tasks.mkdir(parents=True)
        (tasks / "TASK-2026-0901-beds.md").write_text("---\nid: TASK-2026-0901\nstatus: ready\n---\n", encoding="utf-8")
        (self.memory / "tasks" / "STATE.md").write_text("| TASK-2026-0901 | ready |\n", encoding="utf-8")
        entries = [self.board_entry("garden", "Garden Planner", "projects/example-garden/status", with_repo)]
        self.make_board("projects/example-garden/status", "garden")
        if second_board:
            entries.append(self.board_entry("pond", "Pond Pump", "projects/example-pond/status", False))
            self.make_board("projects/example-pond/status", "pond")
        config = self.memory / "skills" / "owner-board" / "config"
        config.mkdir(parents=True)
        (config / "boards.json").write_text(json.dumps({"boards": entries}, indent=2), encoding="utf-8")
        if with_repo:
            self.make_repo()

    @staticmethod
    def board_entry(board_id: str, label: str, status: str, with_repo: bool) -> dict:
        entry = {"id": board_id, "label": label, "status": status, "blurb": "A fictional " + label.lower(),
                 "where_view_href": "example-app://{appId}/index.html[?plot={plotId}]#{view}"}
        if with_repo:
            entry.update({"repo": "{project_repos_root}/example-garden",
                          "committed_version": {"file": "package.json", "key": "version"},
                          "built_version": {"file": "dist/manifest.json", "key": "version"},
                          "copy_only_prefixes": ["example-app://"]})
        return entry

    def make_board(self, status: str, board_id: str) -> None:
        folder = self.memory / status
        (folder / "cards").mkdir(parents=True)
        (folder / "board.md").write_text(BOARD_MD.replace('"garden"', '"' + board_id + '"'), encoding="utf-8")
        for n, (cid, state, version, branch, view) in enumerate([
                ("soil-depth", "needs_review", "1.1.0", "", "beds"),
                ("seed-list", "building", "", "feature/seed-list", ""),
                ("frost-dates", "queued", "", "", "")], start=1):
            (folder / "cards" / (cid + ".md")).write_text(CARD.format(
                id=cid, title="show me the " + cid.replace("-", " "), track="beds" if n < 3 else "seeds",
                state=state, version=version or "null", branch=branch or "null", n=n, view=view),
                encoding="utf-8")

    def make_repo(self) -> None:
        remote = self.repos / "example-garden.git"
        repo = self.repos / "example-garden"
        remote.mkdir(parents=True)
        git(remote, "init", "-q", "--bare", "-b", "main")
        repo.mkdir()
        git(repo, "init", "-q", "-b", "main")
        git(repo, "config", "user.email", "tester@example.com")
        git(repo, "config", "user.name", "Tester")
        (repo / "package.json").write_text('{"version": "1.0.0"}', encoding="utf-8")
        git(repo, "add", "package.json")
        git(repo, "commit", "-q", "-m", "start")
        git(repo, "remote", "add", "origin", str(remote))
        # A merged release, 1.2.0, that no card mentions.
        git(repo, "checkout", "-q", "-b", "release/1.2.0")
        (repo / "package.json").write_text('{"version": "1.2.0"}', encoding="utf-8")
        git(repo, "commit", "-q", "-am", "bump")
        git(repo, "checkout", "-q", "main")
        git(repo, "merge", "-q", "--no-ff", "-m", "Merge 1.2.0 beds", "release/1.2.0")
        # A pushed branch nobody is building.
        git(repo, "checkout", "-q", "-b", "fix/orphan")
        (repo / "notes.txt").write_text("x", encoding="utf-8")
        git(repo, "add", "notes.txt")
        git(repo, "commit", "-q", "-m", "orphan")
        git(repo, "checkout", "-q", "main")
        git(repo, "push", "-q", "origin", "main", "fix/orphan", "release/1.2.0")
        (repo / "dist").mkdir()
        (repo / "dist" / "manifest.json").write_text('{"version": "1.1.0"}', encoding="utf-8")
        self.repo = repo

    def config(self) -> board_config.Config:
        return board_config.Config(self.root)

    def board(self, which: str = "garden") -> dict:
        return self.config().board(which)

    def close(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.repos, ignore_errors=True)


def quiet(fn, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        result = fn(*args, **kwargs)
    return result, out.getvalue()


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(with_repo=False)

    def tearDown(self):
        self.brain.close()

    def test_brain_root_found_from_a_nested_folder(self):
        nested = self.brain.memory / "projects" / "example-garden" / "status" / "cards"
        self.assertEqual(board_config.find_brain_root(nested), self.brain.root.resolve())

    def test_board_defaults_and_owner_name_come_from_the_profile(self):
        board = self.brain.board()
        self.assertEqual(board["owner"], "Sam")
        self.assertEqual(board["title"], "Garden Planner: where we are")
        self.assertEqual(board["verdict_prefix"], "garden-verdicts-")
        self.assertEqual(board["node"], "/memory/projects/example-garden")

    def test_board_is_inferred_from_the_current_folder(self):
        config = self.brain.config()
        folder = self.brain.memory / "projects" / "example-garden" / "status" / "cards"
        self.assertEqual(config.board(cwd=folder)["id"], "garden")

    def test_repo_placeholder_is_filled_from_the_owner_profile(self):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["boards"][0]["repo"] = "{project_repos_root}/example-garden"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertEqual(self.brain.board()["repo"], self.brain.repos / "example-garden")

    def test_missing_configuration_is_a_plain_error(self):
        (self.brain.memory / "skills" / "owner-board" / "config" / "boards.json").unlink()
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = board_config.cli(build_status.main, ["--root", str(self.brain.root)])
        self.assertEqual(code, 2)
        self.assertIn("no owner-board configuration", err.getvalue())

    def test_a_config_path_rewritten_by_git_bash_names_the_fix(self):
        mangled = "C:/Program Files/Git/memory/skills/owner-board/config/boards.json"
        with contextlib.redirect_stderr(io.StringIO()) as err:
            code = board_config.cli(build_status.main, ["--root", str(self.brain.root), "--config", mangled])
        self.assertEqual(code, 2)
        self.assertIn("MSYS_NO_PATHCONV=1", err.getvalue())


class CardTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.board = self.brain.board()

    def tearDown(self):
        self.brain.close()

    def test_round_trip_keeps_every_field_and_writes_empty_as_empty(self):
        data = cards.load(self.board)
        original = next(c for c in data["items"] if c["id"] == "soil-depth")
        original["sent_back"] = "the depth is in inches, I want centimetres"
        cards.write(self.board, original)
        text = (self.board["folder"] / "cards" / "soil-depth.md").read_text(encoding="utf-8")
        self.assertRegex(text, r"\nwhere_href: ?\n")
        self.assertNotIn("[]", text)
        self.assertIn("## Sam sent it back", text)
        again = next(c for c in cards.load(self.board)["items"] if c["id"] == "soil-depth")
        for key in ("title", "state", "version", "track", "landed", "review", "sent_back", "where", "area"):
            self.assertEqual(again[key], original[key], key)

    def test_unreadable_card_raises_rather_than_vanishing(self):
        (self.board["folder"] / "cards" / "broken.md").write_text("no front matter", encoding="utf-8")
        with self.assertRaises(ValueError):
            cards.load(self.board)

    def test_card_cli_creates_and_merges_a_card(self):
        root = ["--root", str(self.brain.root), "--board", "garden"]
        _, out = quiet(card_cli.main, root + ["new", "compost", "--track", "beds", "--branch", "fix/compost",
                                              "--title", "where does the compost go"])
        self.assertIn("status.html", out)
        quiet(card_cli.main, root + ["set", "compost", "--state", "needs_review", "--version", "1.3.0",
                                     "--branch", "-"])
        found = next(c for c in cards.load(self.board)["items"] if c["id"] == "compost")
        self.assertEqual((found["state"], found["version"], found["branch"]), ("needs_review", "1.3.0", None))
        self.assertEqual(found["title"], "where does the compost go")


class PageTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(second_board=True)

    def tearDown(self):
        self.brain.close()

    def page_data(self, path: Path) -> tuple:
        text = path.read_text(encoding="utf-8")
        grab = lambda name: json.loads(re.search(
            r'<script id="' + name + r'" type="application/json">(.*?)</script>', text, re.S)
            .group(1).replace("<\\/", "</"))
        return text, grab("config"), grab("data")

    def test_status_page_carries_owner_labels_and_built_links(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"))
        text, page, data = self.page_data(self.brain.memory / "projects/example-garden/status/status.html")
        self.assertIn("<title>Garden Planner: where we are</title>", text)
        self.assertEqual(page["labels"]["needsReview"], "Needs Sam's review")
        soil = next(i for i in data["items"] if i["id"] == "soil-depth")
        # `plotId` is not a board field, so the bracketed part is left out.
        self.assertEqual(soil["where"]["href"], "example-app://exampleappid/index.html#beds")
        self.assertNotIn("__", re.sub(r"__[a-z]", "", text).split("<script>")[0])

    def test_view_href_keeps_an_optional_part_when_its_field_exists(self):
        href = build_status.view_href("x://{appId}/p[?plot={plotId}]#{view}", "a b", {"appId": "q", "plotId": "7"})
        self.assertEqual(href, "x://q/p?plot=7#a%20b")
        self.assertEqual(build_status.view_href("x://{missing}#{view}", "v", {}), "")

    def test_directory_lists_every_board_with_counts_and_relative_links(self):
        config = self.brain.config()
        quiet(build_boards.build, config, None, "2026-01-05 09:00")
        text = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="../projects/example-garden/status/status.html"', text)
        self.assertIn('href="../projects/example-pond/status/status.html"', text)
        self.assertEqual(text.count('<span class="n you"><b>1</b>Needs you</span>'), 2)


class VerdictTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(second_board=True)
        self.config = self.brain.config()
        self.garden = self.config.board("garden")
        self.inbox = Path(verdicts.inbox(self.garden))
        self.inbox.mkdir()

    def tearDown(self):
        self.brain.close()

    def save(self, board: dict, entries: list, name: str, board_id: str | None = None) -> Path:
        data = cards.load(board)
        sigs = {c["id"]: c["sig"] for c in data["items"]}
        body = {"schema": board["verdict_schema"], "board": board_id if board_id is not None else board["id"],
                "verdicts": [dict(e, sig=e.get("sig", sigs.get(e["id"], ""))) for e in entries]}
        folder = Path(verdicts.inbox(board))
        folder.mkdir(exist_ok=True)
        path = folder / (board["verdict_prefix"] + name + ".json")
        path.write_text(json.dumps(body), encoding="utf-8")
        return path

    def test_accept_closes_and_rework_keeps_the_owner_words(self):
        path = self.save(self.garden, [{"id": "soil-depth", "verdict": "accepted"},
                                       {"id": "seed-list", "verdict": "rework", "why": "sort by sowing month"}], "a")
        applied, skipped = verdicts.apply(self.garden, str(path))
        self.assertEqual((len(applied), skipped), (2, []))
        self.assertFalse((self.garden["folder"] / "cards" / "soil-depth.md").exists())
        _, _, board_json = cards.read_board_json(self.garden)
        self.assertIn("1.1.0", board_json["closed"])
        seed = next(c for c in cards.load(self.garden)["items"] if c["id"] == "seed-list")
        self.assertEqual((seed["state"], seed["sent_back"]), ("rework", "sort by sowing month"))
        self.assertTrue((self.garden["folder"] / "verdicts-applied" / path.name).exists())

    def test_a_verdict_on_a_changed_card_is_refused(self):
        path = self.save(self.garden, [{"id": "soil-depth", "verdict": "accepted", "sig": "000000000000"}], "b")
        applied, skipped = verdicts.apply(self.garden, str(path))
        self.assertEqual(applied, [])
        self.assertIn("changed after the verdict", skipped[0])
        self.assertTrue((self.garden["folder"] / "cards" / "soil-depth.md").exists())

    def test_a_file_from_another_board_is_refused(self):
        path = self.save(self.garden, [{"id": "soil-depth", "verdict": "accepted"}], "c", board_id="pond")
        with self.assertRaises(verdicts.Refused):
            verdicts.apply(self.garden, str(path))

    def test_router_sends_each_file_to_the_board_it_names(self):
        pond = self.config.board("pond")
        self.save(self.garden, [{"id": "frost-dates", "verdict": "rework", "why": "garden"}], "d")
        self.save(pond, [{"id": "frost-dates", "verdict": "rework", "why": "pond"}], "e")
        changed, _ = quiet(apply_verdicts.route, self.config, False)
        self.assertEqual(sorted(changed), ["garden", "pond"])
        for board, why in ((self.garden, "garden"), (pond, "pond")):
            frost = next(c for c in cards.load(board)["items"] if c["id"] == "frost-dates")
            self.assertEqual(frost["sent_back"], why)

    def test_dry_run_changes_nothing(self):
        path = self.save(self.garden, [{"id": "soil-depth", "verdict": "accepted"}], "f")
        before = (self.garden["folder"] / "board.md").read_text(encoding="utf-8")
        verdicts.apply(self.garden, str(path), dry_run=True)
        self.assertTrue(path.exists())
        self.assertEqual((self.garden["folder"] / "board.md").read_text(encoding="utf-8"), before)


class ReconcileTests(unittest.TestCase):
    def test_task_checks_run_without_a_repository(self):
        brain = Brain()
        try:
            said = reconcile.check(brain.board())
            self.assertIn("TASK-2026-0901 still says ready, but the beds track has landed work or has a card in flight.", said)
            self.assertIn("TASK-2026-0902 is the task for the seeds track and has no record in /memory/tasks/open.", said)
        finally:
            brain.close()

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_git_disagreements_are_reported(self):
        brain = Brain(with_repo=True)
        try:
            board = brain.board()
            board["fetch"] = False
            said = reconcile.check(board)
            self.assertIn("dist/ is built at 1.1.0 but main is 1.2.0 - the owner loads dist, so this is what they see.", said)
            self.assertIn("origin/fix/orphan is pushed and not merged - no card on the board is building it, and no worktree exists", said)
            self.assertIn("1.2.0 is merged into main and has no card - the owner has not seen it.", said)
            self.assertIn("seed-list says it is being built, but feature/seed-list has no worktree and is not on origin - nobody is building it.", said)
            self.assertIn("The board says main is 1.1.0; git says 1.2.0.", said)
        finally:
            brain.close()

    def test_a_missing_repository_is_said_not_silent(self):
        brain = Brain()
        try:
            board = brain.board()
            board["repo"] = brain.repos / "not-there"
            self.assertTrue(any("does not exist" in s for s in reconcile.check(board)))
        finally:
            brain.close()


TASK = """---
id: {id}
title: {title}
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: {status}
owner: Sam
priority: {priority}
created: 2026-01-02T09:00:00+10:00
updated: {updated}
due: {due}
next_review: {review}
waiting_on: {waiting}
project_refs:{refs}
---

# {title}
"""

TEMPLATE = """---
id: TASK-YYYY-NNNN
title: Clear action or outcome
type: task
schema_version: 0.2
contract: /CONTRACT.md
status: inbox
owner: OWNER_SHORT_NAME
priority: normal
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
due: null
next_review: null
waiting_on: null
project_refs: []
skill_refs: []
depends_on: []
---

# Clear action or outcome

## Outcome

## Next action

## History
"""

STATE = """# Current State

| Task | Status | Priority | Review / waiting on | Title |
|---|---|---|---|---|
| `TASK-2026-0901` | **ready** | normal | - | Beds |
"""

TODAY = __import__("datetime").date(2026, 1, 10)


class TaskBoardTests(unittest.TestCase):
    """Tasks shown on boards: routing, fallback, no duplication, order, the new-task path."""

    def setUp(self):
        self.brain = Brain(second_board=True)
        today = mock.patch.object(task_board, "local_today", return_value=TODAY)
        today.start()
        self.addCleanup(today.stop)
        store = self.brain.memory / "tasks"
        for folder in ("inbox", "completed", "templates"):
            (store / folder).mkdir(parents=True, exist_ok=True)
        (store / "templates" / "TASK_TEMPLATE.md").write_text(TEMPLATE, encoding="utf-8")
        (store / "STATE.md").write_text(STATE, encoding="utf-8")
        self.add("TASK-2026-0910", "open", "ready", ["/memory/projects/example-garden"], priority="low")
        self.add("TASK-2026-0911", "open", "ready", ["/memory/projects/example-garden"], priority="high",
                 due="2026-02-01")
        self.add("TASK-2026-0912", "open", "ready", ["/memory/projects/example-garden"], priority="high",
                 due="2026-01-15")
        # The first reference has no board, the second has: the second decides.
        self.add("TASK-2026-0913", "open", "waiting", ["/memory/projects/example-shed", "/memory/projects/example-pond"],
                 review="2026-01-20", waiting="Example Pumps Pty Ltd")
        # A folder beneath a board's node belongs to that board.
        self.add("TASK-2026-0914", "open", "waiting", ["/memory/projects/example-pond/filters"],
                 review="2026-01-08", waiting="a delivery")
        self.add("TASK-2026-0915", "open", "in_progress", ["/memory/projects/example-shed"])
        self.add("TASK-2026-0916", "inbox", "inbox", [])
        self.add("TASK-2026-0917", "completed", "completed", ["/memory/projects/example-garden"], updated="2026-01-09T10:00:00+10:00")
        self.add("TASK-2026-0918", "completed", "completed", ["/memory/projects/example-garden"], updated="2025-11-01T10:00:00+10:00")

    def tearDown(self):
        self.brain.close()

    def add(self, tid, folder, status, refs, priority="normal", due="null", review="null", waiting="null",
            updated="2026-01-02T09:00:00+10:00"):
        text = TASK.format(id=tid, title="Fictional task " + tid[-4:], status=status, priority=priority,
                           updated=updated, due=due, review=review, waiting=waiting,
                           refs="".join("\n  - " + r for r in refs) if refs else " []")
        (self.brain.memory / "tasks" / folder / (tid + "-fictional.md")).write_text(text, encoding="utf-8")

    def test_the_memory_skeleton_config_draws_the_personal_board_from_the_first_task(self):
        skeleton = (SCRIPTS.parents[3] / "shared" / "templates" / "memory-skeleton" / "skills" / "owner-board"
                    / "config" / "boards.json")
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        shutil.copyfile(skeleton, path)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["boards"], [])
        _, out = quiet(task_board.main, ["--root", str(self.brain.root), "--no-fetch", "build",
                                         "--for", "TASK-2026-0910"])
        self.assertIn("is on Personal tasks", out)
        self.assertTrue((self.brain.memory / "boards" / "personal.html").is_file())
        self.assertTrue((self.brain.memory / "boards" / "index.html").is_file())

    def set_tasks(self, **values):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("tasks", {}).update(values)
        path.write_text(json.dumps(data), encoding="utf-8")

    def placed(self, config=None):
        routed = task_board.route(config or self.brain.config(), today=TODAY)
        return {key: sorted(t.tid for t, _ in b["tasks"]) for key, b in routed.items()}

    def build_all(self):
        config = self.brain.config()
        for board in config.boards:
            quiet(build_status.build, config, board, False)
        quiet(build_boards.build, config, None, "2026-01-10 09:00")
        return config

    def test_routing_takes_the_first_reference_that_has_a_board(self):
        placed = self.placed()
        self.assertEqual(placed["garden"], ["TASK-2026-0910", "TASK-2026-0911", "TASK-2026-0912", "TASK-2026-0917"])
        self.assertEqual(placed["pond"], ["TASK-2026-0913", "TASK-2026-0914"])

    def test_tasks_without_a_board_fall_back_to_the_personal_board(self):
        placed = self.placed()
        # No references (0901, 0916) or only a project without a board (0915).
        self.assertEqual(placed["personal"], ["TASK-2026-0901", "TASK-2026-0915", "TASK-2026-0916"])

    def test_auto_boards_give_a_project_without_a_board_its_own_page(self):
        self.set_tasks(auto_boards=True)
        placed = self.placed()
        # The first reference of 0913 now has a board of its own, so it decides.
        self.assertEqual(placed["auto:example-shed"], ["TASK-2026-0913", "TASK-2026-0915"])
        self.assertEqual(placed["pond"], ["TASK-2026-0914"])
        config = self.build_all()
        self.assertTrue((self.brain.memory / "boards" / "projects" / "example-shed.html").is_file())
        self.assertEqual(task_board.check(config, TODAY), [])

    def test_every_open_task_appears_exactly_once_on_its_board(self):
        config = self.build_all()
        self.assertEqual(task_board.check(config, TODAY), [])
        pages = {"garden": self.brain.memory / "projects/example-garden/status/status.html",
                 "pond": self.brain.memory / "projects/example-pond/status/status.html",
                 "personal": self.brain.memory / "boards" / "personal.html"}
        seen = [tid for page in pages.values() for tid, _ in task_board.shown_on(page)]
        self.assertEqual(len(seen), len(set(seen)))
        self.assertIn("TASK-2026-0917", seen)       # completed nine days ago: recent
        self.assertNotIn("TASK-2026-0918", seen)    # completed in November: not recent
        # A duplicated task is caught by the check.
        page = pages["pond"]
        page.write_text(page.read_text(encoding="utf-8").replace(
            "</section>", '<article class="task" data-task="TASK-2026-0910"></article></section>'), encoding="utf-8")
        self.assertTrue(any("TASK-2026-0910" in p for p in task_board.check(config, TODAY)))

    def test_task_cards_link_to_the_record_and_carry_no_verdict(self):
        self.build_all()
        text = (self.brain.memory / "projects/example-pond/status/status.html").read_text(encoding="utf-8")
        section = text[text.index('<section class="tasks"'):text.index("</section>")]
        self.assertIn('href="../../../tasks/open/TASK-2026-0913-fictional.md"', section)
        self.assertIn("Waiting on: Example Pumps Pty Ltd", section)
        self.assertNotIn("<input", section)
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="personal.html">Personal tasks</a>', index)
        self.assertIn("<b>3</b>Open tasks", index)   # garden: 0910, 0911, 0912

    def test_column_order_is_deliberate(self):
        routed = task_board.route(self.brain.config(), today=TODAY)
        garden = task_board.section(routed["garden"], self.brain.memory, TODAY)
        ready = garden[garden.index('data-column="ready"'):garden.index('data-column="in_progress"')]
        # Priority first, then the nearer deadline: 0912 (high, 15 Jan), 0911 (high, 1 Feb), 0910 (low).
        order = re.findall(r'data-task="(TASK-\d{4}-\d{4})"', ready)
        self.assertEqual(order, ["TASK-2026-0912", "TASK-2026-0911", "TASK-2026-0910"])
        pond = task_board.section(routed["pond"], self.brain.memory, TODAY)
        waiting = re.findall(r'data-task="(TASK-\d{4}-\d{4})"', pond)
        self.assertEqual(waiting, ["TASK-2026-0914", "TASK-2026-0913"])   # nearest review first
        self.assertIn("review due", pond)                                  # 0914's review has come
        columns = re.findall(r'data-column="([a-z_]+)"', garden)
        self.assertEqual(columns, ["inbox", "ready", "in_progress", "waiting", "scheduled", "blocked", "completed"])

    def test_a_new_task_appears_on_its_board_at_once(self):
        sys.path.insert(0, str(SCRIPTS.parents[1] / "tasks" / "scripts"))
        import tasks as task_cli
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = task_cli.main(["--tasks", str(self.brain.memory / "tasks"), "new", "--title", "Mulch the pond edge",
                                  "--status", "ready", "--priority", "high", "--project", "/memory/projects/example-pond",
                                  "--now", "2026-01-10T09:00:00+10:00"], cwd=self.brain.root)
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("TASK-2026-0919 is on Pond Pump", out.getvalue())
        record = self.brain.memory / "tasks" / "open" / "TASK-2026-0919-mulch-the-pond-edge.md"
        self.assertTrue(record.is_file())
        self.assertIn("| `TASK-2026-0919` | **ready** | high | - | Mulch the pond edge |",
                      (self.brain.memory / "tasks" / "STATE.md").read_text(encoding="utf-8"))
        page = self.brain.memory / "projects/example-pond/status/status.html"
        self.assertIn(("TASK-2026-0919", "ready"), task_board.shown_on(page))


class FaviconTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()

    def tearDown(self):
        self.brain.close()

    def pages(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"))
        return [(self.brain.memory / p).read_text(encoding="utf-8") for p in
                ("boards/index.html", "boards/personal.html", "projects/example-garden/status/status.html")]

    def test_every_page_carries_the_default_icon(self):
        for text in self.pages():
            head = text[:text.index("</head>")]
            self.assertIn('<link rel="icon" href="data:image/svg+xml,', head)

    def test_the_owner_icon_overrides_the_default(self):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["directory"] = {"favicon": '<svg xmlns="http://www.w3.org/2000/svg"><circle r="9" fill="#123456"/></svg>'}
        (self.brain.memory / "boards").mkdir(exist_ok=True)
        (self.brain.memory / "boards" / "garden.svg").write_text('<svg><rect fill="#abcdef"/></svg>', encoding="utf-8")
        data["boards"][0]["favicon"] = "garden.svg"
        path.write_text(json.dumps(data), encoding="utf-8")
        index, personal, garden = self.pages()
        self.assertIn("%23123456", index)
        self.assertIn("%23123456", personal)
        self.assertIn("%23abcdef", garden)
        data["boards"][0]["favicon"] = "missing.svg"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(board_config.ConfigError):
            board_config.favicon_link(self.brain.config(), self.brain.board())


if __name__ == "__main__":
    unittest.main()
