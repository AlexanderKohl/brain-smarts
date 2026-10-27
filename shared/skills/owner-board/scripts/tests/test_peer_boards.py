"""Two brains on one board: ids, the fold, conflicts, stale pages, releases and the migration.

Fictional authors `sam` (this brain) and `bob` (the other brain, which writes under its own
author into the same folder). Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v
"""

from __future__ import annotations

import itertools
import json
import shutil
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BRAIN = SCRIPTS.parents[3]
sys.path.insert(0, str(SCRIPTS))

import apply_events  # noqa: E402
import build_boards  # noqa: E402
import board_config  # noqa: E402
import build_status  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402
import migrate_board  # noqa: E402
import task_board  # noqa: E402
from board_fixtures import SOIL, SEED, FROST, Brain, event_files, quiet, save_verdicts  # noqa: E402


def decide(board: dict, who: str, card: str, kind: str, at: str, **fields) -> dict:
    """What the other brain would write: an event under its own author, after the fences."""
    item = next(c for c in events.state(board)["items"] if c["id"] == card)
    event = events.make(board, kind, who, at, card=card, sig=item["sig"], seen_through=item["last_event"], **fields)
    reason = events.check_fences(item, event)
    if reason:
        raise AssertionError(reason)
    events.write(board, event)
    return event


class IdTests(unittest.TestCase):
    def test_two_authors_in_one_second_never_collide_and_one_author_gets_a_suffix(self):
        moment = events.utc("2026-03-01T10:00:00Z")
        taken: set = set()
        for expected in ("sam-20260301T100000Z", "bob-20260301T100000Z", "sam-20260301T100000Z-2", "sam-20260301T100000Z-3"):
            got = events.new_id("Sam" if expected.startswith("sam") else "Bob", moment, taken)
            self.assertEqual(got, expected)
            taken.add(got)
        self.assertEqual(events.parse_id("sam-20260301T100000Z-3"), ("sam", "20260301T100000Z", 3))
        self.assertEqual(events.utc("2026-03-01T20:00:00+10:00").isoformat(), "2026-03-01T10:00:00+00:00")

    def test_an_event_is_never_rewritten(self):
        brain = Brain()
        try:
            board = brain.board()
            event = events.make(board, "defer", "sam", "2026-03-01T10:00:00Z", card=SOIL)
            events.write(board, event)
            with self.assertRaises(FileExistsError):
                events.write(board, event)
        finally:
            brain.close()


class FoldTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.board = self.brain.board()

    def tearDown(self):
        self.brain.close()

    def test_the_fold_gives_one_state_for_every_order_of_the_event_files(self):
        decide(self.board, "sam", SOIL, "accept", "2026-01-10T10:00:00Z")
        sig = next(c for c in cards.load(self.board)["items"] if c["id"] == SOIL)["sig"]
        events.write(self.board, events.make(self.board, "reject", "bob", "2026-01-10T10:00:05Z", card=SOIL, why="no", sig=sig))
        decide(self.board, "sam", FROST, "defer", "2026-01-10T10:00:09Z")
        log = events.read_all(self.board)
        answers = set()
        for order in itertools.permutations(log):
            folded = events.fold(cards.load(self.board)["items"], sorted(order, key=events.order_key))
            answers.add(json.dumps({"closed": folded["closed"], "conflicts": [i["id"] for i in folded["conflicts"]],
                                    "items": [(i["id"], i["state"], i["fold"]) for i in folded["items"]]}, sort_keys=True))
        self.assertEqual(len(answers), 1)

    def test_earliest_wins_and_a_later_different_outcome_marks_a_conflict(self):
        decide(self.board, "bob", SOIL, "reject", "2026-01-10T10:00:00Z", why="inches")
        sig = cards.load(self.board)["items"][0]["sig"]
        events.write(self.board, events.make(self.board, "accept", "sam", "2026-01-10T10:00:30Z", card=SOIL, sig=sig))
        state = events.state(self.board)
        soil = next(i for i in state["items"] if i["id"] == SOIL)
        self.assertEqual((soil["state"], soil["fold"], soil["decided"]["by"], soil["sent_back"]), ("rework", "conflict", "bob", "inches"))
        self.assertEqual([e["by"] for e in soil["conflict"]], ["sam"])
        self.assertEqual(state["retired"], [])
        self.assertEqual(events.conflicting_ids(soil), ["bob-20260110T100000Z", "sam-20260110T100030Z"])

    def test_the_same_outcome_twice_is_no_conflict(self):
        decide(self.board, "sam", SOIL, "accept", "2026-01-10T10:00:00Z")
        sig = cards.load(self.board)["items"][0]["sig"]
        events.write(self.board, events.make(self.board, "accept", "bob", "2026-01-10T10:00:30Z", card=SOIL, sig=sig))
        state = events.state(self.board)
        self.assertEqual(state["conflicts"], [])
        soil = state["retired"][0]
        self.assertEqual((soil["id"], soil["decided"]["by"], soil["also_by"]), (SOIL, "sam", ["bob"]))

    def test_resolve_is_refused_without_both_ids_and_decides_with_them(self):
        decide(self.board, "bob", SOIL, "reject", "2026-01-10T10:00:00Z")
        sig = cards.load(self.board)["items"][0]["sig"]
        events.write(self.board, events.make(self.board, "accept", "sam", "2026-01-10T10:00:30Z", card=SOIL, sig=sig))
        soil = next(i for i in events.state(self.board)["items"] if i["id"] == SOIL)
        half = events.make(self.board, "resolve", "sam", "2026-01-10T11:00:00Z", card=SOIL, outcome="accept",
                           resolves=["sam-20260110T100030Z"], seen_through=soil["last_event"])
        self.assertIn("must name every conflicting event", events.check_fences(soil, half))
        whole = dict(half, resolves=events.conflicting_ids(soil))
        self.assertIsNone(events.check_fences(soil, whole))
        events.write(self.board, whole)
        state = events.state(self.board)
        self.assertEqual(state["conflicts"], [])
        self.assertEqual([i["id"] for i in state["retired"]], [SOIL])
        self.assertIn("1.1.0", state["closed"])

    def test_a_stale_page_and_a_changed_card_are_refused(self):
        decide(self.board, "bob", SOIL, "defer", "2026-01-10T10:00:00Z")
        soil = next(i for i in events.state(self.board)["items"] if i["id"] == SOIL)
        stale = events.make(self.board, "accept", "sam", "2026-01-10T10:01:00Z", card=SOIL, sig=soil["sig"], seen_through="")
        self.assertIn("pull, rebuild, decide again", events.check_fences(soil, stale))
        changed = events.make(self.board, "accept", "sam", "2026-01-10T10:01:00Z", card=SOIL, sig="0" * 12, seen_through=soil["last_event"])
        self.assertIn("changed after the verdict", events.check_fences(soil, changed))
        self.assertIn("no card", events.check_fences(None, stale))

    def test_a_rejected_card_set_building_again_is_no_longer_overlaid(self):
        decide(self.board, "bob", SOIL, "reject", "2026-01-10T10:00:00Z", why="inches")
        fresh = next(c for c in cards.load(self.board)["items"] if c["id"] == SOIL)
        fresh["state"] = "building"
        cards.write(self.board, fresh)
        soil = next(i for i in events.state(self.board)["items"] if i["id"] == SOIL)
        self.assertEqual((soil["state"], soil["decided"]), ("building", None))

    def test_released_events_fold_to_the_released_fold_then_retire(self):
        events.write(self.board, events.make(self.board, "released", "sam", "2026-01-11T09:00:00Z", card=SOIL,
                                             version="1.1.0", env="testing"))
        soil = next(i for i in events.state(self.board)["items"] if i["id"] == SOIL)
        self.assertEqual((soil["fold"], soil["released_to"]), ("released", {"testing": "1.1.0"}))
        events.write(self.board, events.make(self.board, "released", "bob", "2026-01-12T09:00:00Z", card=SOIL,
                                             version="1.1.0", env="production"))
        state = events.state(self.board)
        self.assertEqual([i["id"] for i in state["retired"]], [SOIL])
        self.assertEqual(state["closed"]["1.1.0"], "show me the soil depth")


