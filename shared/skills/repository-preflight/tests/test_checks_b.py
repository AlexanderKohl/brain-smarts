"""The eval-b preflight checks: pointer files, knowledge provenance, knowledge review dates."""
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import checks_b  # noqa: E402


class PointerTest(unittest.TestCase):
    def test_rule_id_in_a_pointer_fails(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "CLAUDE.md").write_text("Read /CONTRACT.md. SMART-RULE-0009 says commit.\n", encoding="utf-8")
            (root / "AGENTS.md").write_text("Read /CONTRACT.md.\n", encoding="utf-8")
            errors = []
            checks_b.validate_pointer_files(root, errors)
            self.assertEqual(len(errors), 1)
            self.assertIn("CLAUDE.md", errors[0])


class ProvenanceTest(unittest.TestCase):
    def test_added_line_citing_a_source_needs_a_status(self):
        with tempfile.TemporaryDirectory() as d:
            memory = Path(d) / "memory"
            node = memory / "projects" / "x"
            node.mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=memory, check=True)
            (node / "KNOWLEDGE.md").write_text("# Knowledge\n", encoding="utf-8")
            subprocess.run(["git", "add", "-A"], cwd=memory, check=True)
            subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-qm", "x"], cwd=memory, check=True)
            (node / "KNOWLEDGE.md").write_text("# Knowledge\n- Bank account changed (/memory/sources/s-1.md)\n"
                                               "- Grout is charcoal (/memory/sources/s-2.md, unverified)\n", encoding="utf-8")
            errors = []
            checks_b.validate_knowledge_provenance(Path(d), errors)
            self.assertEqual(len(errors), 1)


class ReviewDateTest(unittest.TestCase):
    def test_a_claim_past_its_review_date_fails_and_a_superseded_one_does_not(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "memory" / "projects" / "x").mkdir(parents=True)
            (root / "memory" / "projects" / "x" / "KNOWLEDGE.md").write_text(
                "- Price: $465,000 (as of 2026-09-20; review by 2026-09-25)\n"
                "~~- Price: $500,000 (as of 2026-08-10; review by 2026-08-11)~~\n"
                "- Site manager: Rowan Ashdale (as of 2026-09-20; review by 2026-12-31)\n", encoding="utf-8")
            errors = []
            checks_b.validate_knowledge_review_dates(root, errors, today=date(2026, 9, 27))
            self.assertEqual(len(errors), 1)
            self.assertIn("2026-09-25", errors[0])


if __name__ == "__main__":
    unittest.main()
