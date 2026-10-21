"""Behavioural tests for the owner-board scripts, on a fictional brain built in a temporary folder.

Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

Every name, product and identifier here is invented (SMART-RULE-0008). The peer-board
behaviour (two authors, conflicts, stale pages, releases, migration) is in test_peer_boards.py.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import re
import sys
import unittest
from unittest import mock
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import apply_events  # noqa: E402
import board_config  # noqa: E402
import build_boards  # noqa: E402
import build_status  # noqa: E402
import card as card_cli  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402
import reconcile  # noqa: E402
from board_fixtures import HAS_GIT, SOIL, SEED, FROST, git, Brain, event_files, quiet, save_verdicts  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(with_repo=False)

    def tearDown(self):
        self.brain.close()

    def test_brain_root_found_from_a_nested_folder(self):
        nested = self.brain.memory / "projects" / "example-garden" / "status" / "cards"
        self.assertEqual(board_config.find_brain_root(nested), self.brain.root.resolve())

    def test_board_defaults_author_and_owner_name_come_from_the_profile(self):
        board = self.brain.board()
        self.assertEqual((board["owner"], board["author"]), ("Sam", "sam"))
        self.assertEqual(board["title"], "Garden Planner: where we are")
        self.assertEqual(board["verdict_prefix"], "garden-verdicts-")
        self.assertEqual(board["node"], "/memory/projects/example-garden")
        self.assertFalse(board["shared"])
        self.assertEqual(board["release_notes"], [])

    def test_a_repository_status_resolves_under_the_project_repos_root(self):
        shared = Brain(shared=True)
        try:
            board = shared.board()
            self.assertTrue(board["shared"])
            self.assertEqual(board["folder"], shared.repos / "example-garden" / "brain" / "status")
            self.assertEqual(board["card_parent"], "example-garden:brain")
            self.assertEqual(board["node"], "/memory/projects/example-garden")   # the pointer node, for tasks
        finally:
            shared.close()

    def test_board_is_inferred_from_the_current_folder(self):
        config = self.brain.config()
        folder = self.brain.memory / "projects" / "example-garden" / "status" / "cards"
        self.assertEqual(config.board(cwd=folder)["id"], "garden")

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
        original = next(c for c in data["items"] if c["id"] == SOIL)
        original["sent_back"] = "the depth is in inches, I want centimetres"
        cards.write(self.board, original)
        text = (self.board["folder"] / "cards" / (SOIL + ".md")).read_text(encoding="utf-8")
        self.assertRegex(text, r"\nwhere_href: ?\n")
        self.assertNotIn("[]", text)
        self.assertIn("## Sam sent it back", text)
        self.assertIn("\nauthor: sam\n", text)
        again = next(c for c in cards.load(self.board)["items"] if c["id"] == SOIL)
        for key in ("title", "state", "version", "track", "landed", "review", "sent_back", "where", "area", "author"):
            self.assertEqual(again[key], original[key], key)

    def test_unreadable_card_raises_rather_than_vanishing(self):
        (self.board["folder"] / "cards" / "broken.md").write_text("no front matter", encoding="utf-8")
        with self.assertRaises(ValueError):
            cards.load(self.board)

    def test_a_board_still_on_board_md_is_told_to_migrate(self):
        (self.board["folder"] / "board.json").rename(self.board["folder"] / "board.md")
        with self.assertRaisesRegex(ValueError, "migrate_board.py --board garden"):
            cards.load(self.board)

    def test_card_cli_names_a_new_card_by_author_and_time_and_merges_it(self):
        root = ["--root", str(self.brain.root), "--board", "garden"]
        with mock.patch.object(events, "utc", return_value=events.utc("2026-02-01T00:00:00Z")):
            _, out = quiet(card_cli.main, root + ["new", "--track", "beds", "--branch", "fix/compost",
                                                  "--title", "where does the compost go", "--note", "compost"])
        self.assertIn("sam-20260201T000000Z.md", out)
        quiet(card_cli.main, root + ["set", "sam-20260201T000000Z", "--state", "needs_review", "--version", "1.3.0",
                                     "--branch", "-"])
        found = next(c for c in cards.load(self.board)["items"] if c["id"] == "sam-20260201T000000Z")
        self.assertEqual((found["state"], found["version"], found["branch"]), ("needs_review", "1.3.0", None))
        self.assertEqual((found["title"], found["release_note"], found["author"]), ("where does the compost go", "compost", "sam"))

    def test_another_authors_card_is_not_edited_or_dropped_here(self):
        bob = dict(self.board, author="bob")
        with mock.patch.object(board_config.Config, "board", return_value=bob):
            with self.assertRaisesRegex(SystemExit, "its author"):
                quiet(card_cli.main, ["--root", str(self.brain.root), "set", SOIL, "--version", "9.9.9"])
            with self.assertRaisesRegex(SystemExit, "its author"):
                quiet(card_cli.main, ["--root", str(self.brain.root), "drop", SOIL])
        self.assertTrue((self.board["folder"] / "cards" / (SOIL + ".md")).exists())


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

    def test_status_page_carries_owner_labels_links_author_and_seen_through(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"))
        text, page, data = self.page_data(self.brain.memory / "projects/example-garden/status/status.html")
        self.assertIn("<title>Garden Planner: where we are</title>", text)
        self.assertEqual(page["labels"]["needsReview"], "Needs Sam's review")
        self.assertEqual(page["author"], "sam")
        self.assertEqual(page["seenThrough"]["lastEvent"], "sam-20260104T090000Z")
        soil = next(i for i in data["items"] if i["id"] == SOIL)
        self.assertEqual(soil["where"]["href"], "example-app://exampleappid/index.html#beds")
        self.assertEqual(soil["last_event"], "")
        self.assertEqual(data["closed"], {"1.0.0": "first release"})
        self.assertNotIn("__", re.sub(r"__[a-z]", "", text).split("<script>")[0])
        state = json.loads((self.brain.memory / "projects/example-garden/status/state.json").read_text(encoding="utf-8"))
        self.assertEqual([i["id"] for i in state["items"]], [SOIL, SEED, FROST])

    def test_verdicts_are_saved_as_a_download_and_carry_seen_through(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"))
        text, page, _ = self.page_data(self.brain.memory / "projects/example-garden/status/status.html")
        self.assertIn("a.download = name", text)
        self.assertIn("seen_through: item.last_event", text)
        self.assertIn("Accept all released", text)
        self.assertNotIn("showDirectoryPicker", text)

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

    def test_directory_links_other_pages_after_the_personal_board(self):
        path = self.brain.memory / "skills" / "owner-board" / "config" / "boards.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["pages"] = [{"label": "Contacts", "page": "contacts.html", "blurb": "Everyone, searchable."},
                        {"label": "No page"}]
        path.write_text(json.dumps(raw), encoding="utf-8")
        config = self.brain.config()
        self.assertEqual([p["label"] for p in config.pages], ["Contacts"])
        quiet(build_boards.build, config, None, "2026-01-05 09:00")
        text = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<h2><a href="contacts.html">Contacts</a></h2><p class="blurb">Everyone, searchable.</p>', text)
        self.assertLess(text.index("contacts.html"), text.index("example-garden/status/status.html"))


class EventTests(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(second_board=True)
        self.config = self.brain.config()
        self.garden = self.config.board("garden")
        self.inbox = self.brain.root / "saved"

    def tearDown(self):
        self.brain.close()

    def test_accept_retires_and_reject_keeps_the_owner_words(self):
        path = save_verdicts(self.garden, [{"id": SOIL, "verdict": "accepted"},
                                           {"id": SEED, "verdict": "rework", "why": "sort by sowing month"}], self.inbox, "a")
        applied, skipped, _ = apply_events.apply_file(self.config, self.garden, str(path))
        self.assertEqual((len(applied), skipped), (2, []))
        self.assertEqual(event_files(self.garden), sorted(["sam-20260104T090000Z.json", "sam-20260110T100000Z.json", "sam-20260110T100000Z-2.json"]))
        lines, _ = quiet(apply_events.settle, self.garden)
        self.assertTrue((self.garden["folder"] / "cards" / "closed" / (SOIL + ".md")).exists())
        self.assertFalse((self.garden["folder"] / "cards" / (SOIL + ".md")).exists())
        state = events.state(self.garden)
        self.assertEqual(state["closed"], {"1.0.0": "first release", "1.1.0": "show me the soil depth"})
        seed = next(c for c in state["items"] if c["id"] == SEED)
        self.assertEqual((seed["state"], seed["sent_back"]), ("rework", "sort by sowing month"))
        self.assertIn("## Sam sent it back", (self.garden["folder"] / "cards" / (SEED + ".md")).read_text(encoding="utf-8"))
        self.assertFalse(path.exists())   # filed in this brain's own memory
        self.assertTrue((self.brain.memory / "skills" / "owner-board" / "applied" / path.name).exists())
        self.assertEqual(quiet(apply_events.settle, self.garden)[0], [])   # settling again changes nothing

    def test_screenshots_sent_back_are_kept_beside_the_card_named_by_the_event(self):
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
        path = save_verdicts(self.garden, [{"id": SEED, "verdict": "rework", "why": "see the picture",
                                            "shots": [png, "data:text/html;base64,PHA+"]}], self.inbox, "s")
        apply_events.apply_file(self.config, self.garden, str(path))
        quiet(apply_events.settle, self.garden)
        seed = next(c for c in cards.load(self.garden)["items"] if c["id"] == SEED)
        self.assertEqual(seed["sent_back"], "see the picture")
        self.assertEqual(seed["sent_back_images"], ["img/sam-20260110T100000Z-1.png"])
        self.assertTrue((self.garden["folder"] / "img" / "sam-20260110T100000Z-1.png").exists())
        quiet(build_status.build, self.config, self.garden)
        page = (self.garden["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn(png.split(",")[1], page)

    def test_a_verdict_saved_in_a_folder_inside_downloads_is_found(self):
        downloads = self.brain.root / "fake-downloads"
        save_verdicts(self.garden, [], downloads / "Some Folder", "x")
        with mock.patch.object(apply_events, "downloads", return_value=str(downloads)):
            found = apply_events.candidates(self.config)
        self.assertEqual([Path(f).parent.name for f in found], ["Some Folder"])

    def test_a_verdict_on_a_changed_card_is_refused(self):
        path = save_verdicts(self.garden, [{"id": SOIL, "verdict": "accepted", "sig": "000000000000"}], self.inbox, "b")
        applied, skipped, _ = apply_events.apply_file(self.config, self.garden, str(path), dry_run=True)
        self.assertEqual(applied, [])
        self.assertIn("changed after the verdict", skipped[0])

    def test_a_file_from_another_board_is_refused(self):
        path = save_verdicts(self.garden, [{"id": SOIL, "verdict": "accepted"}], self.inbox, "c", board_id="pond")
        with self.assertRaises(apply_events.Refused):
            apply_events.apply_file(self.config, self.garden, str(path))

    def test_router_sends_each_file_to_the_board_it_names(self):
        pond = self.config.board("pond")
        save_verdicts(self.garden, [{"id": FROST, "verdict": "rework", "why": "garden"}], self.inbox, "d")
        save_verdicts(pond, [{"id": FROST, "verdict": "rework", "why": "pond"}], self.inbox, "e")
        with mock.patch.object(apply_events, "downloads", return_value=str(self.brain.root / "none")):
            changed, _ = quiet(apply_events.route, self.config, False, [str(self.inbox)])
        self.assertEqual(sorted(changed), ["garden", "pond"])
        for board, why in ((self.garden, "garden"), (pond, "pond")):
            frost = next(c for c in events.state(board)["items"] if c["id"] == FROST)
            self.assertEqual(frost["sent_back"], why)

    def test_dry_run_changes_nothing(self):
        path = save_verdicts(self.garden, [{"id": SOIL, "verdict": "accepted"}], self.inbox, "f")
        before = event_files(self.garden)
        applied, _, _ = apply_events.apply_file(self.config, self.garden, str(path), dry_run=True)
        self.assertEqual(len(applied), 1)
        self.assertTrue(path.exists())
        self.assertEqual(event_files(self.garden), before)


class ReconcileTests(unittest.TestCase):
    def test_task_checks_run_without_a_repository(self):
        brain = Brain()
        try:
            said = reconcile.check(brain.board())
            self.assertIn("TASK-2026-0901 still says ready, but the beds track has landed work or has a card in flight.", said)
            self.assertIn("TASK-2026-0902 is the task for the seeds track and has no record in /memory/tasks/open.", said)
        finally:
            brain.close()

    def test_a_derived_key_kept_in_board_json_is_reported(self):
        brain = Brain()
        try:
            board = brain.board()
            data = cards.read_board(board)
            data["closed"] = {"1.0.0": "kept by hand"}
            cards.write_board(board, data)
            self.assertIn("board.json still carries closed; it is derived on every build - remove the key.", reconcile.check(board))
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
            self.assertIn(SEED + " says it is being built, but feature/seed-list has no worktree and is not on origin - nobody is building it.", said)
            self.assertFalse(any("mainVersion" in s for s in said), said)
        finally:
            brain.close()

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_the_page_shows_gits_version(self):
        brain = Brain(with_repo=True)
        try:
            board = brain.board()
            board["fetch"] = False
            self.assertEqual(reconcile.repo_version(board), "1.2.0")
            built, _ = quiet(build_status.build, brain.config(), board)
            self.assertEqual(built["mainVersion"], "1.2.0")
        finally:
            brain.close()

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_the_production_branch_is_never_a_stray(self):
        brain = Brain(with_repo=True)
        try:
            board = brain.board()
            board["fetch"] = False
            board["production"] = "origin/fix/orphan"
            said = reconcile.check(board)
            self.assertFalse(any("fix/orphan" in s for s in said), said)
        finally:
            brain.close()

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_a_merge_that_names_an_existing_task_counts_as_seen(self):
        brain = Brain(with_repo=True)
        try:
            completed = brain.memory / "tasks" / "completed"
            completed.mkdir()
            (completed / "TASK-2026-0903-paths.md").write_text("---\nid: TASK-2026-0903\nstatus: completed\n---\n", encoding="utf-8")
            for version, task in (("1.3.0", "TASK-2026-0901"), ("1.4.0", "TASK-2026-0903"), ("1.5.0", "TASK-2026-0999")):
                git(brain.repo, "checkout", "-q", "-b", "release/" + version)
                (brain.repo / "package.json").write_text('{"version": "%s"}' % version, encoding="utf-8")
                git(brain.repo, "commit", "-q", "-am", "bump")
                git(brain.repo, "checkout", "-q", "main")
                git(brain.repo, "merge", "-q", "--no-ff", "-m", "Merge %s: paths (%s)" % (version, task), "release/" + version)
            board = brain.board()
            board["fetch"] = False
            said = reconcile.check(board)
            self.assertIn("1.2.0 is merged into main and has no card - the owner has not seen it.", said)
            self.assertFalse(any(s.startswith("1.3.0 ") for s in said), said)
            self.assertFalse(any(s.startswith("1.4.0 ") for s in said), said)
            self.assertIn("1.5.0 is merged into main and has no card - the owner has not seen it.", said)
        finally:
            brain.close()

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_abandoned_silences_a_branch_as_a_mapping_or_a_list(self):
        brain = Brain(with_repo=True)
        try:
            board = brain.board()
            board["fetch"] = False
            reason = "Sam, 5 Jan 2026: abandoned until Pat confirms"
            for form in ({"fix/orphan": reason}, ["fix/orphan: " + reason], [{"branch": "fix/orphan", "reason": reason}]):
                data = events.state(board)
                data["abandoned"] = form
                said = reconcile.check(board, data)
                self.assertFalse(any("fix/orphan" in s for s in said), (form, said))
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
