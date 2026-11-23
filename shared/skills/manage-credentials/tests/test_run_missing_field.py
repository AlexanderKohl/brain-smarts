"""The credential runner never waits for a passphrase nobody can type. Fictional data only.

Run from the brain root:
    python -m unittest shared/skills/manage-credentials/tests/test_run_missing_field.py -v
"""
from __future__ import annotations

import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import contextlib
import io
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import vault_broker_client  # noqa: E402
import vault_credentials  # noqa: E402
from portable_vault import CredentialError  # noqa: E402

RUN = ["run", "--entry", "example-entry", "--map", "EXAMPLE_ID=client_id", "--", sys.executable, "-c", "print('child ran')"]


class NoTerminal:
    def isatty(self) -> bool:
        return False


def run_tool(request, unlocked: bool = True) -> tuple[int, str]:
    """(exit code, what the tool wrote to standard error) with a faked Vault Agent and no terminal."""
    errors = io.StringIO()
    clean = {k: v for k, v in os.environ.items() if k != "PORTABLE_VAULT_PASSPHRASE"}
    with mock.patch.object(vault_broker_client, "broker_request", request), \
            mock.patch.object(vault_broker_client, "broker_unlocked", lambda: unlocked), \
            mock.patch.object(vault_credentials.getpass, "getpass", side_effect=AssertionError("a prompt would hang here")), \
            mock.patch.object(sys, "stdin", NoTerminal()), mock.patch.dict(os.environ, clean, clear=True), \
            mock.patch.object(sys, "argv", ["vault_credentials.py", *RUN]), contextlib.redirect_stderr(errors):
        code = vault_credentials.main()
    return code, errors.getvalue()


class RunTests(unittest.TestCase):
    def test_a_field_the_unlocked_agent_says_is_missing_fails_at_once_and_names_it(self) -> None:
        def request(operation: str, **payload: object) -> object:
            raise CredentialError("Credential field does not exist: example-entry#client_id")

        code, said = run_tool(request)
        self.assertEqual(code, 2)
        self.assertIn("Credential field does not exist: example-entry#client_id", said)

    def test_a_locked_agent_without_a_terminal_fails_with_what_to_do(self) -> None:
        def request(operation: str, **payload: object) -> object:
            raise vault_broker_client.BrokerLocked("locked")

        code, said = run_tool(request, unlocked=False)
        self.assertEqual(code, 2)
        self.assertIn("no terminal", said)
        self.assertIn("Unlock the Portable Vault tray app", said)

    def test_an_agent_that_goes_away_mid_request_is_treated_as_unavailable(self) -> None:
        def request(operation: str, **payload: object) -> object:
            raise vault_broker_client.BrokerUnavailable("gone")

        self.assertIsNone(self.fields(request))

    def test_the_fields_are_returned_when_the_agent_has_them(self) -> None:
        self.assertEqual(self.fields(lambda operation, **payload: {"client_id": "sample-id"}), {"client_id": "sample-id"})

    def test_the_null_device_is_no_terminal_so_listing_fails_at_once(self) -> None:
        # On Windows the null device answers isatty() with yes; a session's shell hands it over as standard input.
        errors = io.StringIO()
        clean = {k: v for k, v in os.environ.items() if k != "PORTABLE_VAULT_PASSPHRASE"}
        with open(os.devnull) as nothing, mock.patch.object(sys, "stdin", nothing),                 mock.patch.object(vault_credentials.getpass, "getpass", side_effect=AssertionError("a prompt would hang here")),                 mock.patch.dict(os.environ, clean, clear=True),                 mock.patch.object(sys, "argv", ["vault_credentials.py", "list"]), contextlib.redirect_stderr(errors):
            code = vault_credentials.main()
        self.assertEqual(code, 2)
        self.assertIn("no terminal", errors.getvalue())

    def fields(self, request) -> object:
        with mock.patch.object(vault_broker_client, "broker_request", request), \
                mock.patch.object(vault_broker_client, "broker_unlocked", lambda: True):
            return vault_credentials._try_broker_fields("example-entry", ["client_id"])


if __name__ == "__main__":
    unittest.main()
