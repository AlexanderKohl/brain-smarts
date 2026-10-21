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
from board_fixtures import SOIL, Brain, quiet  # noqa: E402

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


class TaskIds(unittest.TestCase):
    def test_ids_come_from_the_task_field_then_the_text_each_once(self):
        item = {"task": "TASK-2026-0002", "title": "x (TASK-2026-0001, TASK-2026-0002)", "landed": "", "review": ""}
        self.assertEqual(card_detail.task_ids(item), ["TASK-2026-0002", "TASK-2026-0001"])


if __name__ == "__main__":
    unittest.main()
