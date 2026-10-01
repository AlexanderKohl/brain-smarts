"""Behavioural tests for the owner-board scripts, on a fictional brain built in a temporary folder.

Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

Every name, product and identifier here is invented (SMART-RULE-0008).
"""

from __future__ import annotations

import base64
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
BRAIN = SCRIPTS.parents[3]  # the brain root: owner-board is a core skill beside tasks
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
from board_fixtures import HAS_GIT, BOARD_MD, CARD, git, Brain, quiet  # noqa: E402

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

    def test_verdicts_are_saved_as_a_download_and_the_page_says_where(self):
        config = self.brain.config()
        quiet(build_status.build, config, config.board("garden"))
        text, page, _ = self.page_data(self.brain.memory / "projects/example-garden/status/status.html")
        # One path: a download, found anywhere inside Downloads. The remembered folder was removed.
        self.assertIn("a.download = name", text)
        self.assertIn('id="savenote"', text)
        self.assertNotIn("showDirectoryPicker", text)
        self.assertNotIn("inbox", page)

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
        self.assertEqual([p["label"] for p in config.pages], ["Contacts"])   # an entry without a page is left out
        quiet(build_boards.build, config, None, "2026-01-05 09:00")
        text = (self.brain.memory / "boards" / "index.html").read_text(encoding="utf-8")
        self.assertIn('<h2><a href="contacts.html">Contacts</a></h2><p class="blurb">Everyone, searchable.</p>', text)
        self.assertLess(text.index("contacts.html"), text.index("example-garden/status/status.html"))


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

    def test_screenshots_sent_back_are_kept_beside_the_card_and_shown(self):
        png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode("ascii")
        path = self.save(self.garden, [{"id": "seed-list", "verdict": "rework", "why": "see the picture",
                                        "shots": [png, "data:text/html;base64,PHA+"]}], "s")
        verdicts.apply(self.garden, str(path))
        seed = next(c for c in cards.load(self.garden)["items"] if c["id"] == "seed-list")
        # Only the image is kept; the owner's words stay exactly as written.
        self.assertEqual(seed["sent_back"], "see the picture")
        self.assertEqual(len(seed["sent_back_images"]), 1)
        rel = seed["sent_back_images"][0]
        self.assertTrue(rel.startswith("img/seed-list-") and rel.endswith(".png"))
        self.assertTrue((self.garden["folder"] / rel).exists())
        quiet(build_status.build, self.config, self.garden)
        page = (self.garden["folder"] / "status.html").read_text(encoding="utf-8")
        self.assertIn(png.split(",")[1], page)

    def test_a_verdict_saved_in_a_folder_inside_downloads_is_found(self):
        downloads = self.brain.root / "fake-downloads"
        (downloads / "Some Folder").mkdir(parents=True)
        body = {"schema": self.garden["verdict_schema"], "board": "garden", "verdicts": []}
        (downloads / "Some Folder" / (self.garden["verdict_prefix"] + "x.json")).write_text(json.dumps(body), encoding="utf-8")
        with mock.patch.object(verdicts, "downloads", return_value=str(downloads)):
            found = apply_verdicts.candidates(self.config)
        self.assertEqual([Path(f).parent.name for f in found], ["Some Folder"])

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

    @unittest.skipUnless(HAS_GIT, "git is not installed")
    def test_the_checkout_on_the_local_main_branch_is_not_a_stray_worktree(self):
        # main named as a remote branch ("origin/main"), the repository checked out on main.
        brain = Brain(with_repo=True)
        try:
            board = brain.board()
            board["fetch"] = False
            board["main"] = "origin/main"
            said = reconcile.check(board)
            self.assertFalse(any(s.startswith("main is merged but its worktree") for s in said), said)
            self.assertFalse(any("a worktree is building main " in s for s in said), said)
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
