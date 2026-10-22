"""A card's detail shows its fields and links its task, on a memory board and on a repository board.

    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

The page data is checked on every run; the detail is also opened in a headless browser when
Playwright and a Chromium-family browser are installed (skipped otherwise, never failed).
"""

from __future__ import annotations

import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_status  # noqa: E402
import card_detail  # noqa: E402
from board_fixtures import HAS_GIT, SEED, SOIL, Brain, git, quiet  # noqa: E402

CHROME = Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe"


def name_task(board: dict, card_id: str, task_id: str) -> None:
    path = Path(board["folder"]) / "cards" / (card_id + ".md")
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("show me the soil depth", "show me the soil depth (" + task_id + ")"),
                    encoding="utf-8")


def page_items(board: dict) -> dict:
    page = (Path(board["folder"]) / "status.html").read_text(encoding="utf-8")
    found = re.search(r'<script[^>]*id="data"[^>]*>(.*?)</script>', page, re.S)
    return {i["id"]: i for i in json.loads(found.group(1).replace("<\\/", "</"))["items"]}


def open_detail(board: dict, card_id: str):
    """Click the card in a headless browser; the detail's text and its links, or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    url = (Path(board["folder"]) / "status.html").resolve().as_uri()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=str(CHROME)) if CHROME.exists() else p.chromium.launch()
        except Exception:
            return None
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        # The fixture cards share their landed text, so the card is found by its title.
        card = page.locator("div.card", has=page.locator("p.ask", has_text="soil depth")).first
        card.click()
        body = card.locator(".body")
        out = {"display": body.evaluate("e => getComputedStyle(e).display"), "text": body.inner_text(),
               "hrefs": body.locator(".tlinks a").evaluate_all("as => as.map(a => a.getAttribute('href'))"),
               "errors": errors}
        browser.close()
        return out


class MemoryBoardDetail(unittest.TestCase):
    def setUp(self):
        self.brain = Brain()
        self.config = self.brain.config()
        self.board = self.brain.board()
        name_task(self.board, SOIL, "TASK-2026-0901")
        quiet(build_status.build, self.config, self.board)

    def tearDown(self):
        self.brain.close()

    def test_the_detail_carries_every_field_and_links_the_task_file(self):
        item = page_items(self.board)[SOIL]
        facts = dict(item["facts"])
        self.assertEqual(facts["Version"], "1.1.0")
        self.assertIn("Asked", facts)
        self.assertTrue(item["landed"] and item["review"])
        link = item["taskLinks"][0]
        self.assertEqual(link["id"], "TASK-2026-0901")
        target = (Path(self.board["folder"]) / link["href"]).resolve()
        self.assertEqual(target, (self.brain.memory / "tasks" / "open" / "TASK-2026-0901-beds.md").resolve())
        self.assertIsInstance(item["history"], list)

    def test_an_empty_where_draws_no_bare_label_and_the_click_opens_the_detail(self):
        seen = open_detail(self.board, SOIL)
        if seen is None:
            self.skipTest("no headless browser here")
        self.assertEqual(seen["errors"], [])
        self.assertEqual(seen["display"], "block")
        for word in ("Asked:", "Version:", "Task:", "TASK-2026-0901", "To check:"):
            self.assertIn(word, seen["text"])
        self.assertEqual(len(seen["hrefs"]), 1)
        self.assertTrue(seen["hrefs"][0].endswith("TASK-2026-0901-beds.md"))


class RepositoryBoardDetail(unittest.TestCase):
    def setUp(self):
        self.brain = Brain(shared=True)
        self.config = self.brain.config()
        self.board = self.brain.board()
        name_task(self.board, SOIL, "TASK-2026-0901")
        quiet(build_status.build, self.config, self.board)

    def tearDown(self):
        self.brain.close()

    def test_the_task_is_named_by_id_with_a_note_and_no_memory_path(self):
        item = page_items(self.board)[SOIL]
        self.assertEqual(item["taskLinks"], [{"id": "TASK-2026-0901", "note": card_detail.REPO_NOTE}])
        self.assertEqual(dict(item["facts"])["Version"], "1.1.0")
        page = (Path(self.board["folder"]) / "status.html").read_text(encoding="utf-8")
        self.assertNotIn("/memory/", page)

    def test_the_click_opens_the_detail_with_the_task_id_and_no_link(self):
        seen = open_detail(self.board, SOIL)
        if seen is None:
            self.skipTest("no headless browser here")
        self.assertEqual(seen["errors"], [])
        self.assertEqual(seen["display"], "block")
        self.assertIn("TASK-2026-0901", seen["text"])
        self.assertIn("owner's own brain", seen["text"])
        self.assertEqual(seen["hrefs"], [])


LONG_BRANCH = "robin-example-a-very-long-branch-name-that-is-wider-than-any-card-on-the-board"


def set_branch(board: dict, card_id: str, branch: str) -> None:
    path = Path(board["folder"]) / "cards" / (card_id + ".md")
    text = path.read_text(encoding="utf-8")
    path.write_text(re.sub(r"(?m)^branch: .*$", "branch: " + branch, text, count=1), encoding="utf-8")


def facts_fit(board: dict, width: int):
    """Open the soil-depth card at `width` px; each fact's box against the card's, or None."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    url = (Path(board["folder"]) / "status.html").resolve().as_uri()
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=str(CHROME)) if CHROME.exists() else p.chromium.launch()
        except Exception:
            return None
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(url)
        card = page.locator("div.card", has=page.locator("p.ask", has_text="soil depth")).first
        card.click()
        out = card.evaluate("""c => {
          const box = c.getBoundingClientRect();
          return {cardRight: box.right, cardLeft: box.left, page: document.documentElement.scrollWidth,
            facts: [...c.querySelectorAll('.facts span')].map(s => ({text: s.innerText,
              left: s.getBoundingClientRect().left, right: s.getBoundingClientRect().right,
              title: (s.querySelector('i') || {}).title || ''}))};
        }""")
        browser.close()
        return out


