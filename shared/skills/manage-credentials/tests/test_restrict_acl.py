"""restrict_to_current_user leaves only the user and SYSTEM with access on Windows, through make_private
(follow-up plan R15, fix 1, rule 7). On a folder the two entries must be inheritable: a file that already
exists in the folder, or is created in it afterwards, must still open for the user, or the tray fails
with "Permission denied" at unlock (the vault's .lock file, a README). Only temporary folders are
changed here."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import vault_agent_runtime  # noqa: E402


@unittest.skipUnless(os.name == "nt", "Windows access lists only")
class RestrictedFolderTest(unittest.TestCase):
    def setUp(self):
        # mkdtemp() on Windows sets explicit grants of its own; a folder made inside it inherits its
        # access, as the vault's data folder does from its parents.
        self.parent = Path(tempfile.mkdtemp())
        self.folder = self.parent / "data"
        self.folder.mkdir()
        self.addCleanup(shutil.rmtree, self.parent, ignore_errors=True)

    def open_and_write(self, path):
        with path.open("a+b") as handle:
            handle.write(b"0")

    def test_only_the_user_and_system_hold_a_right(self):
        self.assertFalse(vault_agent_runtime.is_private(self.folder))
        vault_agent_runtime.restrict_to_current_user(self.folder)
        self.assertTrue(vault_agent_runtime.is_private(self.folder))

    def test_a_file_that_existed_before_the_folder_is_restricted_still_opens(self):
        # The order a new vault meets: the .lock file and README exist, then save() restricts the folder.
        earlier = self.folder / "fictional.vault.lock"
        self.open_and_write(earlier)
        vault_agent_runtime.restrict_to_current_user(self.folder)
        self.open_and_write(earlier)

    def test_a_file_created_after_the_folder_is_restricted_opens(self):
        vault_agent_runtime.restrict_to_current_user(self.folder)
        later = self.folder / "fictional.vault.lock"
        self.open_and_write(later)
        self.open_and_write(later)

    def test_no_subprocess_is_used(self):
        self.assertFalse(hasattr(vault_agent_runtime, "subprocess"))
        self.assertFalse(hasattr(vault_agent_runtime, "icacls_arguments"))


if __name__ == "__main__":
    unittest.main()
