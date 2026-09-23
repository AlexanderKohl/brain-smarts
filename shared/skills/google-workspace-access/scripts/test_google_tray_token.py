"""Unit tests for google_tray_token helpers. Uses fictional sample data only."""

from __future__ import annotations

import unittest

from google_tray_token import event_matches, parse_au_address


class EventMatchTests(unittest.TestCase):
    def test_matches_location_and_person_in_summary(self) -> None:
        event = {
            "summary": "Coffee with Jane Example",
            "location": "12 Fictional Lane, Exampletown QLD 4999, Australia",
        }
        self.assertTrue(
            event_matches(
                event,
                location_contains="Exampletown",
                person_needles=["Jane", "Example"],
            )
        )

    def test_rejects_wrong_suburb(self) -> None:
        event = {
            "summary": "Coffee with Jane Example",
            "location": "9 Madeup Street, Otherplace QLD 4000",
        }
        self.assertFalse(
            event_matches(
                event,
                location_contains="Exampletown",
                person_needles=["Jane"],
            )
        )


class AddressParseTests(unittest.TestCase):
    def test_parses_australian_street_address(self) -> None:
        parsed = parse_au_address(
            "12 Fictional Lane, Exampletown QLD 4999, Australia"
        )
        self.assertEqual(parsed["streetAddress"], "12 Fictional Lane")
        self.assertEqual(parsed["city"], "Exampletown")
        self.assertEqual(parsed["region"], "QLD")
        self.assertEqual(parsed["postalCode"], "4999")
        self.assertEqual(parsed["country"], "Australia")
        self.assertEqual(parsed["formattedValue"], "12 Fictional Lane, Exampletown QLD 4999, Australia")

    def test_keeps_unparsed_location_as_formatted_value(self) -> None:
        parsed = parse_au_address("Exampletown community hall")
        self.assertEqual(parsed["formattedValue"], "Exampletown community hall")
        self.assertNotIn("streetAddress", parsed)


if __name__ == "__main__":
    unittest.main()
