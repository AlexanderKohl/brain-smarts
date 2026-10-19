"""vault_credentials.py list prints the entry names of a vault in alphabetical order and their count,
never a field name or value, and prints nothing when the vault cannot be unlocked. Every vault here is
a fictional one in a temporary folder, never the owner's vault."""
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
from portable_vault import CredentialError, PortableVault  # noqa: E402


class ListEntriesTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.vault_path = self.folder / "fictional.vault"
        self.passphrase = "fictional-" + secrets.token_hex(16)
        self.field_values = {
            "zeta-fictional-crm": {"api_key": "fictional-value-" + secrets.token_hex(8)},
            "Alpha Fictional Mail": {"client_id": "fictional-value-" + secrets.token_hex(8)},
            "beta-fictional-bank": {"username": "fictional-value-" + secrets.token_hex(8)},
        }
        vault = PortableVault(self.vault_path)
        vault.initialize(self.passphrase)
        for entry, fields in self.field_values.items():
            vault.set_fields(entry, {name: (value, "text") for name, value in fields.items()},
                             self.passphrase)

    def run_list(self, passphrase, vault_path=None):
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"PORTABLE_VAULT_PATH", "PORTABLE_VAULT_PASSPHRASE"}}
        environment["PORTABLE_VAULT_PASSPHRASE"] = passphrase
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "vault_credentials.py"),
             "--vault", str(vault_path or self.vault_path), "list"],
            capture_output=True, text=True, env=environment, stdin=subprocess.DEVNULL, timeout=120,
        )

    def test_entry_names_in_alphabetical_order_then_the_count(self):
        result = self.run_list(self.passphrase)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), [
            "Alpha Fictional Mail",
            "beta-fictional-bank",
            "zeta-fictional-crm",
            "3 entries",
        ])

    def test_no_field_name_value_or_passphrase_is_printed(self):
        result = self.run_list(self.passphrase)
        printed = result.stdout + result.stderr
        self.assertNotIn(self.passphrase, printed)
        for fields in self.field_values.values():
            for name, value in fields.items():
                self.assertNotIn(name, printed)
                self.assertNotIn(value, printed)

    def test_a_wrong_passphrase_prints_nothing_and_fails(self):
        result = self.run_list("fictional-wrong-" + secrets.token_hex(16))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
        self.assertNotIn("fictional-crm", result.stderr)

    def test_a_missing_vault_prints_nothing_and_fails(self):
        result = self.run_list(self.passphrase, self.folder / "absent.vault")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)

    def test_entry_names_reads_the_names_only(self):
        vault = PortableVault(self.vault_path)
        self.assertEqual(sorted(vault.entry_names(self.passphrase)),
                         sorted(self.field_values))
        with self.assertRaises(CredentialError):
            vault.entry_names("fictional-wrong-" + secrets.token_hex(16))


if __name__ == "__main__":
    unittest.main()