class FactsLineWraps(unittest.TestCase):
    """A long branch name stays inside the card at a phone's width and a desktop's."""

    def setUp(self):
        self.brain = Brain(shared=True)
        self.config = self.brain.config()
        self.board = self.brain.board()
        set_branch(self.board, SOIL, LONG_BRANCH)
        quiet(build_status.build, self.config, self.board)

    def tearDown(self):
        self.brain.close()

    def test_every_fact_stays_inside_the_card_and_the_long_branch_keeps_a_tooltip(self):
        for width in (390, 1280):
            seen = facts_fit(self.board, width)
            if seen is None:
                self.skipTest("no headless browser here")
            self.assertLessEqual(seen["page"], width, width)
            self.assertTrue(seen["facts"], width)
            for fact in seen["facts"]:
                self.assertGreaterEqual(fact["left"], seen["cardLeft"] - 0.5, (width, fact))
                self.assertLessEqual(fact["right"], seen["cardRight"] + 0.5, (width, fact))
            branch = [f for f in seen["facts"] if f["text"].startswith("Branch:")]
            self.assertEqual(branch[0]["title"], "Branch: " + LONG_BRANCH)


@unittest.skipUnless(HAS_GIT, "git is not installed")
class BranchBy(unittest.TestCase):
    """'Card by' is who wrote the card; 'Branch by' is who wrote the branch, read from Git."""

    def setUp(self):
        self.brain = Brain(with_repo=True)
        self.config = self.brain.config()
        self.board = self.brain.board()
        repo = self.brain.repo
        # The seed-list branch is Robin's, pushed and then gone from the local checkout, so its
        # author must come from the remote copy.
        git(repo, "checkout", "-q", "-b", "feature/seed-list")
        (repo / "seeds.txt").write_text("tomato", encoding="utf-8")
        git(repo, "add", "seeds.txt")
        git(repo, "-c", "user.name=Robin Example", "-c", "user.email=robin@example.com",
            "commit", "-q", "-m", "seed list")
        git(repo, "push", "-q", "origin", "feature/seed-list")
        git(repo, "checkout", "-q", "main")
        git(repo, "branch", "-q", "-D", "feature/seed-list")
        quiet(build_status.build, self.config, self.board)

    def tearDown(self):
        self.brain.close()

    def test_the_branch_shows_its_own_author_beside_it_and_the_card_its_writer_last(self):
        facts = page_items(self.board)[SEED]["facts"]
        labels = [label for label, _ in facts]
        self.assertEqual(dict(facts)["Branch by"], "Robin Example")
        self.assertEqual(dict(facts)["Card by"], "sam")
        self.assertNotIn("Author", labels)
        self.assertEqual(labels.index("Branch by"), labels.index("Branch") + 1)
        self.assertEqual(labels[-1], "Card by")

    def test_git_that_cannot_tell_names_no_branch_author(self):
        self.assertEqual(card_detail.branch_authors(self.board, "no/such-branch"), "")
        # Merged into main: no commit of its own is left to name an author by.
        self.assertEqual(card_detail.branch_authors(self.board, "release/1.2.0"), "")
        self.assertEqual(card_detail.branch_authors(dict(self.board, repo=None), "feature/seed-list"), "")
        # A card with no branch carries neither label.
        labels = [label for label, _ in page_items(self.board)[SOIL]["facts"]]
        self.assertNotIn("Branch by", labels)

    def test_authors_are_ordered_by_commits_then_name(self):
        repo = self.brain.repo
        git(repo, "checkout", "-q", "-b", "feature/shared-work")
        for who, name in (("Kim Example", "a"), ("Ari Example", "b"), ("Ari Example", "c")):
            (repo / (name + ".txt")).write_text(name, encoding="utf-8")
            git(repo, "add", name + ".txt")
            git(repo, "-c", "user.name=" + who, "-c", "user.email=x@example.com", "commit", "-q", "-m", name)
        git(repo, "checkout", "-q", "main")
        self.assertEqual(card_detail.branch_authors(self.board, "feature/shared-work"), "Ari Example, Kim Example")


class TaskIds(unittest.TestCase):
    def test_ids_come_from_the_task_field_then_the_text_each_once(self):
        item = {"task": "TASK-2026-0002", "title": "x (TASK-2026-0001, TASK-2026-0002)", "landed": "", "review": ""}
        self.assertEqual(card_detail.task_ids(item), ["TASK-2026-0002", "TASK-2026-0001"])


if __name__ == "__main__":
    unittest.main()
