"""Task numbers are claimed atomically: concurrent creators never share one."""
import unittest
from concurrent.futures import ThreadPoolExecutor

from brainfix import Brain

import task_new  # noqa: E402


class ClaimTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brain = Brain()

    def tearDown(self) -> None:
        self.brain.close()

    def test_concurrent_claims_are_distinct(self):
        with ThreadPoolExecutor(max_workers=16) as pool:
            ids = list(pool.map(lambda _: task_new.claim_id(self.brain.root, "sam", 2026), range(48)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids)[0], "TASK-sam-2026-0001")

    def test_claims_are_ignored_by_git_and_count_toward_the_next_number(self):
        task_new.claim_id(self.brain.root, "sam", 2026)
        claims = self.brain.store / ".claims"
        self.assertEqual((claims / ".gitignore").read_text(encoding="utf-8"), "*\n")
        self.assertEqual(task_new.next_id(self.brain.root, "sam", 2026), "TASK-sam-2026-0002")
        self.assertEqual(task_new.next_id(self.brain.root, "bob", 2026), "TASK-bob-2026-0001")


if __name__ == "__main__":
    unittest.main()
