"""The card schema in /shared/schemas/card-schema.md and the code agree (skill library amendment A1).

Run from the brain root:
    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BRAIN = SCRIPTS.parents[3]
sys.path.insert(0, str(SCRIPTS))

import build_boards  # noqa: E402
import cards  # noqa: E402

SCHEMA = BRAIN / "shared" / "schemas" / "card-schema.md"


def table(section: str) -> list[list[str]]:
    """Rows of the first table under `## <section>`, each as its cells without backticks."""
    text = SCHEMA.read_text(encoding="utf-8")
    body = re.search(r"^## " + section + r"\s*\n(.*?)(?=\n## |\Z)", text, re.S | re.M).group(1)
    lines = body.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("| "))
    end = next((i for i in range(start, len(lines)) if not lines[i].startswith("|")), len(lines))
    rows = [line for line in lines[start:end] if not line.startswith("|---") and not line.startswith("| ---")]
    return [[cell.strip().strip("`") for cell in row.strip("|").split("|")] for row in rows[1:]]


class CardSchemaTests(unittest.TestCase):
    def test_fields_match_what_card_py_writes_in_order(self) -> None:
        self.assertEqual([row[0] for row in table("Fields")], cards.FIELD_ORDER)

    def test_states_and_labels_match_the_board_in_order(self) -> None:
        self.assertEqual([(row[0], row[1]) for row in table("States")], build_boards.STATES)

    def test_the_only_list_field_is_the_one_the_code_treats_as_a_list(self) -> None:
        text = SCHEMA.read_text(encoding="utf-8")
        self.assertIn("(the only list field)", text)
        self.assertEqual(cards.LIST_FIELDS, {"area"})


if __name__ == "__main__":
    unittest.main()
