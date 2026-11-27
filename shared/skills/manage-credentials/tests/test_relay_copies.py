"""The team credential relay copies some of this skill's modules (design team-credential-relay.md,
section 9; product-development rule 15). scripts/team_relay/relay-copies.json holds the hash of each
as the relay copied it; this test fails when one changes here, so the relay's copy is changed in the
same piece of work. Where the relay's repository is checked out beside the brain, its own pins must
be the same hashes."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import hashlib
import json
import re
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PINS = json.loads((SCRIPTS / "team_relay" / "relay-copies.json").read_text("utf-8"))
CLASS_END = "self.status, self.error, self.body = status, error, body"
CRLF, LF = bytes([13, 10]), bytes([10])


def _copied_part(rel: str) -> bytes:
    data = (SCRIPTS / rel).read_bytes().replace(CRLF, LF)
    if PINS["files"][rel]["part"] != "whole file":
        text = data.decode("utf-8")
        return text[text.index("class ProviderNotCalled"):text.index(CLASS_END) + len(CLASS_END)].encode("utf-8")
    return data


def _relay_checkout() -> Path | None:
    brain = Path(__file__).resolve().parents[4]
    owner = brain / "memory" / "OWNER.md"
    match = re.search(r"^project_repos_root:\s*(\S.*?)\s*$", owner.read_text("utf-8"), re.M) if owner.is_file() else None
    folder = (Path(match.group(1)) if match else brain.parent) / "brain-relay"
    return folder if (folder / "VENDORED.json").is_file() else None


class RelayCopies(unittest.TestCase):
    def test_every_copied_module_is_as_the_relay_copied_it(self):
        for rel, pin in PINS["files"].items():
            self.assertEqual(hashlib.sha256(_copied_part(rel)).hexdigest(), pin["sha256"],
                             f"{rel} changed: change the relay's copy and both pins in the same piece of work")

    def test_the_relays_pins_are_the_same_where_it_is_checked_out(self):
        relay = _relay_checkout()
        if relay is None:
            self.skipTest("brain-relay is not checked out beside the brain")
        theirs = json.loads((relay / "VENDORED.json").read_text("utf-8"))["files"]
        prefix = "shared/skills/manage-credentials/scripts/"
        mine = {rel: pin["sha256"] for rel, pin in PINS["files"].items()}
        self.assertEqual({pin["source"][len(prefix):]: pin["sha256"] for pin in theirs.values()}, mine)


if __name__ == "__main__":
    unittest.main()
