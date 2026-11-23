import datetime as dt
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import learning_views as lv  # noqa: E402

LEARNINGS = "memory/projects/example-node/data/learnings"
LEARNING = "memory/projects/brain-development/data/learning"


def record(ident, title, category="working-methods", evidence="observed", review="reviewed",
           independence="independent", created="2026-01-02T10:00:00+10:00", next_action="watch it", extra=""):
    lines = ["---", "id: " + ident, "title: " + title, "type: learning", "created: " + created,
             "updated: " + created, "category: " + category, "evidence_status: " + evidence,
             "review_status: " + review, "review_independence: " + independence]
    if next_action is not None:
        lines.append('next_action: "%s"' % next_action)
    return "\n".join(lines) + extra + "\n---\n\n# " + title + "\n"


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "CONTRACT.md").write_text("x", encoding="utf-8")
        for d in (LEARNINGS, LEARNING + "/inbox"):
            (self.root / d).mkdir(parents=True)
        self.add("alpha.md", record("learning-alpha", "Alpha lesson", "observed-behaviour",
                                    created="2026-01-01T10:00:00+10:00"))
        self.add("beta.md", record("learning-beta", "Beta lesson", "observed-behaviour",
                                   created="2026-02-01T10:00:00+10:00", review="pending", independence="unknown"))
        self.add("gamma.md", record("learning-gamma", "Gamma lesson", "recovery-methods", evidence="confirmed"))
        self.add("README.md", "---\nid: r\ntitle: Readme\ntype: node_readme\n---\n")
        (self.root / LEARNING / "digest-2026-01-10.md").write_text(
            "---\nid: DIGEST-2026-01-10\ntitle: d\ntype: digest\ndelivery_status: delivered\n"
            "delivered: 2026-01-10T09:00:00+10:00\n---\n", encoding="utf-8")
        (self.root / LEARNING / "inbox" / "one.md").write_text(
            "---\nid: n1\ntitle: n\ntype: learning_note\nstatus: pending\n---\n", encoding="utf-8")
        (self.root / LEARNING / "inbox" / "two.md").write_text(
            "---\nid: n2\ntitle: n\ntype: learning_note\nstatus: integrated\n---\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, name, text):
        (self.root / LEARNINGS / name).write_text(text, encoding="utf-8")

    def now(self, minute=0):
        return dt.datetime(2026, 3, 1, 12, minute, 0)

    def build(self, minute=0):
        out = io.StringIO()
        with redirect_stdout(out):
            lv.cmd_build(self.root, None, self.now(minute))
        return out.getvalue()

    def check(self, minute=0):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = lv.cmd_check(self.root, None, self.now(minute))
        return rc, out.getvalue()

    def view(self, name):
        return (self.root / LEARNING / name).read_text(encoding="utf-8")


class BuildTests(Fixture):
    def test_counts_order_and_both_views_from_one_build(self):
        self.build()
        index, board = self.view("index.md"), self.view("board.md")
        self.assertIn("Records: 3;", index)
        self.assertIn("1 pending", index)
        self.assertIn("Evidence: 2 observed, 1 confirmed", index)
        self.assertIn("1 pending artifact(s)", index)
        self.assertIn("`DIGEST-2026-01-10` delivered 2026-01-10T09:00:00+10:00", index)
        rows = [l for l in index.splitlines() if l.startswith("| ") and "learning-" in l]
        self.assertEqual([r.split(" | ")[1] for r in rows], ["learning-beta", "learning-alpha", "learning-gamma"])
        board_rows = [l for l in board.splitlines() if l.startswith("| ") and "lesson" in l]
        self.assertEqual(len(board_rows), 3)
        for irow, brow in zip(rows, board_rows):
            self.assertEqual(irow.replace(" " + irow.split(" | ")[1] + " |", "", 1), brow)
        self.assertIn("| Category | Learning | Evidence / review | Next action |", board)
        self.assertNotIn("Learning ID", board)

    def test_no_date_and_no_phrase_in_the_views(self):
        self.build()
        for name in ("index.md", "board.md"):
            text = self.view(name)
            self.assertNotIn("next is due", text)
            self.assertIn("repeating reminder task", text)
            self.assertIn("tasks.py review", text)

    def test_nothing_new_changes_nothing(self):
        self.build(0)
        before = {n: self.view(n) for n in ("index.md", "board.md")}
        out = self.build(5)
        self.assertEqual(out.count("unchanged"), 2)
        self.assertEqual(before, {n: self.view(n) for n in ("index.md", "board.md")})

    def test_a_changed_record_rewrites_both(self):
        self.build(0)
        self.add("alpha.md", record("learning-alpha", "Alpha lesson", "observed-behaviour",
                                    created="2026-01-01T10:00:00+10:00", next_action="new step"))
        out = self.build(5)
        self.assertEqual(out.count("written"), 2)
        self.assertIn("new step", self.view("board.md"))
        self.assertIn("12:05:00", self.view("index.md"))

    def test_out_directory_leaves_the_real_views_alone(self):
        out_dir = self.root / "elsewhere"
        with redirect_stdout(io.StringIO()):
            lv.cmd_build(self.root, out_dir, self.now())
        self.assertTrue((out_dir / "index.md").is_file())
        self.assertFalse((self.root / LEARNING / "index.md").exists())

    def test_pipe_in_a_cell_is_escaped(self):
        self.add("alpha.md", record("learning-alpha", "Alpha lesson", next_action="a | b"))
        self.build()
        self.assertIn("a \\| b", self.view("board.md"))


class CheckTests(Fixture):
    def test_passes_on_a_fresh_pair_and_after_a_time_only_difference(self):
        self.build(0)
        self.assertEqual(self.check(30)[0], 0)

    def test_fails_on_a_stale_board_naming_the_view_and_line(self):
        self.build()
        board = self.root / LEARNING / "board.md"
        board.write_text(board.read_text(encoding="utf-8").replace("watch it", "old text", 1), encoding="utf-8")
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("board.md differs from a fresh build at line", out)
        self.assertNotIn("index.md differs", out)

    def test_fails_when_a_view_is_missing(self):
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("cannot be read", out)

    def test_unparseable_record_is_listed_and_fails(self):
        self.add("bad.md", "---\ntype: learning\nthis is not a key value\n---\n")
        self.build()
        for name in ("index.md", "board.md"):
            self.assertIn("- Not read: /" + LEARNINGS + "/bad.md (", self.view(name))
            self.assertIn("Records: 3;", self.view(name))
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("not read:", out)

    def test_unclosed_front_matter_is_not_read(self):
        self.add("bad.md", "---\ntype: learning\nid: x\n")
        self.build()
        self.assertIn("front matter is not closed", self.view("index.md"))

    def test_missing_next_action_shows_not_set_and_fails(self):
        self.add("alpha.md", record("learning-alpha", "Alpha lesson", "observed-behaviour", next_action=None))
        self.build()
        self.assertIn("| not set |", self.view("board.md"))
        rc, out = self.check()
        self.assertEqual(rc, 1)
        self.assertIn("next_action missing", out)


class ParseTests(unittest.TestCase):
    def test_quoted_value_with_colon_and_backticks(self):
        fm = lv.parse_front_matter('---\nnext_action: "none: now `RULE` text"\nid: a\n---\nbody')
        self.assertEqual(fm["next_action"], "none: now `RULE` text")

    def test_crlf_front_matter(self):
        self.assertEqual(lv.parse_front_matter("---\r\nid: a\r\n---\r\n")["id"], "a")

    def test_review_cell_variants(self):
        base = {"evidence_status": "owner-reported, with research", "review_status": "reviewed"}
        self.assertEqual(lv.review_cell(dict(base, review_independence="same_model")),
                         "owner-reported / reviewed (same model)")
        self.assertEqual(lv.review_cell(dict(base)), "owner-reported / reviewed (independence not recorded)")
        self.assertEqual(lv.review_cell({"evidence_status": "observed", "review_status": "pending"}),
                         "observed / pending")


if __name__ == "__main__":
    unittest.main()
