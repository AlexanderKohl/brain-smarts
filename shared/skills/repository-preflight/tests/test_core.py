"""/CORE.md: what always applies, verbatim, and when to read the rest; stale or incomplete fails."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import core  # noqa: E402
import preflight  # noqa: E402

CONTRACT = """---
updated: 2026-01-02T00:00:00+10:00
---

# Contract

## 1. Authority

Always read this.

### 1.1 Detail

Part of section 1.

## 2. Rarely

Only when rare.

### 2.1 Sub

Also rare.
"""

RULES = """---
updated: 2026-01-03T00:00:00+10:00
---

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0001` | First | this file | always |
| `SMART-RULE-0002` | Second | this file | writing a widget |

| Section | Title | Applies when |
|---|---|---|
| §1 | Authority | always |
| §2.1 | Sub | a rare case |

## SMART-RULE-0001 – First

- Always do the first thing.

## SMART-RULE-0002 – Second

- Do the second thing when writing a widget.
"""


def brain(rules: str = RULES) -> Path:
    root = Path(tempfile.mkdtemp())
    (root / "CONTRACT.md").write_text(CONTRACT, encoding="utf-8")
    (root / "RULES.md").write_text(rules, encoding="utf-8")
    return root


class CoreTest(unittest.TestCase):
    def test_core_holds_what_always_applies_and_the_tables(self):
        text = core.render(brain())
        self.assertIn("## 1. Authority\n\nAlways read this.\n\n### 1.1 Detail\n\nPart of section 1.", text)
        self.assertIn("- Always do the first thing.", text)
        self.assertIn("| `SMART-RULE-0002` | Second | this file | writing a widget |", text)
        self.assertIn("| §2.1 | Sub | a rare case |", text)
        self.assertNotIn("Only when rare.", text)
        self.assertNotIn("- Do the second thing", text)
        self.assertIn("updated: 2026-01-03T00:00:00+10:00", text)

    def test_a_row_without_applies_when_fails(self):
        found = core.problems(RULES.replace("| writing a widget |", "|  |"))
        self.assertEqual(found, ["/RULES.md: SMART-RULE-0002 has no Applies when"])

    def test_a_rule_heading_without_an_index_row_fails(self):
        found = core.problems(RULES + "\n## SMART-RULE-0003 – Third\n\n- Unlisted.\n")
        self.assertEqual(found, ["/RULES.md: SMART-RULE-0003 has a heading but no index row"])

    def test_preflight_fails_a_stale_core_and_passes_a_fresh_one(self):
        root = brain()
        errors = []
        preflight.validate_core(root, errors)
        self.assertEqual(len(errors), 1)
        self.assertIn("out of date", errors[0])
        self.assertEqual(core.main(["build", "--root", str(root)]), 0)
        errors = []
        preflight.validate_core(root, errors)
        self.assertEqual(errors, [])
        (root / "RULES.md").write_text(RULES.replace("Always do", "Always, always do"), encoding="utf-8")
        preflight.validate_core(root, errors)
        self.assertEqual(len(errors), 1)

    def test_the_real_core_is_current(self):
        root = Path(__file__).resolve().parents[4]
        self.assertEqual(core.main(["check", "--root", str(root)]), 0)


if __name__ == "__main__":
    unittest.main()
