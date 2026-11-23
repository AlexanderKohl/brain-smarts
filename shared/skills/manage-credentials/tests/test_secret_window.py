"""secret_window.py checks, and vault_credentials.py init/put-entry --window routing with the windows
and the Vault Agent mocked. Every vault here is a fictional one in a temporary folder, never the
owner's vault; no window is ever shown."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import os
import secrets
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import secret_window  # noqa: E402
import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
from portable_vault import CredentialError, PortableVault  # noqa: E402

ENTRY = "fictional-service"


class CheckFunctionsTest(unittest.TestCase):
    def test_new_passphrase_needs_twenty_characters_and_a_match(self):
        good = "f" * secret_window.MIN_PASSPHRASE_LENGTH
        self.assertIsNone(secret_window.check_new_passphrase(good, good))
        self.assertIn("at least 20", secret_window.check_new_passphrase(good[:-1], good[:-1]))
        self.assertIn("do not match", secret_window.check_new_passphrase(good, good + "x"))
        self.assertIn("at least 20", secret_window.check_new_passphrase("", ""))

    def test_every_secret_field_needs_a_value(self):
        fields = ["client_id", "client_secret"]
        self.assertIsNone(secret_window.check_secret_values({"client_id": "a", "client_secret": "b"}, fields))
        self.assertIn("client_secret", secret_window.check_secret_values({"client_id": "a", "client_secret": ""}, fields))
        self.assertIn("client_id", secret_window.check_secret_values({}, fields))
        self.assertIsNone(secret_window.check_secret_values({}, []))

    def test_passphrase_given_and_pasted_line_break_removed(self):
        self.assertIsNotNone(secret_window.check_passphrase_given(""))
        self.assertIsNotNone(secret_window.check_passphrase_given(None))
        self.assertIsNone(secret_window.check_passphrase_given("fictional"))
        self.assertEqual(secret_window.clean_secret("fictional-value\r\n"), "fictional-value")

    def test_no_tkinter_gives_a_plain_message(self):
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            with self.assertRaises(CredentialError) as caught:
                secret_window.ask_new_passphrase()
        self.assertIn("python-tk", str(caught.exception))
        self.assertIn("without --window", str(caught.exception))

    def test_no_display_gives_a_plain_message(self):
        fake = types.ModuleType("tkinter")
        fake.TclError = type("TclError", (Exception,), {})

        def no_display():
            raise fake.TclError("no display name and no $DISPLAY environment variable")

        fake.Tk = no_display
        with mock.patch.dict(sys.modules, {"tkinter": fake}):
            with self.assertRaises(CredentialError) as caught:
                secret_window.ask_secrets("t", ["client_id"], need_passphrase=False)
        self.assertIn("without --window", str(caught.exception))


class WindowRoutingTest(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.vault_path = self.folder / "fictional.vault"
        self.passphrase = "fictional-" + secrets.token_hex(16)
        self.secret = "fictional-secret-" + secrets.token_hex(8)

    def run_tool(self, *arguments, unlocked=False, broker=None):
        """(exit code, standard output, standard error) of vault_credentials.py with the agent mocked."""
        out, err = io.StringIO(), io.StringIO()
        environment = {k: v for k, v in os.environ.items() if k not in ("PORTABLE_VAULT_PATH", "PORTABLE_VAULT_PASSPHRASE")}
        argv = ["vault_credentials.py", "--vault", str(self.vault_path), *arguments]
        broker = broker or mock.Mock(return_value={"saved": True})
        with mock.patch.dict(os.environ, environment, clear=True), mock.patch.object(sys, "argv", argv), \
                mock.patch.object(vault_broker_client, "broker_unlocked", return_value=unlocked), \
                mock.patch.object(vault_broker_client, "broker_request", broker), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = vault_credentials.main()
        self.assertNotIn(self.secret, out.getvalue() + err.getvalue())
        self.assertNotIn(self.passphrase, out.getvalue() + err.getvalue())
        self.assertNotIn(self.secret, os.environ.values())
        return code, out.getvalue(), err.getvalue()

    def make_vault(self):
        vault = PortableVault(self.vault_path)
        vault.initialize(self.passphrase)
        return vault

    def test_init_window_creates_the_vault(self):
        with mock.patch.object(secret_window, "ask_new_passphrase", return_value=self.passphrase):
            code, out, _err = self.run_tool("init", "--window")
        self.assertEqual(code, 0)
        self.assertIn("Initialised", out)
        self.assertEqual(PortableVault(self.vault_path).entry_names(self.passphrase), [])

    def test_init_window_cancel_creates_nothing(self):
        with mock.patch.object(secret_window, "ask_new_passphrase", return_value=None):
            code, out, err = self.run_tool("init", "--window")
        self.assertEqual(code, 1)
        self.assertIn("Cancelled; nothing stored.", err)
        self.assertFalse(self.vault_path.exists())

    def test_put_entry_window_locked_agent_asks_passphrase_and_writes_whole_entry(self):
        vault = self.make_vault()
        answer = ({"client_secret": self.secret}, self.passphrase)
        broker = mock.Mock()
        with mock.patch.object(secret_window, "ask_secrets", return_value=answer) as ask:
            code, out, _err = self.run_tool("put-entry", "--window", "--entry", ENTRY, "--secret", "client_secret",
                                            "--empty-json", "oauth_token_json", unlocked=False, broker=broker)
        self.assertEqual(code, 0)
        self.assertTrue(ask.call_args.kwargs["need_passphrase"])
        broker.assert_not_called()
        self.assertEqual(vault.get(ENTRY, "client_secret", self.passphrase), self.secret)
        self.assertEqual(vault.get(ENTRY, "oauth_token_json", self.passphrase), {})
        self.assertIn(f"{ENTRY} (client_secret, oauth_token_json)", out)

    def test_put_entry_window_unlocked_agent_stores_through_the_agent_without_passphrase(self):
        broker = mock.Mock(return_value={"saved": True})
        with mock.patch.object(secret_window, "ask_secrets", return_value=({"client_secret": self.secret}, None)) as ask:
            code, out, _err = self.run_tool("put-entry", "--window", "--entry", ENTRY, "--secret", "client_secret",
                                            "--empty-json", "oauth_token_json", unlocked=True, broker=broker)
        self.assertEqual(code, 0)
        self.assertFalse(ask.call_args.kwargs["need_passphrase"])
        broker.assert_has_calls([
            mock.call("set_text", entry=ENTRY, field="client_secret", value=self.secret),
            mock.call("set_json", entry=ENTRY, field="oauth_token_json", value={}),
        ])
        self.assertFalse(self.vault_path.exists(), "no direct vault write")

    def test_put_entry_window_unlocked_with_only_json_asks_nothing(self):
        broker = mock.Mock(return_value={"saved": True})
        with mock.patch.object(secret_window, "ask_secrets") as ask:
            code, _out, _err = self.run_tool("put-entry", "--window", "--entry", ENTRY, "--empty-json",
                                             "oauth_token_json", unlocked=True, broker=broker)
        self.assertEqual(code, 0)
        ask.assert_not_called()
        broker.assert_called_once_with("set_json", entry=ENTRY, field="oauth_token_json", value={})

    def test_put_entry_window_cancel_stores_nothing(self):
        vault = self.make_vault()
        broker = mock.Mock()
        for unlocked in (False, True):
            with mock.patch.object(secret_window, "ask_secrets", return_value=None):
                code, _out, err = self.run_tool("put-entry", "--window", "--entry", ENTRY, "--secret", "client_secret",
                                                unlocked=unlocked, broker=broker)
            self.assertEqual(code, 1)
            self.assertIn("Cancelled; nothing stored.", err)
        broker.assert_not_called()
        self.assertEqual(vault.entry_names(self.passphrase), [])

    def test_put_entry_window_empty_value_stores_nothing(self):
        vault = self.make_vault()
        broker = mock.Mock()
        for unlocked, passphrase in ((False, self.passphrase), (True, None), (False, "")):
            values = {"client_secret": ""} if passphrase != "" else {"client_secret": self.secret}
            with mock.patch.object(secret_window, "ask_secrets", return_value=(values, passphrase)):
                code, _out, err = self.run_tool("put-entry", "--window", "--entry", ENTRY, "--secret", "client_secret",
                                                unlocked=unlocked, broker=broker)
            self.assertEqual(code, 2)
            self.assertIn("Nothing stored.", err)
        broker.assert_not_called()
        self.assertEqual(vault.entry_names(self.passphrase), [])

    def test_without_window_put_entry_still_uses_the_terminal_path(self):
        with mock.patch.object(secret_window, "ask_secrets") as ask, \
                mock.patch.object(vault_credentials, "_keyboard", return_value=False):
            code, _out, err = self.run_tool("put-entry", "--entry", ENTRY, "--secret", "client_secret")
        self.assertEqual(code, 2)
        ask.assert_not_called()
        self.assertIn("no terminal", err)


if __name__ == "__main__":
    unittest.main()
