"""vault_credentials.py delete-field removes one field and leaves the rest of its entry. Every vault
here is a fictional one in a temporary folder, never the owner's vault."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import os
import secrets
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import vault_credentials  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402

ENTRY = "fictional-mail"


class DeleteFieldTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.vault_path = self.folder / "fictional.vault"
        self.passphrase = "fictional-" + secrets.token_hex(16)
        self.vault = PortableVault(self.vault_path)
        self.vault.initialize(self.passphrase)
        self.vault.set_fields(ENTRY, {"client_id": ("fictional-id", "text"), "client_secret": ("fictional-secret", "text"),
                                      "oauth_token_json": ({"refresh_token": "fictional-token"}, "json")}, self.passphrase)
        self.vault.set_fields("fictional-other", {"api_key": ("fictional-key", "text")}, self.passphrase)

    def fields(self, entry=ENTRY):
        return sorted(self.vault.load(self.passphrase)["entries"][entry]["fields"])

    def run_tool(self, entry, field, typed):
        """(exit code, standard output, standard error) of delete-field with `typed` at the confirmation."""
        out, err = io.StringIO(), io.StringIO()
        environment = {k: v for k, v in os.environ.items() if k != "PORTABLE_VAULT_PATH"}
        environment["PORTABLE_VAULT_PASSPHRASE"] = self.passphrase
        argv = ["vault_credentials.py", "--vault", str(self.vault_path), "delete-field", "--entry", entry, "--field", field]
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch("builtins.input", return_value=typed), \
                mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = vault_credentials.main()
        return code, out.getvalue(), err.getvalue()

    def test_one_field_goes_and_the_rest_of_the_entry_stays(self):
        code, out, _err = self.run_tool(ENTRY, "client_secret", f"{ENTRY}#client_secret")
        self.assertEqual(code, 0)
        self.assertEqual(self.fields(), ["client_id", "oauth_token_json"])
        self.assertEqual(self.vault.get(ENTRY, "oauth_token_json", self.passphrase), {"refresh_token": "fictional-token"})
        self.assertEqual(self.fields("fictional-other"), ["api_key"], "another entry is untouched")
        self.assertIn(f"Deleted encrypted credential field: {ENTRY}#client_secret", out)
        self.assertNotIn("fictional-secret", out)

    def test_nothing_is_deleted_unless_the_owner_types_the_exact_target(self):
        for typed in ("", "yes", ENTRY, f"{ENTRY}#client_id"):
            code, _out, err = self.run_tool(ENTRY, "client_secret", typed)
            self.assertEqual(code, 2, typed)
            self.assertIn("not confirmed", err)
        self.assertEqual(self.fields(), ["client_id", "client_secret", "oauth_token_json"])

    def test_a_field_or_entry_that_does_not_exist_is_an_error(self):
        for entry, field in ((ENTRY, "absent_field"), ("fictional-absent", "client_id")):
            code, _out, err = self.run_tool(entry, field, f"{entry}#{field}")
            self.assertEqual(code, 2)
            self.assertIn(f"Credential field does not exist: {entry}#{field}", err)

    def test_the_last_field_of_an_entry_is_refused(self):
        code, _out, err = self.run_tool("fictional-other", "api_key", "fictional-other#api_key")
        self.assertEqual(code, 2)
        self.assertIn("delete-entry", err)
        self.assertEqual(self.fields("fictional-other"), ["api_key"])

    def test_a_wrong_passphrase_deletes_nothing(self):
        with self.assertRaises(CredentialError):
            self.vault.delete_field(ENTRY, "client_secret", "fictional-wrong-" + secrets.token_hex(16))
        self.assertEqual(self.fields(), ["client_id", "client_secret", "oauth_token_json"])


if __name__ == "__main__":
    unittest.main()
