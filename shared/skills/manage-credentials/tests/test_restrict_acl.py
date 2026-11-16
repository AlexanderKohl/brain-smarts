"""restrict_to_current_user leaves only the user and SYSTEM with access on Windows. On a folder the
grants must be inheritable: `/inheritance:r` strips the inherited grants of every file already in
the folder, so without inheritable replacements those files (the vault's .lock file, a README) are
left with an empty access list, and the tray fails with "Permission denied" at unlock. Only
temporary folders are changed here."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import vault_agent_runtime  # noqa: E402


class IcaclsArgumentsTest(unittest.TestCase):
    def test_folder_grants_are_inherited_by_new_children(self):
        args = vault_agent_runtime.icacls_arguments(Path("vault-folder"), "fictional-user", True)
        self.assertEqual(args, ["icacls", "vault-folder", "/inheritance:r",
                                "/grant:r", "fictional-user:(OI)(CI)(F)",
                                "/grant:r", "SYSTEM:(OI)(CI)(F)"])

    def test_file_grants_carry_no_inheritance_flags(self):
        args = vault_agent_runtime.icacls_arguments(Path("x.vault"), "fictional-user", False)
        self.assertEqual(args, ["icacls", "x.vault", "/inheritance:r",
                                "/grant:r", "fictional-user:(F)", "/grant:r", "SYSTEM:(F)"])


@unittest.skipUnless(os.name == "nt", "Windows access lists only")
class RestrictedFolderTest(unittest.TestCase):
    def setUp(self):
        # mkdtemp() on Windows sets explicit grants of its own, which hide the bug; a folder made
        # inside it inherits its access, as the vault's data folder does from its parents.
        self.parent = Path(tempfile.mkdtemp())
        self.folder = self.parent / "data"
        self.folder.mkdir()
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        # A failing run can leave a child nobody can open; give it back before removing it.
        subprocess.run(["icacls", str(self.parent), "/grant", f"{os.environ['USERNAME']}:(OI)(CI)(F)",
                        "/T", "/C", "/Q"], capture_output=True)
        shutil.rmtree(self.parent, ignore_errors=True)

    def open_and_write(self, path):
        with path.open("a+b") as handle:
            handle.write(b"0")

    def test_a_file_that_existed_before_the_folder_is_restricted_still_opens(self):
        # The order a new vault meets: the .lock file and README exist, then save() restricts
        # the folder. /inheritance:r strips the children's inherited grants.
        earlier = self.folder / "fictional.vault.lock"
        self.open_and_write(earlier)
        vault_agent_runtime.restrict_to_current_user(self.folder)
        self.open_and_write(earlier)

    def test_a_file_created_after_the_folder_is_restricted_opens(self):
        vault_agent_runtime.restrict_to_current_user(self.folder)
        later = self.folder / "fictional.vault.lock"
        self.open_and_write(later)
        self.open_and_write(later)


if __name__ == "__main__":
    unittest.main()
