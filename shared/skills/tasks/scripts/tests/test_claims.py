"""Task numbers are claimed atomically: concurrent creators never share one (TASK-2026-0049)."""
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import tasks  # noqa: E402


class ClaimTest(unittest.TestCase):
    def test_concurrent_claims_are_distinct(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            (store / "open").mkdir()
            with ThreadPoolExecutor(max_workers=16) as pool:
                ids = list(pool.map(lambda _: tasks.claim_id(store, 2026), range(64)))
            self.assertEqual(len(ids), len(set(ids)))
            self.assertEqual(sorted(ids)[0], "TASK-2026-0001")

    def test_claims_are_ignored_by_git(self):
        with tempfile.TemporaryDirectory() as d:
            store = Path(d)
            tasks.claim_id(store, 2026)
            self.assertEqual((store / ".claims" / ".gitignore").read_text(encoding="utf-8"), "*\n")


if __name__ == "__main__":
    unittest.main()
