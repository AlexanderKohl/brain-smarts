"""core.py: a rule pack also holds the contract sections of its situation (PROPOSAL-contract-in-packs)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import core  # noqa: E402
import preflight  # noqa: E402
from test_core import PACKED, brain  # noqa: E402

ROW = "| `/rules/widgets.md` | making a widget | `SMART-RULE-0002`, `SMART-RULE-0003` |"
SECTIONED = PACKED.replace("| Pack | Applies when | Rules |", "| Pack | Applies when | Contract sections and rules |").replace(
    ROW, "| `/rules/widgets.md` | making a widget, or a rare case | `§2.1`, `SMART-RULE-0002`, `SMART-RULE-0003` |")


class SectionsInPacksTest(unittest.TestCase):
    def test_a_pack_holds_its_section_word_for_word_ahead_of_its_rules(self):
        self.assertEqual(core.problems(SECTIONED), [])
        parts = core.render(brain(SECTIONED))
        pack, second = parts["rules/widgets.md"], parts["RULES-CORE.md"]
        self.assertIn("### 2.1 Sub\n\nAlso rare.", pack)
        self.assertLess(pack.index("### 2.1 Sub"), pack.index("## SMART-RULE-0002"))
        self.assertIn("Generated from `/CONTRACT.md` and `/RULES.md`", pack)
        self.assertIn("A section's\ncanonical home stays `/CONTRACT.md`", pack)
        self.assertNotIn("Only when rare.", pack)                    # section 2 itself is not named, only 2.1
        # the section's row names the pack, whose own row says when
        self.assertIn("| §2.1 | Sub | in `/rules/widgets.md` |", second)
        self.assertNotIn("| §2.1 | Sub | a rare case |", second)
        self.assertIn("| §1 | Authority | always |", second)
        self.assertIn("holds, verbatim, the contract sections and the rules of one situation", second)
        self.assertIn("| `/rules/widgets.md` | making a widget, or a rare case | `§2.1`, `SMART-RULE-0002`, `SMART-RULE-0003` |", second)

    def test_a_pack_without_a_section_reads_as_before(self):
        parts = core.render(brain(PACKED))
        self.assertIn("Generated from `/RULES.md` by `core.py build`", parts["rules/widgets.md"])
        self.assertIn("| §2.1 | Sub | a rare case |", parts["RULES-CORE.md"])
        self.assertIn("A rule pack holds, verbatim, the rules of one situation.", parts["RULES-CORE.md"])

    def test_a_pack_with_a_section_stands_with_fewer_than_two_rules(self):
        one_rule = SECTIONED.replace("`§2.1`, `SMART-RULE-0002`, `SMART-RULE-0003` |", "`§2.1`, `SMART-RULE-0002` |")
        only_section = SECTIONED.replace("`§2.1`, `SMART-RULE-0002`, `SMART-RULE-0003` |", "`§2.1` |")
        self.assertEqual(core.problems(one_rule), [])
        self.assertEqual(core.problems(only_section), [])
        pack = core.render(brain(only_section))["rules/widgets.md"]
        self.assertIn("### 2.1 Sub\n\nAlso rare.", pack)
        self.assertNotIn("| ID | Rule |", pack)                          # no rule table when it holds no rule
        self.assertEqual(core.problems(PACKED.replace(", `SMART-RULE-0003` |", " |")),
                         ["/RULES.md: pack /rules/widgets.md names fewer than two rules; a single rule keeps its own row"])

    def test_a_pack_that_names_a_wrong_section_fails(self):
        always = SECTIONED.replace("`§2.1`, `SMART-RULE-0002`", "`§1`, `SMART-RULE-0002`")
        unlisted = SECTIONED.replace("`§2.1`, `SMART-RULE-0002`", "`§7`, `SMART-RULE-0002`")
        self.assertEqual(core.problems(always),
                         ["/RULES.md: pack /rules/widgets.md names CONTRACT §1, which always applies and is in the core"])
        self.assertEqual(core.problems(unlisted),
                         ["/RULES.md: pack /rules/widgets.md names CONTRACT §7, which the section table does not list"])

    def test_the_preflight_fails_a_pack_that_is_out_of_date_with_the_contract(self):
        root = brain(SECTIONED)
        self.assertEqual(core.main(["build", "--root", str(root)]), 0)
        errors: list[str] = []
        preflight.validate_core(root, errors)
        self.assertEqual(errors, [])
        contract = (root / "CONTRACT.md").read_text(encoding="utf-8")
        (root / "CONTRACT.md").write_text(contract.replace("Also rare.", "Also very rare."), encoding="utf-8")
        preflight.validate_core(root, errors)
        self.assertEqual(errors, ["/rules/widgets.md: out of date with /CONTRACT.md and /RULES.md; run core.py build"])

    def test_every_real_section_that_does_not_always_apply_is_in_a_pack(self):
        root = Path(__file__).resolve().parents[4]
        rules = (root / "RULES.md").read_text(encoding="utf-8").replace("\r\n", "\n")
        held = {number for numbers in core.pack_sections(rules).values() for number in numbers}
        loose = [key for key, when in core.tables(rules)[3] if not when.startswith("always") and key not in held]
        self.assertEqual(loose, [])


if __name__ == "__main__":
    unittest.main()
