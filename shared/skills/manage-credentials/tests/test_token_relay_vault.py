"""Token relay through PortableVaultJsonStore and the command line, on throwaway vaults.

The relay runs on its in-memory backend; the Vault Agent is either absent (in-process unlock) or a
fake broker held in a dictionary. No network, no gh call and no real vault. Every value is invented.
Tests named test_review2_finding_N_... reproduce the second review's findings 2, 3a and 6;
test_review3_finding_2_... reproduces the third review's finding 2 through seed --replace.
"""

from __future__ import annotations

import base64
import getpass
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import portable_vault  # noqa: E402
import token_relay  # noqa: E402
import token_relay_backend as trb  # noqa: E402
import vault_broker_client  # noqa: E402

KEY = bytes(range(32))
KEY_TEXT = base64.b64encode(KEY).decode("ascii")
ENTRY = "example-oauth"
NAME = "example-oauth.json"
PASSPHRASE = "example passphrase for a throwaway vault"
START = 1_900_000_000.0


def token(number: int) -> dict:
    return {
        "access_token": f"example-access-{number}",
        "refresh_token": f"example-refresh-{number}",
        "expires_at": START + number,
        "obtained_at": START,
    }


class VaultCase(unittest.TestCase):
    """A temporary folder, no Vault Agent, no subprocess and a fresh environment."""

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.backend = trb.MemoryBackend()
        for patch in (
            mock.patch.object(vault_broker_client, "broker_unlocked", lambda: False),
            mock.patch.object(portable_vault, "_apply_windows_user_acl", lambda path: None),
            mock.patch("subprocess.run", side_effect=AssertionError("no subprocess may run")),
            mock.patch.object(token_relay, "make_backend", lambda config: self.backend),
            mock.patch.dict(os.environ, {"PORTABLE_VAULT_PASSPHRASE": PASSPHRASE}),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def vault(self, name: str, value: dict, *, entries=None, key: bool = True) -> Path:
        folder = self.folder / name
        folder.mkdir()
        path = folder / "credentials.vault"
        vault = portable_vault.PortableVault(path)
        vault.initialize(PASSPHRASE)
        fields = {"oauth_token_json": (value, "json")}
        vault.set_fields(ENTRY, fields, PASSPHRASE)
        if key:
            vault.set("token-relay", "relay_key", KEY_TEXT, "text", PASSPHRASE)
        if entries is not None:
            config = {"backend": "github", "repository": "example-owner/example-relay", "entries": entries}
            (folder / "token-relay.json").write_text(json.dumps(config), encoding="utf-8")
        return path

    def store(self, path: Path):
        return portable_vault.PortableVaultJsonStore(ENTRY, path=path, passphrase=PASSPHRASE)


class RelayOffTests(VaultCase):
    def test_no_config_or_unlisted_entry_behaves_as_before(self):
        for name, entries in (("no-config", None), ("unlisted", ["another-oauth"])):
            path = self.vault(name, token(1), entries=entries, key=False)
            store = self.store(path)
            self.assertIsNone(store._relay)
            with store.rotation_lock(refresh=True, leeway_seconds=300):
                self.assertEqual(store.load(), token(1))
                store.save(token(2))
            store.sync()
            self.assertEqual(store.load(), token(2))
        self.assertEqual(self.backend.files, {})


class ListedEntryTests(VaultCase):
    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            code = token_relay.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_seed_status_and_a_listed_store_end_to_end(self):
        first = self.vault("brain-a", token(1), entries=[ENTRY])
        second = self.vault("brain-b", {}, entries=[ENTRY])

        store = self.store(first)
        self.assertIsInstance(store._relay, token_relay.RelayedStore)
        with self.assertRaisesRegex(trb.RelayIntegrityError, "no shared record"):
            with store.rotation_lock(refresh=True):
                self.fail("an unseeded entry must refuse")

        code, out, _ = self.run_main("--vault", str(first), "seed", "--entry", ENTRY)
        self.assertEqual((code, out.strip()), (0, f"Seeded {ENTRY} as version 1."))
        self.assertEqual(trb.decrypt_token(KEY, ENTRY, trb.parse_record(self.backend.files[NAME][0], ENTRY)), token(1))
        code, _, err = self.run_main("--vault", str(first), "seed", "--entry", ENTRY)
        self.assertEqual(code, 2)
        self.assertIn("already has a shared record", err)

        store = self.store(first)
        store.set_chain_keys(["access_token", "refresh_token", "expires_at", "obtained_at"])
        with store.rotation_lock(refresh=True):
            store.save(token(2))
        store.save({**store.load(), "selected_tenant_id": "tenant-example"})
        self.assertEqual(store.load(), {**token(2), "selected_tenant_id": "tenant-example"})

        other = self.store(second)
        self.assertEqual(other.load(), {})
        other.sync()
        self.assertEqual(other.load(), {**token(2), "selected_tenant_id": "tenant-example"})
        other.clear()
        self.assertEqual(other.load(), {})
        other.sync()  # second review, finding 2: a cleared computer adopts the shared token again
        self.assertEqual(other.load(), {**token(2), "selected_tenant_id": "tenant-example"})
        self.assertEqual(trb.parse_record(self.backend.files[NAME][0], ENTRY)["version"], 3)

        code, out, _ = self.run_main("--vault", str(first), "status")
        row = json.loads(out)
        self.assertEqual(
            (code, row["remote_version"], row["local_version"], row["unpushed"], row["lease_holder"]),
            (0, 3, 3, False, None),
        )
        for secret in ("example-refresh", "example-access", KEY_TEXT):
            self.assertNotIn(secret, out)

    def test_review2_finding_2_a_cleared_computer_re_adopts_through_the_vault(self):
        self.run_main("--vault", str(self.vault("brain-a", token(1), entries=[ENTRY])), "seed", "--entry", ENTRY)
        other = self.store(self.vault("brain-b", {}, entries=[ENTRY]))
        other.sync()
        other.clear()
        other.sync()
        self.assertEqual(other.load(), token(1))

    def test_review2_finding_3a_seed_replace_overwrites_a_stuck_record_at_a_higher_version(self):
        path = self.vault("brain-a", {**token(4), "_relay_version": 5}, entries=[ENTRY])
        old_key = trb.build_record(bytes(32), ENTRY, 3, token(1), lease=None, holder="h-1", updated_at="t")
        self.backend.put(NAME, trb.dump_record(old_key), None, "an old key's record")
        code, _, err = self.run_main("--vault", str(path), "seed", "--entry", ENTRY)
        self.assertEqual(code, 2)
        self.assertIn("--replace", err)

        def replace() -> tuple[int, dict]:
            code, out, _ = self.run_main("--vault", str(path), "seed", "--entry", ENTRY, "--replace")
            self.assertEqual(code, 0, out)
            record = trb.parse_record(self.backend.files[NAME][0], ENTRY)
            self.assertEqual(trb.decrypt_token(KEY, ENTRY, record), token(4))
            self.assertEqual(self.store(path)._local_load()["_relay_version"], record["version"])
            return record["version"], out

        self.assertEqual(replace(), (6, f"Seeded {ENTRY} as version 6.\n"))
        newer = trb.build_record(bytes(32), ENTRY, 9, token(1), lease=None, holder="h-1", updated_at="t")
        self.backend.put(NAME, trb.dump_record(newer), self.backend.files[NAME][1], "a newer record")
        self.assertEqual(replace()[0], 10)
        self.backend.files[NAME] = (b"not a relay record", self.backend.files[NAME][1])
        self.assertEqual(replace()[0], 11)
        empty = self.vault("brain-b", {}, entries=[ENTRY])
        code, _, err = self.run_main("--vault", str(empty), "seed", "--entry", ENTRY, "--replace")
        self.assertEqual(code, 2)
        self.assertIn("no refresh token", err)

    def test_review3_finding_2_after_key_new_replace_a_cleared_computer_authorises_then_seeds(self):
        path = self.vault("brain-a", {"_relay_version": 3}, entries=[ENTRY])  # cleared at version 3
        old_key = trb.build_record(bytes(32), ENTRY, 3, token(1), lease=None, holder="h-1", updated_at="t")
        self.backend.put(NAME, trb.dump_record(old_key), None, "a record under the old key")
        store = self.store(path)
        err = io.StringIO()
        with mock.patch.object(sys, "stderr", err):
            with store.rotation_lock(refresh=True, new_authorisation=True):
                store.save(token(5))
        self.assertIn(f"seed --entry {ENTRY} --replace next", err.getvalue())
        self.assertEqual(self.store(path).load(), token(5))
        code, out, _ = self.run_main("--vault", str(path), "seed", "--entry", ENTRY, "--replace")
        self.assertEqual((code, out), (0, f"Seeded {ENTRY} as version 4.\n"))
        record = trb.parse_record(self.backend.files[NAME][0], ENTRY)
        self.assertEqual(trb.decrypt_token(KEY, ENTRY, record), token(5))
        store = self.store(path)
        with store.rotation_lock(refresh=True):  # the relay works again with the new key
            store.save(token(6))
        self.assertEqual(trb.parse_record(self.backend.files[NAME][0], ENTRY)["version"], 5)
        holder_file = path.parent / "token-relay-computer-id"
        self.assertTrue(holder_file.is_file())
        self.assertTrue(record["updated_by"].endswith("-" + holder_file.read_text(encoding="ascii").strip()))


class FakeBroker:
    def __init__(self, vault_path: Path) -> None:
        self.fields: dict[str, dict[str, str]] = {}
        self.vault_path = vault_path

    def request(self, operation: str, **payload):
        if operation == "get_fields":
            stored = self.fields.get(payload["entry"], {})
            return {name: stored[name] for name in payload["fields"] if name in stored}
        if operation == "set_text":
            self.fields.setdefault(payload["entry"], {})[payload["field"]] = payload["value"]
            return {}
        raise AssertionError(f"unexpected broker operation {operation}")

    def status(self):
        return {"unlocked": True, "vault_path": str(self.vault_path)}


class KeyCommandTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.vault_path = self.folder / "credentials.vault"
        self.broker = FakeBroker(self.vault_path)
        for patch in (
            mock.patch.object(vault_broker_client, "broker_unlocked", lambda: True),
            mock.patch.object(vault_broker_client, "broker_request", self.broker.request),
            mock.patch.object(vault_broker_client, "broker_status", self.broker.status),
            mock.patch("subprocess.run", side_effect=AssertionError("no subprocess may run")),
            mock.patch.dict(os.environ, {}),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            code = token_relay.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def stored(self):
        return self.broker.fields.get("token-relay", {}).get("relay_key")

    def test_key_new_stores_once_and_refuses_to_replace_without_the_flag(self):
        code, out, _ = self.run_main("--vault", str(self.vault_path), "key-new")
        self.assertEqual(code, 0)
        first = self.stored()
        self.assertEqual(len(base64.b64decode(first)), 32)
        self.assertNotIn(first, out)
        code, _, err = self.run_main("key-new")
        self.assertEqual((code, self.stored()), (2, first))
        self.assertIn("--replace", err)
        self.assertEqual(self.run_main("key-new", "--replace")[0], 0)
        self.assertNotEqual(self.stored(), first)

    def test_key_commands_refuse_a_vault_the_agent_does_not_serve(self):
        other = str(self.folder / "other" / "credentials.vault")
        for command in ("key-new", "key-import", "key-export"):
            code, _, err = self.run_main("--vault", other, command)
            self.assertEqual(code, 2)
            self.assertIn("Vault Agent serves", err)
        self.assertIsNone(self.stored())

    def test_review2_finding_6_seed_and_status_refuse_a_vault_the_agent_does_not_serve(self):
        other = str(self.folder / "other" / "credentials.vault")
        for command in (["status"], ["seed", "--entry", ENTRY], ["seed", "--entry", ENTRY, "--replace"]):
            code, out, err = self.run_main("--vault", other, *command)
            self.assertEqual((code, out), (2, ""))
            self.assertIn("Vault Agent serves", err)
        code, out, _ = self.run_main("--vault", str(self.vault_path), "status")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["relay"], "off")

    def test_key_import_refuses_echoed_input_and_stores_a_hidden_one(self):
        def echoed(prompt):
            warnings.warn("cannot hide input", getpass.GetPassWarning)
            return KEY_TEXT

        with mock.patch.object(getpass, "getpass", echoed):
            code, _, err = self.run_main("key-import")
        self.assertEqual((code, self.stored()), (2, None))
        self.assertIn("refusing echoed input", err)
        with mock.patch.object(getpass, "getpass", lambda prompt: KEY_TEXT):
            self.assertEqual(self.run_main("key-import")[0], 0)
        self.assertEqual(self.stored(), KEY_TEXT)

    def test_key_export_prints_only_to_a_terminal(self):
        self.broker.fields["token-relay"] = {"relay_key": KEY_TEXT}
        code, out, err = self.run_main("key-export")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("only to a terminal", err)


if __name__ == "__main__":
    unittest.main()
