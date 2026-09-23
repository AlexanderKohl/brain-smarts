"""Behavioural tests for the personal-data check (SMART-RULE-0008) as the validator runs it.

Every value is invented. Values that must look like personal data are assembled at run time, so
this file itself passes the check.

Run from the brain root:
    python -m unittest discover -s shared/skills/repository-preflight/tests -v
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import personal_data  # noqa: E402
from test_preflight import Brain, md  # noqa: E402

AT = "@"


def personal(errors: list[str]) -> list[str]:
    return [e for e in errors if "personal data" in e or "personal-data" in e]


class PersonalDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()
        self.brain.write("memory/projects/orchard-planner/README.md", md("orchard-readme"))

    def tearDown(self) -> None:
        self.brain.close()

    def test_a_clean_mechanics_repository_reports_nothing(self) -> None:
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_owner_terms_and_patterns_in_the_mechanics_fail(self) -> None:
        self.brain.write("shared/skills/garden-access/SKILL.md", md(
            "skill-garden", "Written for Example Owner on the orchard-planner node.\n"
            "Mail robin" + AT + "realmail.test or call +61 7 " + "3000 0199.\n"))
        found = personal(self.brain.run().errors)
        kinds = sorted({e.split("(")[1].split(")")[0] for e in found})
        self.assertEqual(kinds, ["email", "owner-term", "phone"])
        self.assertTrue(all(e.startswith("/shared/skills/garden-access/SKILL.md:") for e in found))

    def test_the_same_values_in_memory_pass(self) -> None:
        self.brain.write("memory/projects/orchard-planner/NOTES.md", md(
            "orchard-notes", "Example Owner, robin" + AT + "realmail.test, +61 7 " + "3000 0199.\n"))
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_a_personal_name_matches_only_as_written(self) -> None:
        self.brain.write("shared/notes.md", md("shared-notes", "The owner decides; every owner may.\n"))
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_skeleton_node_names_are_not_owner_terms(self) -> None:
        self.brain.write("memory/projects/brain-development/README.md", md("bd-readme"))
        self.brain.write("shared/templates/memory-skeleton/projects/brain-development/README.md",
                         md("skeleton-bd-readme"))
        self.brain.write("shared/notes.md", md("shared-notes", "See the brain-development node.\n"))
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_vendor_documentation_is_exempt(self) -> None:
        self.brain.write("shared/skills/garden-access/openapi/spec.json",
                         '{"example": "jane' + AT + 'vendor-sample.test"}\n')
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_fiction_numbers_and_long_counts_are_not_phones(self) -> None:
        self.brain.write("shared/notes.md", md("shared-notes", "Call +1 555 010 0199. At 1700000000000 ms.\n"))
        self.assertEqual(personal(self.brain.run().errors), [])

    def test_without_memory_only_patterns_run(self) -> None:
        bare = Brain(with_memory=False)
        try:
            bare.write("shared/notes.md", md("shared-notes", "orchard-planner, and robin" + AT + "realmail.test\n"))
            kinds = [e.split("(")[1].split(")")[0] for e in personal(bare.run().errors)]
            self.assertEqual(kinds, ["email"])
        finally:
            bare.close()

    def test_an_exemption_without_a_reason_is_a_problem(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "exemptions.txt"
            path.write_text("path: */docs/*  # public docs\nvalue: something\n", encoding="utf-8")
            globs, values, problems = personal_data.load_exemptions(path)
        self.assertEqual((globs, values, len(problems)), (["*/docs/*"], set(), 1))

    def test_the_library_is_checked_when_present(self) -> None:
        self.brain.write("library/skills/garden-access/SKILL.md", md("lib-garden", "For Example Owner.\n"))
        found = personal(self.brain.run().errors)
        self.assertTrue(any(e.startswith("/library/skills/garden-access/SKILL.md:") for e in found), found)


if __name__ == "__main__":
    unittest.main()