class TwoBrainsTests(unittest.TestCase):
    """The same folder seen from two brains: the saves, the settle, and what each side moves."""

    def setUp(self):
        self.brain = Brain()
        self.config = self.brain.config()
        self.sam = self.config.board("garden")
        self.bob = dict(self.sam, author="bob", owner="Bob")
        self.saved = self.brain.root / "saved"

    def tearDown(self):
        self.brain.close()

    def test_bob_accepts_then_sam_disagrees_and_both_see_the_conflict_until_sam_resolves(self):
        apply_events.apply_file(self.config, self.bob, str(save_verdicts(self.bob, [{"id": SOIL, "verdict": "accepted"}], self.saved, "b")))
        # Sam's page was built before Bob's event arrived: refused with the pull hint.
        stale = save_verdicts(self.sam, [{"id": SOIL, "verdict": "rework", "why": "cm", "seen_through": ""}], self.saved, "s1")
        applied, skipped, _ = apply_events.apply_file(self.config, self.sam, str(stale))
        self.assertEqual(applied, [])
        self.assertIn("pull, rebuild, decide again", skipped[0])
        # After the pull Sam decides again; both are kept and the card is in conflict on both sides.
        apply_events.apply_file(self.config, self.sam, str(save_verdicts(self.sam, [{"id": SOIL, "verdict": "rework", "why": "cm"}], self.saved, "s2")))
        for board in (self.sam, self.bob):
            soil = next(i for i in events.state(board)["items"] if i["id"] == SOIL)
            self.assertEqual((soil["fold"], soil["decided"]["by"], soil["conflict"][0]["by"]), ("conflict", "bob", "sam"))
        self.assertEqual(quiet(apply_events.settle, self.bob)[0], [])   # nothing moves while in conflict
        ids = events.conflicting_ids(soil)
        apply_events.apply_file(self.config, self.sam, str(save_verdicts(
            self.sam, [{"id": SOIL, "verdict": "resolve", "outcome": "accepted", "resolves": ids}], self.saved, "s3")))
        self.assertEqual(events.state(self.sam)["conflicts"], [])
        # Bob's accept retired it; Bob's brain moves the file, Sam's leaves it for the pull.
        self.assertEqual(quiet(apply_events.settle, self.sam)[0], [])
        self.assertEqual(quiet(apply_events.settle, self.bob)[0], ["moved " + SOIL + " to cards/closed/"])
        self.assertTrue((self.sam["folder"] / "cards" / "closed" / (SOIL + ".md")).exists())
        self.assertEqual(quiet(apply_events.settle, self.bob)[0], [])   # already in cards/closed/: left alone

    def test_bob_sends_sams_card_back_and_only_sam_writes_the_words_into_it(self):
        apply_events.apply_file(self.config, self.bob, str(save_verdicts(self.bob, [{"id": SOIL, "verdict": "rework", "why": "inches"}], self.saved, "b")))
        self.assertEqual(quiet(apply_events.settle, self.bob)[0], [])
        self.assertNotIn("sent it back", (self.sam["folder"] / "cards" / (SOIL + ".md")).read_text(encoding="utf-8"))
        soil = next(i for i in events.state(self.bob)["items"] if i["id"] == SOIL)
        self.assertEqual((soil["state"], soil["sent_back"]), ("rework", "inches"))   # overlaid meanwhile
        self.assertEqual(quiet(apply_events.settle, self.sam)[0], ["wrote the words of bob into " + SOIL])
        text = (self.sam["folder"] / "cards" / (SOIL + ".md")).read_text(encoding="utf-8")
        self.assertIn("state: rework", text)
        self.assertIn("inches", text)

    def test_the_page_draws_both_verdicts_and_the_resolve_control(self):
        apply_events.apply_file(self.config, self.bob, str(save_verdicts(self.bob, [{"id": SOIL, "verdict": "accepted"}], self.saved, "b")))
        apply_events.apply_file(self.config, self.sam, str(save_verdicts(self.sam, [{"id": SOIL, "verdict": "rework", "why": "cm"}], self.saved, "s")))
        data, _ = quiet(build_status.build, self.config, self.sam)
        page = (self.sam["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn('"fold": "conflict"', page)
        self.assertIn('"by": "bob"', page)
        self.assertIn("Resolve: ", page)
        self.assertNotIn('"events":', page)   # the whole log stays out of the page
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn("<b>1</b>In conflict", index)


class RepositoryBoardTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(shared=True)
        self.config = self.brain.config()
        self.board = self.config.board("garden")

    def tearDown(self):
        self.brain.close()

    def test_a_repository_page_draws_the_repository_tasks_and_no_memory_path(self):
        quiet(build_status.build, self.config, self.board)
        page = (self.board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertNotIn("/memory/", page)
        self.assertIn(("TASK-2026-0901", "ready"), task_board.shown_on(self.board["folder"] / "status.html"))
        self.assertTrue((self.board["folder"] / "state.json").exists())
        routed = task_board.route(self.config)
        self.assertEqual(routed["garden"]["page"], self.board["folder"] / "status.html")
        # The owner's private tasks about the project have a page of their own in memory.
        own = routed[task_board.OWN + "garden"]
        self.assertEqual(own["page"], self.brain.memory / "boards" / "projects" / "garden.html")
        self.assertTrue(own["page"].exists())
        self.assertTrue(all(migrate_board.check_no_memory_paths(self.board["folder"]) == [] for _ in [0]))
        index = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="projects/garden.html"', index)

    def test_the_build_refuses_a_page_that_would_carry_a_memory_path(self):
        data = cards.read_board(self.board)
        data["elsewhere"] = {"note": "see /memory/projects/example-garden/STATE.md"}
        cards.write_board(self.board, data)
        with self.assertRaises(build_status.Refused):
            quiet(build_status.build, self.config, self.board)
        self.assertFalse((self.board["folder"] / "status.html").exists())

    def test_the_build_refuses_a_repository_board_whose_card_says_memory(self):
        path = sorted((self.board["folder"] / "cards").glob("*.md"))[0]
        path.write_text(path.read_text(encoding="utf-8") + "\nSee /memory/projects/example-garden/STATE.md\n", encoding="utf-8")
        with self.assertRaises(build_status.Refused) as caught:
            quiet(build_status.build, self.config, self.board)
        self.assertIn("cards/" + path.name, str(caught.exception))
        self.assertFalse((self.board["folder"] / "status.html").exists())

    def test_a_new_card_on_a_repository_board_names_the_repository_node(self):
        with mock.patch.object(events, "utc", return_value=events.utc("2026-02-01T00:00:00Z")):
            import card as card_cli
            quiet(card_cli.main, ["--root", str(self.brain.root), "new", "--track", "beds", "--title", "x"])
        text = (self.board["folder"] / "cards" / "sam-20260201T000000Z.md").read_text(encoding="utf-8")
        self.assertIn('parent: "example-garden:brain"', text)
        self.assertRegex(text, r"\ncreated: \"?2026-02-01T\d\d:00:00[+-]\d\d:\d\d\"?\n")   # local time with its offset
        self.assertNotIn("/memory/", text)


class IndexLinkTests(unittest.TestCase):
    """The index links a repository board so the link resolves from the index's own folder,
    both when built in the shared checkout and when built in a session copy of it."""

    def setUp(self):
        import tempfile
        self.brain = Brain(shared=True)
        self.top = Path(tempfile.mkdtemp(prefix="owner-board-repos-"))
        # The brain inside project_repos_root, beside the repository that holds the board.
        shutil.move(str(self.brain.root), str(self.top / "brain"))
        shutil.move(str(self.brain.repos / "example-garden"), str(self.top / "example-garden"))
        self.root = self.top / "brain"
        owner = self.root / "memory" / "OWNER.md"
        owner.write_text(owner.read_text(encoding="utf-8").replace(str(self.brain.repos), str(self.top)), encoding="utf-8")
        (self.top / "example-garden" / "brain" / "status" / "status.html").write_text("<p>board</p>", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self.top, ignore_errors=True)
        shutil.rmtree(self.brain.repos, ignore_errors=True)

    def links(self, root: Path) -> list:
        import re
        out = quiet(build_boards.build, board_config.Config(root))
        page = Path(out[0] if isinstance(out, tuple) else out).read_text(encoding="utf-8")
        return re.findall(r'<a href="([^"]+)"', page)

    def assert_resolve(self, hrefs: list, folder: Path) -> None:
        self.assertTrue(any("example-garden/brain/status/status.html" in h for h in hrefs), hrefs)
        for href in hrefs:
            self.assertTrue((folder / href).resolve().is_file(), href + " does not resolve from " + str(folder))

    def test_every_link_resolves_from_the_shared_checkout(self):
        hrefs = self.links(self.root)
        self.assertIn("../../../example-garden/brain/status/status.html", hrefs)
        self.assert_resolve(hrefs, self.root / "memory" / "boards")

    def test_a_session_copy_links_as_the_shared_checkout_will_open_it(self):
        copy = self.top / "brain-sessions" / "copy"
        copy.parent.mkdir()
        shutil.copytree(str(self.root), str(copy))
        (copy / ".git").write_text("gitdir: " + (self.root / ".git" / "worktrees" / "copy").as_posix() + "\n", encoding="utf-8")
        (copy / "memory" / ".git").write_text(
            "gitdir: " + (self.root / "memory" / ".git" / "worktrees" / "m1").as_posix() + "\n", encoding="utf-8")
        hrefs = self.links(copy)
        external = [h for h in hrefs if "example-garden/brain/status" in h]
        self.assertEqual(external, ["../../../example-garden/brain/status/status.html"])
        # Opened from the shared checkout once merged; the in-brain links resolve in either place.
        (self.root / "memory" / "boards").mkdir(exist_ok=True)
        for href in external:
            self.assertTrue((self.root / "memory" / "boards" / href).resolve().is_file(), href)
        for href in hrefs:
            if href not in external:
                self.assertTrue((copy / "memory" / "boards" / href).resolve().is_file(), href)


class PageSizeTests(unittest.TestCase):
    """A board with many release notes and many loose commits stays small: the option list of
    notes is written once per project, not once per commit."""

    def setUp(self):
        self.brain = Brain()
        boards = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        raw = json.loads(boards.read_text(encoding="utf-8"))
        raw["boards"][0]["release_notes"] = ["garden-app"]
        boards.write_text(json.dumps(raw), encoding="utf-8")

    def tearDown(self):
        self.brain.close()

    def test_the_page_stays_small_with_many_notes_and_loose_commits(self):
        import types
        import page_notes
        notes = [{"slug": "note-%03d" % i, "body": "A fictional change number %d." % i, "conflicts": [],
                  "front": {"title": "Fictional garden change number %d, described at some length" % i,
                            "kind": "changed", "visibility": "undecided"}} for i in range(400)]
        loose = [{"hash": "%08x" % (0xabc000 + i), "author": "Test", "subject": "Fictional commit %d" % i}
                 for i in range(400)]
        project = {"id": "garden-app", "label": "Garden app"}
        fake = types.SimpleNamespace(
            load_config=lambda brain: types.SimpleNamespace(projects={"garden-app": project}),
            collect_unreleased=lambda cfg, p: (notes, [], []),
            collect_loose=lambda cfg, p, n: loose,
            collect_released=lambda cfg, p: {})
        config = self.brain.config()
        board = config.board("garden")
        with mock.patch.object(page_notes, "skill_module", lambda brain: fake):
            quiet(build_status.build, config, board)
        page = (board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn("Fictional commit 399", page)
        self.assertIn('data-project="garden-app">', page)
        self.assertEqual(page.count('value="note-123"'), 1)
        self.assertLess(len(page.encode("utf-8")), 1_000_000)


class MigrationTests(unittest.TestCase):
    OLD_BOARD = """---
id: x
---

# The board

```json
{"id": "garden", "label": "Garden Planner", "generated": "2026-01-05T09:00:00+10:00", "mainVersion": "1.0.0",
 "tracks": {"beds": {"label": "Beds", "task": "TASK-2026-0901", "done": 2, "of": 5}},
 "appId": "exampleappid", "closed": {"1.0.0": "first release", "0.9.0": "beta"}, "abandoned": {}}
```
"""

    def setUp(self):
        self.brain = Brain()
        self.board = self.brain.board()
        folder = self.board["folder"]
        shutil.rmtree(folder / "events")
        (folder / "board.json").unlink()
        (folder / "board.md").write_text(self.OLD_BOARD, encoding="utf-8")
        for name in (SOIL, SEED, FROST):
            (folder / "cards" / (name + ".md")).rename(folder / "cards" / (name.split("-")[1][:8].lower() + "-slug.md"))
        for path in (folder / "cards").glob("*.md"):
            path.write_text(path.read_text(encoding="utf-8").replace("id: sam-", "id: " + path.stem + "\nold: sam-").replace("author: sam\n", ""), encoding="utf-8")
        applied = folder / "verdicts-applied"
        applied.mkdir()
        (applied / "garden-verdicts-garden-2026-01-08-10-00-00.json").write_text(json.dumps({
            "schema": "owner-board/verdicts/v1", "board": "garden", "savedAt": "2026-01-08T10:00:00.000Z",
            "verdicts": [{"id": "20260105-slug", "verdict": "rework", "why": "cm", "sig": "abc"}],
            "tasks": [{"id": "TASK-2026-0901", "action": "done"}]}), encoding="utf-8")

    def tearDown(self):
        self.brain.close()

    def test_dry_run_plans_and_writes_nothing(self):
        _, out = quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden", "--dry-run"])
        self.assertIn("would: card 20260105-slug.md -> cards/sam-20260105T090000Z.md", out)
        self.assertIn("would: event sam-20260108T100000Z reject sam-20260105T090000Z", out)
        self.assertIn("accept 1.0.0", out)
        self.assertIn("task action(s) stay in this memory", out)
        self.assertFalse((self.board["folder"] / "board.json").exists())
        self.assertTrue((self.board["folder"] / "board.md").exists())

    def test_in_place_conversion_derives_the_same_closed_register(self):
        _, out = quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden"])
        folder = self.board["folder"]
        self.assertFalse((folder / "board.md").exists())
        self.assertFalse((folder / "verdicts-applied").exists())
        data = cards.read_board(self.board)
        self.assertEqual(sorted(data), ["abandoned", "appId", "id", "label", "release_notes", "tracks"])
        self.assertEqual(sorted(p.name for p in (folder / "cards").glob("*.md")), [SOIL + ".md", SEED + ".md", FROST + ".md"])
        state = events.state(self.board)
        self.assertEqual(state["closed"], {"0.9.0": "beta", "1.0.0": "first release"})
        # The migrated verdict keeps the signature it was given against; the card has moved on
        # since (its effect was applied at the time), so it is a record, not an overlay.
        soil = next(i for i in state["items"] if i["id"] == SOIL)
        self.assertEqual((soil["state"], soil["decided"]), ("needs_review", None))
        migrated = json.loads((folder / "events" / "sam-20260108T100000Z.json").read_text(encoding="utf-8"))
        self.assertEqual((migrated["kind"], migrated["card"], migrated["why"], migrated["sig"]), ("reject", SOIL, "cm", "abc"))
        self.assertTrue(migrated["source"].startswith("migrated from verdicts-applied/"))
        quiet(build_status.build, self.brain.config(), self.board)

    def test_conversion_into_a_repository_folder_ignores_the_generated_files_and_repoints_the_registry(self):
        repo = self.brain.repos / "example-garden"
        (repo / "brain").mkdir(parents=True)
        (repo / ".gitignore").write_text("node_modules/\n", encoding="utf-8")
        _, out = quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden", "--to", "example-garden:brain/status"])
        target = repo / "brain" / "status"
        self.assertTrue((target / "board.json").exists())
        self.assertEqual(len(list((target / "cards").glob("*.md"))), 3)
        self.assertEqual(len(list((target / "events").glob("*.json"))), 3)
        self.assertEqual((repo / ".gitignore").read_text(encoding="utf-8"), "node_modules/\n")   # nothing outside brain/
        self.assertEqual((target / ".gitignore").read_text(encoding="utf-8"), "status.html\nstate.json\n")
        outside = [p.name for p in repo.rglob("*") if p.is_file() and "brain" not in p.relative_to(repo).parts]
        self.assertEqual(outside, [".gitignore"])
        for path in (target / "cards").glob("*.md"):
            self.assertIn('parent: "example-garden:brain"', path.read_text(encoding="utf-8"))
        raw = json.loads((self.brain.memory / "skills" / "owner-board" / "config" / "boards.json").read_text(encoding="utf-8"))
        self.assertEqual(raw["boards"][0]["status"], "example-garden:brain/status")
        self.assertEqual(raw["boards"][0]["node"], "/memory/projects/example-garden")
        self.assertIn("git mv", out)
        self.assertNotIn("WARNING", out)
        self.assertEqual(migrate_board.check_no_memory_paths(target), [])
        board = self.brain.board()
        self.assertTrue(board["shared"])
        self.assertTrue((self.board["folder"] / "board.md").exists())   # the old folder is the conductor's to move
        quiet(build_status.build, self.brain.config(), board)

    def test_a_board_converted_in_place_moves_with_its_events(self):
        quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden"])
        source = self.board["folder"]
        held = sorted(p.name for p in (source / "events").glob("*.json"))
        repo = self.brain.repos / "example-garden"
        (repo / "brain").mkdir(parents=True)
        _, dry = quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden",
                                            "--to", "example-garden:brain/status", "--dry-run"])
        self.assertIn("would: copy event " + held[0], dry)
        self.assertFalse((repo / "brain" / "status").exists())
        _, out = quiet(migrate_board.main, ["--root", str(self.brain.root), "--board", "garden", "--to", "example-garden:brain/status"])
        target = repo / "brain" / "status"
        self.assertEqual(sorted(p.name for p in (target / "events").glob("*.json")), held)
        for name in held:
            self.assertEqual((target / "events" / name).read_bytes(), (source / "events" / name).read_bytes())
        self.assertEqual(events.state(self.brain.board())["closed"], {"0.9.0": "beta", "1.0.0": "first release"})
        self.assertNotIn("WARNING", out)
        self.assertFalse((repo / ".gitignore").exists())

    def test_a_target_outside_the_repository_brain_is_refused(self):
        with self.assertRaises(Exception):
            migrate_board.main(["--root", str(self.brain.root), "--board", "garden", "--to", "example-garden:docs/status"])
        self.assertFalse((self.brain.repos / "example-garden" / "docs").exists())


class ReleaseNotesSectionTests(unittest.TestCase):
    """A board that names a release-notes project draws the section from the release-notes skill."""

    def setUp(self):
        self.brain = Brain()
        library = BRAIN / "shared" / "skills" / "release-notes" / "scripts"
        if not library.is_dir():
            self.skipTest("the release-notes skill is not present")
        dest = self.brain.root / "shared" / "skills" / "release-notes" / "scripts"
        dest.mkdir(parents=True)
        for path in library.glob("*.py"):
            shutil.copy(path, dest / path.name)
        (self.brain.root / "shared" / "skills" / "owner-board" / "scripts").mkdir(parents=True)
        for name in ("events.py", "cards.py", "board_config.py"):
            shutil.copy(SCRIPTS / name, self.brain.root / "shared" / "skills" / "owner-board" / "scripts" / name)
        notes = self.brain.memory / "projects" / "example-garden" / "release-notes" / "unreleased"
        notes.mkdir(parents=True)
        (notes / "depth.md").write_text("---\ntitle: Beds show their depth\nkind: added\nvisibility: undecided\n---\n\nYou can see how deep each bed is.\n", encoding="utf-8")
        config = self.brain.memory / "skills" / "release-notes" / "config"
        config.mkdir(parents=True)
        (config / "release-notes.json").write_text(json.dumps({"pages": [], "projects": [
            {"id": "garden-app", "label": "Garden app", "kind": "folder", "folder": "/memory/projects/example-garden/release-notes"}]}),
            encoding="utf-8")
        boards = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        raw = json.loads(boards.read_text(encoding="utf-8"))
        raw["boards"][0]["release_notes"] = ["garden-app"]
        boards.write_text(json.dumps(raw), encoding="utf-8")

    def tearDown(self):
        self.brain.close()

    def test_the_section_is_drawn_and_choices_become_events_through_apply(self):
        config = self.brain.config()
        board = config.board("garden")
        data, _ = quiet(build_status.build, config, board)
        page = (board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn('<section class="notes"', page)
        self.assertIn("Beds show their depth", page)
        self.assertIn("window.BoardNotes", page)
        self.assertIn("Released to testing", page)
        saved = save_verdicts(board, [], self.brain.root / "saved", "n", extra={"releaseNotes": {
            "notes": [{"project": "garden-app", "slug": "depth", "visibility": "announce"}], "commits": []}})
        applied, skipped, _ = apply_events.apply_file(config, board, str(saved))
        self.assertEqual(skipped, [])
        self.assertTrue(any("garden-app/depth visibility" in line for line in applied))
        choices = list((self.brain.memory / "projects" / "example-garden" / "release-notes" / "choices").glob("*.json"))
        self.assertEqual([p.stem for p in choices], ["sam-20260110T100000Z"])
        # Check 11: a card that raised the middle number and names no note is reported.
        self.assertTrue(any("names no release note" in s for s in data["adrift"]), data["adrift"])


class SharedBoardReleaseNotesTests(unittest.TestCase):
    """A second, fictional brain with no release-notes configuration of its own builds a shared
    board: the section is drawn from the repository's brain/status/release-notes.json."""

    def setUp(self):
        self.brain = Brain(shared=True)
        self.library = BRAIN / "shared" / "skills" / "release-notes" / "scripts"
        if not self.library.is_dir():
            self.skipTest("the release-notes skill is not present")
        (self.brain.root / "shared" / "skills" / "owner-board" / "scripts").mkdir(parents=True)
        for name in ("events.py", "cards.py", "board_config.py"):
            shutil.copy(SCRIPTS / name, self.brain.root / "shared" / "skills" / "owner-board" / "scripts" / name)
        self.repo = self.brain.repos / "example-garden"
        notes = self.repo / "release-notes" / "garden" / "unreleased"
        notes.mkdir(parents=True)
        (notes / "frost.md").write_text("---\ntitle: Frost warnings\nkind: added\nvisibility: undecided\n---\n\n"
                                        "Beds warn you before a frost.\n", encoding="utf-8")
        (self.repo / "brain" / "status" / "release-notes.json").write_text(json.dumps({"projects": [
            {"id": "garden-app", "label": "Garden app", "kind": "folder", "folder": "release-notes/garden"}]}),
            encoding="utf-8")
        boards = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        raw = json.loads(boards.read_text(encoding="utf-8"))
        raw["boards"][0]["release_notes"] = ["garden-app"]
        boards.write_text(json.dumps(raw), encoding="utf-8")

    def tearDown(self):
        self.brain.close()

    def copy_library(self):
        dest = self.brain.root / "shared" / "skills" / "release-notes" / "scripts"
        dest.mkdir(parents=True)
        for path in self.library.glob("*.py"):
            shutil.copy(path, dest / path.name)

    def test_the_section_comes_from_the_repository_and_choices_are_written_there(self):
        self.copy_library()
        self.assertFalse((self.brain.memory / "skills" / "release-notes").exists())
        config = self.brain.config()
        board = config.board("garden")
        data, _ = quiet(build_status.build, config, board)
        page = (board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn('<section class="notes"', page)
        self.assertIn("Frost warnings", page)
        self.assertNotIn('class="notes-problem"', page)
        saved = save_verdicts(board, [], self.brain.root / "saved", "n", extra={"releaseNotes": {
            "notes": [{"project": "garden-app", "slug": "frost", "visibility": "announce"}], "commits": []}})
        applied, skipped, _ = apply_events.apply_file(config, board, str(saved))
        self.assertEqual(skipped, [])
        self.assertTrue(any("garden-app/frost visibility" in line for line in applied), applied)
        self.assertEqual(len(list((self.repo / "release-notes" / "garden" / "choices").glob("*.json"))), 1)

    def test_a_missing_skill_or_project_is_a_visible_line_on_the_page(self):
        config = self.brain.config()
        board = config.board("garden")
        data, _ = quiet(build_status.build, config, board)
        page = (board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn('<p class="notes-problem">The board names release-notes projects but the release-notes '
                      'skill is not checked out', page)
        self.assertTrue(any("not checked out" in s for s in data["adrift"]), data["adrift"])
        self.copy_library()
        (self.repo / "brain" / "status" / "release-notes.json").write_text('{"projects": []}', encoding="utf-8")
        data, _ = quiet(build_status.build, config, board)
        page = (board["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn('<p class="notes-problem">release_notes names garden-app, which is not a project', page)


if __name__ == "__main__":
    unittest.main()
