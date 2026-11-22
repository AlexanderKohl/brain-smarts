"""Pending-write records, one per write and bound by identity (plan sections L4 and its amendments):
every value a person types (put, the agent's set_text and set_json of a static or grant field)
survives a crash after the local commit through one record; a replay writes under that record,
is checked after its own sync, is saved only when the checkpoint holds its projected identities,
and is held for good when a target changed or the store refused it. A browser authorisation, the
migration's writes and save_settings make no record, and no record holds a token. A bare local
repository is the remote, a fake keyring the keychain and VaultAgent runs in process. Every value
is fictional."""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
import keyring  # noqa: E402

from secret_store import SecretStoreError, envelope, fileio, keys, oauth_ops  # noqa: E402
from secret_store.broker_backend import StoreBackend, put_grant_fields  # noqa: E402
from secret_store.pending import PendingWrites  # noqa: E402
from secret_store.repo import RefusedCommit, SecretRepo  # noqa: E402
from secret_store.store import SecretStore  # noqa: E402
from secret_store.store_ops import build_put  # noqa: E402

FIELD = oauth_ops.DEFAULT_FIELD
VALUE = "fictional-value-not-real"
TYPED = "fictional-typed-before-a-crash"
SECRET = "fictional-client-secret"
TOKEN_KEYS = {"access_token", "refresh_token", "expires_at", "token_type", "id_token"}
_saved_env, _global = {}, None


def setUpModule():
    global _global
    _global = tempfile.TemporaryDirectory()
    cfg = Path(_global.name) / "gitconfig"
    cfg.write_text("[user]\n\tname = Test Person\n\temail = person@example.com\n"
                   "[core]\n\tautocrlf = true\n[init]\n\tdefaultBranch = main\n", "utf-8")
    for key in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM"):
        _saved_env[key] = os.environ.get(key)
    os.environ["GIT_CONFIG_GLOBAL"], os.environ["GIT_CONFIG_NOSYSTEM"] = str(cfg), "1"


def tearDownModule():
    for key, value in _saved_env.items():
        os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
    _global.cleanup()


class FakeKeyring:
    def __init__(self):
        self.items = {}

    def get_password(self, service, user):
        return self.items.get((service, user))

    def set_password(self, service, user, password):
        self.items[(service, user)] = password


class Crash(BaseException):
    """The writing process dies: no handler in the store catches it."""


def typed(store, entry, plain=None, kinds=None, grant=None, group=None):
    """The one function that writes typed values (write_typed); before it existed, the writers."""
    try:
        from secret_store.typed_write import write_typed
    except ImportError:  # commit 33ef494: the command's own calls
        plain, grant = dict(plain or {}), dict(grant or {})
        kinds = kinds or {f: "text" for f in plain}
        if plain and grant:
            return oauth_ops.put_fields(store, entry, plain, grant, group, plain_kinds=kinds)
        if plain:
            return store.put_entry(entry, plain, group=group, field_kinds=kinds)
        return put_grant_fields(store, store._group(group), entry, grant)
    return write_typed(store, entry, plain, kinds, grant, group=group)


def apply(store, write_id):
    try:
        from secret_store.typed_write import apply as run
    except ImportError:
        return store.apply_pending(write_id)
    return run(store, write_id)


class Typed(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.bare = self.root / "remote.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.bare)],
                       check=True, capture_output=True)
        self.fake = FakeKeyring()
        name = f"{FakeKeyring.__module__}.{FakeKeyring.__qualname__}"
        for patcher in (mock.patch.object(keyring, "get_keyring", return_value=self.fake),
                        mock.patch.object(keys, "ALLOWED_BACKENDS", frozenset({name}))):
            patcher.start()
            self.addCleanup(patcher.stop)
        first = self.make_store()
        self.fingerprint = first.init_personal(words_callback=lambda words: True)
        first.put_entry("before", {"api_key": VALUE})
        self.a = self.make_store().open()

    def make_store(self, computer="A"):
        base = self.root / computer
        return SecretStore(use_config_file=False, enabled=True, person="alec", computer=computer,
                           personal_clone=base / "brain-secrets", checkpoint_dir=base / "checkpoint",
                           recovery_package_dir=base / "packages", personal_repo_url=str(self.bare))

    def remote_head(self):
        return subprocess.run(["git", "--git-dir", str(self.bare), "rev-parse", "main"],
                              capture_output=True, check=True).stdout.strip()

    def enrol_b(self):
        from secret_store import enrol
        new = self.make_store("B")
        rid = enrol.request(new, self.fingerprint)
        self.assertEqual(enrol.approve_step(self.make_store().open(), rid), "answered")
        enrol.prove(new, rid, display=lambda _title, _words: True)
        self.assertEqual(enrol.approve_step(self.make_store().open(), rid, display=lambda _t, _w: True), "approved")
        return new.open()

    def pending(self, store=None):
        store = store or self.a
        return PendingWrites(store.config["checkpoint_dir"], store._identity().x25519)

    def push_fails(self, git_real=SecretRepo._git, rc=1):
        def git(repo, *args, **kwargs):
            if args and args[0] == "push":
                return subprocess.CompletedProcess(args, rc, b"", b"fictional failure")
            return git_real(repo, *args, **kwargs)
        return mock.patch.object(SecretRepo, "_git", git)

    def crash_before_push(self):
        real = SecretRepo._git

        def git(repo, *args, **kwargs):
            if args and args[0] == "push":
                raise Crash()
            return real(repo, *args, **kwargs)
        return mock.patch.object(SecretRepo, "_git", git)

    def crash_typed(self, writer=None, call=None, **kw):
        """A typed write in another process of computer A dies after its local commit; one record."""
        writer = writer or self.make_store().open()
        head = self.remote_head()
        with self.crash_before_push(), self.assertRaises(Crash):
            (call or (lambda: typed(writer, **kw)))()
        self.assertEqual(self.remote_head(), head)
        found = self.pending().all()
        self.assertEqual(len(found), 1, "one pending record after the crash")
        return next(iter(found))

    def grant_fields(self, store, entry="xero-demo"):
        return oauth_ops.read_grant(store, oauth_ops.find(store, entry, FIELD))["fields"]

    def assert_no_token_in_records(self, store=None):
        for record in self.pending(store).all().values():
            held = set((record or {}).get("plain", {})) | set((record or {}).get("grant", {})) \
                | set((record or {}).get("fields", {}))
            self.assertFalse(held & TOKEN_KEYS)

    # -- one record per write (L4 rule 1) ------------------------------------------------------
    def test_a_replay_whose_push_is_refused_keeps_one_record_then_a_later_sync_saves_it(self):
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        with self.push_fails():
            for _ in range(3):
                self.a._sync(None, self.a.checkpoint)
                self.assertEqual(list(self.pending().all()), [write_id])  # never grows, same id
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.make_store("A").open().get_record("typed"), {"api_key": TYPED})

    def test_a_change_arriving_during_the_replays_own_sync_is_never_overwritten(self):
        b = self.enrol_b()
        self.a.put_entry("typed", {"api_key": "fictional-first"})
        self.crash_typed(entry="typed", plain={"api_key": TYPED})
        real, done = SecretStore._sync, []

        def sync(store, *args, **kwargs):  # b writes after the state check, before the replay's own sync
            if getattr(store, "_replaying", False) and not done:
                done.append(True)
                b.put_entry("typed", {"api_key": "fictional-from-b"})
            return real(store, *args, **kwargs)
        with mock.patch.object(SecretStore, "_sync", sync):
            self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.make_store().open().get_record("typed"), {"api_key": "fictional-from-b"})
        (record,) = self.pending().all().values()
        self.assertTrue(record.get("held"))

    # -- identity, not revision (L4 rule 2) -------------------------------------------------------
    def test_a_static_entry_deleted_and_made_again_is_held_and_not_overwritten(self):
        b = self.enrol_b()
        self.a.put_entry("typed", {"api_key": "fictional-first"})
        self.crash_typed(entry="typed", plain={"api_key": TYPED})
        b.delete_entry("typed")
        b.put_entry("typed", {"api_key": "fictional-new"})  # a new object at revision 1 again
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.a.get_record("typed"), {"api_key": "fictional-new"})
        (record,) = self.pending().all().values()
        self.assertTrue(record.get("held"))

    def test_a_signin_deleted_and_made_again_is_held_and_the_old_value_not_written(self):
        b = self.enrol_b()
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, {}, {"client_id": "fictional-id"})
        self.crash_typed(entry="xero-demo", grant={"client_secret": SECRET})
        b.delete_entry("xero-demo")
        oauth_ops.put_signin(b, "xero-demo", FIELD, {}, {"client_id": "fictional-new"})
        self.a._sync(None, self.a.checkpoint)
        (record,) = self.pending().all().values()
        self.assertTrue(record.get("held"))
        b._sync(None, b.checkpoint)
        self.assertNotIn("client_secret", self.grant_fields(b))

    def test_an_entry_added_to_the_group_holds_a_record_for_a_new_entry(self):
        b = self.enrol_b()
        self.crash_typed(entry="typed", plain={"api_key": TYPED})
        b.put_entry("other", {"api_key": VALUE})
        self.a._sync(None, self.a.checkpoint)
        self.assertNotIn("typed", self.a.list_entries())
        (record,) = self.pending().all().values()
        self.assertTrue(record.get("held"))

    def test_a_replay_refused_for_want_of_authority_stays_held_until_apply(self):
        from secret_store.accept_rules import RuleRefusal
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        import secret_store.store as store_module
        real = store_module.accept_commit

        def refuse(policy, cp, files, *args, **kwargs):
            if getattr(self.a, "_replaying", False):
                raise RuleRefusal("object x: writer has no authority for this object", "object-authority")
            return real(policy, cp, files, *args, **kwargs)
        with mock.patch.object(store_module, "accept_commit", refuse):
            self.a._sync(None, self.a.checkpoint)
        self.assertTrue(self.pending().all()[write_id].get("held"))
        self.a.put_entry("unrelated", {"api_key": VALUE})  # authority is back: nothing is published by itself
        self.assertNotIn("typed", self.a.list_entries())
        self.assertEqual(apply(self.a, write_id), "typed")
        self.assertEqual(self.a.get_record("typed"), {"api_key": TYPED})
        self.assertEqual(self.pending().all(), {})

    def test_a_first_write_refused_before_any_commit_leaves_no_record(self):
        away = self.bare.with_name("remote-away.git")
        self.bare.rename(away)
        with self.assertRaises(SecretStoreError):
            typed(self.a, "typed", {"api_key": TYPED})
        away.rename(self.bare)
        self.assertEqual(self.pending().all(), {})

    # -- every typed value (L4 rule 3) -------------------------------------------------------------
    def test_a_typed_client_secret_alone_survives_a_crash(self):
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, {}, {"client_id": "fictional-id"})
        self.crash_typed(entry="xero-demo", grant={"client_secret": SECRET})
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.grant_fields(self.a)["client_secret"], SECRET)
        self.assertEqual(self.pending().all(), {})

    def test_typed_plain_and_grant_fields_together_survive_a_crash(self):
        self.crash_typed(entry="xero-demo", plain={"note": VALUE}, grant={"client_secret": SECRET})
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.grant_fields(self.a)["client_secret"], SECRET)
        self.assertEqual(self.a.get_record("xero-demo"), {"note": VALUE})

    def test_the_agents_set_text_of_a_client_secret_survives_a_crash(self):
        writer = StoreBackend(self.make_store().open(), sync_seconds=3600)
        self.crash_typed(call=lambda: writer.set_text("xero-demo", "client_secret", SECRET))
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.grant_fields(self.a)["client_secret"], SECRET)

    def test_a_set_json_field_replayed_after_a_crash_keeps_kind_json(self):
        writer = StoreBackend(self.make_store().open(), sync_seconds=3600)
        self.crash_typed(call=lambda: writer.set_json("settings", "config", {"tenant": "fictional-tenant"}))
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.a.get_typed("settings")[1], {"config": "json"})

    def test_an_authorisation_a_migration_and_save_settings_make_no_record(self):
        agent = StoreBackend(self.a, sync_seconds=3600)
        begun = agent.begin_refresh("xero-demo", FIELD, new_authorisation=True)
        agent.set_json("xero-demo", FIELD, {"access_token": "fictional-access", "refresh_token": "fictional-refresh",
                                            "expires_at": 19 * 10**8, "token_type": "Bearer"},
                       operation=begun["operation"])
        agent.set_json("xero-demo", FIELD, {"tenant": "fictional-tenant"})  # save_settings
        oauth_ops.put_signin(self.a, "migrated", FIELD, {"access_token": "fictional-a", "refresh_token": "fictional-r"},
                             {"client_secret": SECRET})  # the migration's writes, beneath write_typed
        put_grant_fields(self.a, "personal", "migrated-grant", {"client_secret": SECRET})
        self.a.put_entry("migrated-static", {"api_key": VALUE}, field_kinds={"api_key": "text"})
        signin = oauth_ops.find(self.a, "xero-demo", FIELD)  # a refresh answer
        oauth_ops.publish(self.a, signin, {"access_token": "fictional-access-2", "refresh_token": "fictional-r2"},
                          oauth_ops.new_operation())
        self.assertEqual(self.pending().all(), {})
        self.crash_typed(entry="typed", plain={"api_key": TYPED}, grant={"client_secret": SECRET})
        self.assert_no_token_in_records()

    def test_the_agent_makes_a_record_whatever_its_request_carries(self):
        from vault_agent import VaultAgent
        from vault_agent_runtime import AGENT_PROTOCOL_VERSION
        agent = VaultAgent(self.root / "none.vault", store=StoreBackend(self.make_store().open(), sync_seconds=3600))
        request = {"v": AGENT_PROTOCOL_VERSION, "token": agent._auth_token, "op": "set_text", "id": "t",
                   "entry": "typed", "field": "api_key", "value": TYPED, "record": False, "pending": False}
        self.crash_typed(call=lambda: agent.handle(request))

    # -- kinds and isolation (L4 rules 4 and 5) ----------------------------------------------------
    def test_a_record_without_kinds_is_never_applied(self):
        pending = self.pending()
        record = {"id": "abcdefabcdefabcd", "repository": self.a.policy.repository, "group": "personal",
                  "entry": "typed", "fields": {"api_key": TYPED}, "base": None, "time": 1}
        header = {"repository": record["repository"], "group": "personal", "id": record["id"], "kind": "static",
                  "revision": 1}
        me = self.a._identity().x25519
        obj = envelope.seal(record, [(keys.key_id(me.public_key()), me.public_key())], header)
        import json
        fileio.write_durable(pending.path(record["id"]), json.dumps(obj).encode("utf-8"))
        self.a._sync(None, self.a.checkpoint)
        self.assertNotIn("typed", self.a.list_entries())
        with self.assertRaises(SecretStoreError):
            apply(self.a, record["id"])
        self.assertNotIn("typed", self.a.list_entries())
        self.assertIn("without field kinds", self.a.status())

    def test_a_refused_remote_commit_met_during_a_replay_stops_it_and_leaves_the_record(self):
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        before = self.pending().path(write_id).read_bytes()
        side = self.root / "side"
        subprocess.run(["git", "clone", "--quiet", str(self.bare), str(side)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(side), "commit", "--quiet", "--allow-empty", "-m", "update"], check=True,
                       capture_output=True)
        subprocess.run(["git", "-C", str(side), "push", "--quiet", "origin", "main"], check=True, capture_output=True)
        with self.assertRaises(RefusedCommit):
            self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().path(write_id).read_bytes(), before)

    # -- amendments a and b ------------------------------------------------------------------------
    def test_a_legacy_static_object_with_grant_fields_is_replayed_not_called_saved(self):
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, {}, {"client_secret": SECRET})
        a = self.a

        def legacy():  # a static object made before grant fields were refused there
            return build_put(a.policy, a.checkpoint.objects, a._index(None), "xero-demo",
                             {"client_id": "fictional-id", "client_secret": SECRET}, "static",
                             a._identity().ed25519, "personal")
        a._write(legacy)
        self.crash_typed(entry="xero-demo", grant={"client_secret": SECRET})
        self.assertEqual(self.a.get_typed("xero-demo")[0], {"client_id": "fictional-id", "client_secret": SECRET})
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.grant_fields(self.a), {"client_secret": SECRET})
        # the whole transformation: the secret left the static object (a client id is not a grant field)
        self.assertEqual(self.a.get_typed("xero-demo")[0], {"client_id": "fictional-id"})

    def test_a_crash_after_the_push_before_the_removal_is_saved_and_moves_nothing(self):
        real = PendingWrites.remove

        def remove(pending, write_id):
            raise Crash()
        with mock.patch.object(PendingWrites, "remove", remove), self.assertRaises(Crash):
            typed(self.make_store().open(), "typed", {"api_key": TYPED})
        self.assertEqual(len(self.pending().all()), 1)
        head = self.remote_head()
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.remote_head(), head)
        self.assertIsNotNone(real)

    def team(self, computer="T"):
        from secret_store import team as team_ops
        base = self.root / computer
        return team_ops.TeamStore(use_config_file=False, enabled=True, person="alec", computer=computer,
                                  team_clone=base / "team", checkpoint_dir=base / "state",
                                  recovery_package_dir=base / "packages", team_repo_url=str(self.team_bare))

    def indexless(self):
        from secret_store import team as team_ops
        self.team_bare = self.root / "team.git"
        subprocess.run(["git", "init", "--quiet", "--bare", "--initial-branch=main", str(self.team_bare)],
                       check=True, capture_output=True)
        self.team().init_team("example-org", words_callback=lambda words: True,
                              gh=lambda *args: self.fail("gh must not run"))
        held = self.team().open()
        team_ops.create_groups(held, ["ops"])
        head = subprocess.run(["git", "--git-dir", str(self.team_bare), "rev-parse", "main"], capture_output=True,
                              check=True).stdout
        with self.crash_before_push(), self.assertRaises(Crash):
            typed(self.team().open(), "Ops API", {"api_key": TYPED}, group="ops")
        self.assertEqual(subprocess.run(["git", "--git-dir", str(self.team_bare), "rev-parse", "main"],
                                        capture_output=True, check=True).stdout, head)
        self.assertEqual(len(self.pending(held).all()), 1)
        return held, team_ops

    def test_a_first_entry_in_a_group_without_an_index_is_replayed_when_nothing_changed(self):
        held, _ops = self.indexless()
        held._sync(None, held.checkpoint)
        self.assertEqual(self.pending(held).all(), {})
        self.assertEqual(held.get_record("Ops API", "ops"), {"api_key": TYPED})

    def test_a_first_entry_in_a_group_without_an_index_is_held_when_the_policy_changed(self):
        held, team_ops = self.indexless()
        with mock.patch("secret_store.typed_write.replay"):  # another process changes the policy
            team_ops.create_groups(self.team().open(), ["finance"])
        held._sync(None, held.checkpoint)
        self.assertNotIn("Ops API", held.list_entries("ops"))
        (record,) = self.pending(held).all().values()
        self.assertTrue(record.get("held"))

    def test_a_first_entry_in_a_group_without_an_index_is_held_when_an_index_appeared(self):
        held, _ops = self.indexless()
        with mock.patch("secret_store.typed_write.replay"):  # another process makes the group's index
            self.team().open().put_entry("Ops other", {"api_key": VALUE}, group="ops")
        held._sync(None, held.checkpoint)
        self.assertEqual(held.list_entries("ops"), ["Ops other"])
        (record,) = self.pending(held).all().values()
        self.assertTrue(record.get("held"))

    # -- corrections after the conductor's review of 4acda25 ------------------------------------------
    def test_a_value_under_any_field_name_is_stored_and_survives_a_crash(self):
        self.crash_typed(entry="api", plain={"access_token": TYPED})
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.a.get_record("api"), {"access_token": TYPED})
        oauth_ops.put_signin(self.a, "xero-demo", FIELD, {}, {"client_id": "fictional-id"})
        self.crash_typed(entry="xero-demo", grant={"refresh_token": "fictional-typed-grant"})
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.grant_fields(self.a)["refresh_token"], "fictional-typed-grant")
        self.assertEqual(self.pending().all(), {})

    def test_follow_raises_an_integrity_error_for_a_changed_pin_and_an_older_checkpoint(self):
        from secret_store import errors
        older = self.a.checkpoint_path.read_bytes()
        self.make_store().open().put_entry("newer", {"api_key": VALUE})
        self.a._save_pin("0" * 64)
        with self.assertRaises(errors.IntegrityError):
            self.a._follow(clone=True)
        self.a._save_pin(self.a._pinned)
        self.a._follow(clone=True)
        self.a.checkpoint_path.write_bytes(older)
        with self.assertRaises(errors.IntegrityError):
            self.a._follow(clone=True)

    def test_a_replay_meeting_an_integrity_error_while_built_raises_and_leaves_the_record(self):
        from secret_store import errors
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        before = self.pending().path(write_id).read_bytes()
        real = SecretStore.static_payload

        def broken(store, *args, **kwargs):
            if getattr(store, "_replaying", False):
                raise errors.IntegrityError("object x in the local copy does not match the checkpoint")
            return real(store, *args, **kwargs)
        with mock.patch.object(SecretStore, "static_payload", broken), self.assertRaises(errors.IntegrityError):
            self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().path(write_id).read_bytes(), before)
        self.assertFalse(self.pending().all()[write_id]["held"])

    def test_a_checkpoint_that_cannot_be_saved_during_a_replay_stops_it_then_the_record_is_saved(self):
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        first = self.pending().all()[write_id]
        real, failed = SecretStore._save_checkpoint, []

        def save(store, cp):
            if getattr(store, "_replaying", False) and not failed:
                failed.append(True)
                raise OSError("fictional disk failure")
            return real(store, cp)
        with mock.patch.object(SecretStore, "_save_checkpoint", save), self.assertRaises(OSError):
            self.a._sync(None, self.a.checkpoint)
        kept = self.pending().all()[write_id]
        self.assertFalse(kept["held"])
        self.assertEqual({k: v for k, v in kept.items() if k != "projected"},
                         {k: v for k, v in first.items() if k != "projected"})
        head = self.remote_head()
        self.make_store().open()  # the next sync: saved by its projected identities
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.remote_head(), head)

    def test_a_first_write_that_loses_a_conflict_keeps_its_first_record_with_the_second_projection(self):
        real, pushes, writes = SecretRepo._git, [], []
        real_write = PendingWrites.write

        def git(repo, *args, **kwargs):
            if args and args[0] == "push":
                pushes.append(True)
                if len(pushes) == 1:
                    return subprocess.CompletedProcess(args, 1, b"", b"! [rejected] main -> main (fetch first)")
                raise Crash()
            return real(repo, *args, **kwargs)

        def write(pending, record):
            writes.append(dict(record))
            return real_write(pending, record)
        with mock.patch.object(SecretRepo, "_git", git), mock.patch.object(PendingWrites, "write", write), \
                self.assertRaises(Crash):
            typed(self.make_store().open(), "typed", {"api_key": TYPED})
        self.assertEqual(len(writes), 2)
        (record,) = self.pending().all().values()
        self.assertEqual({k: v for k, v in record.items() if k != "projected"},
                         {k: v for k, v in writes[0].items() if k != "projected"})
        self.assertEqual(record["projected"], writes[1]["projected"])
        self.assertNotEqual(writes[0]["projected"], writes[1]["projected"])

    def test_a_first_write_whose_sync_replays_another_record_keeps_its_own(self):
        other = self.crash_typed(entry="other", plain={"api_key": VALUE})
        real, pushes = SecretRepo._git, []

        def git(repo, *args, **kwargs):
            if args and args[0] == "push":
                pushes.append(True)
                if len(pushes) == 2:  # the replay's push lands, the write's own dies
                    raise Crash()
            return real(repo, *args, **kwargs)
        with mock.patch.object(SecretRepo, "_git", git), self.assertRaises(Crash):
            typed(self.make_store().open(), "typed", {"api_key": TYPED})
        found = self.pending().all()
        self.assertNotIn(other, found)
        self.assertEqual(len(found), 1)
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.a.get_record("typed"), {"api_key": TYPED})
        self.assertEqual(self.a.get_record("other"), {"api_key": VALUE})

    # -- round 11, rules 1 and 2: the commit mark, and a record that cannot be written ----------------
    def interrupt_git(self, when):
        """KeyboardInterrupt from the first git call for which when(args, calls) is true; calls lists
        the git subcommands run so far in this test."""
        real, calls = SecretRepo._git, []

        def git(repo, *args, **kwargs):
            if args and when(args, calls):
                calls.append("interrupted")
                raise KeyboardInterrupt()
            calls.append(args[0] if args else "")
            return real(repo, *args, **kwargs)
        return mock.patch.object(SecretRepo, "_git", git)

    def test_an_interrupt_right_after_git_commit_keeps_the_record_and_the_value_is_saved(self):
        b = self.enrol_b()
        writer = self.make_store().open()
        with self.interrupt_git(lambda args, calls: calls and calls[-1] == "commit"), \
                self.assertRaises(KeyboardInterrupt):
            typed(writer, "typed", {"api_key": TYPED})
        self.assertEqual(len(self.pending().all()), 1)
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        b._sync(None, b.checkpoint)
        self.assertEqual(b.get_record("typed"), {"api_key": TYPED})

    def test_an_interrupt_during_the_staging_leaves_no_record_and_a_clean_clone(self):
        writer = self.make_store().open()
        parent = writer.repo.head()
        with self.interrupt_git(lambda args, calls: args[0] == "add"), self.assertRaises(KeyboardInterrupt):
            typed(writer, "typed", {"api_key": TYPED})
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(writer.repo.head(), parent)
        status = subprocess.run(["git", "-C", str(writer.clone), "status", "--porcelain", "--untracked-files=all"],
                                capture_output=True, check=True).stdout
        self.assertEqual(status, b"")

    def test_a_commit_that_is_started_and_fails_keeps_the_record_and_it_is_replayed(self):
        real = SecretRepo._git

        def git(repo, *args, **kwargs):
            if args and args[0] == "commit":
                return subprocess.CompletedProcess(args, 1, b"", b"fictional commit failure")
            return real(repo, *args, **kwargs)
        with mock.patch.object(SecretRepo, "_git", git), self.assertRaises(SecretStoreError):
            typed(self.a, "typed", {"api_key": TYPED})
        self.assertEqual(len(self.pending().all()), 1)
        self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().all(), {})
        self.assertEqual(self.a.get_record("typed"), {"api_key": TYPED})

    def test_a_replays_commit_mark_does_not_leak_into_the_write_that_triggered_it(self):
        other = self.crash_typed(entry="other", plain={"api_key": VALUE})
        # the replay's commit runs first; the write's own staging (an add after that commit) is interrupted
        with self.interrupt_git(lambda args, calls: args[0] == "add" and "commit" in calls), \
                self.assertRaises(KeyboardInterrupt):
            typed(self.make_store().open(), "typed", {"api_key": TYPED})
        self.assertEqual(self.pending().all(), {}, "the replay's record removed, no record of the write's own")
        self.assertNotIn(other, self.pending().all())
        self.assertNotIn("typed", self.make_store().open().list_entries())

    def test_a_record_that_cannot_be_rewritten_during_a_replay_stops_the_sync(self):
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        before = self.pending().path(write_id).read_bytes()
        real = PendingWrites.write

        def write(pending, record):
            if getattr(self.a, "_replaying", False):
                raise OSError("fictional disk full")
            return real(pending, record)
        with mock.patch.object(PendingWrites, "write", write), self.assertRaises(OSError):
            self.a._sync(None, self.a.checkpoint)
        self.assertEqual(self.pending().path(write_id).read_bytes(), before)

    def test_a_push_that_fails_after_the_commit_keeps_the_record_until_the_next_operation(self):
        with self.push_fails(), self.assertRaisesRegex(SecretStoreError, "kept on this computer") as caught:
            typed(self.a, "typed", {"api_key": TYPED})
        self.assertNotIn(TYPED, str(caught.exception))
        self.assertEqual(len(self.pending().all()), 1)
        self.a.put_entry("later", {"api_key": VALUE})
        self.assertEqual(self.make_store().open().get_record("typed"), {"api_key": TYPED})
        self.assertEqual(self.pending().all(), {})

    def test_a_damaged_record_or_one_of_another_store_is_never_applied(self):
        self.a.put_entry("typed", {"api_key": VALUE})
        damaged = self.pending().folder / "abcdefabcdefabcd.pending"
        damaged.parent.mkdir(parents=True, exist_ok=True)
        damaged.write_text("{not json", "utf-8")
        self.a._sync(None, self.a.checkpoint)
        self.assertTrue(damaged.exists())
        self.assertIn("abcdefabcdefabcd on this computer is damaged", self.a.status())

    def test_status_and_unfinished_name_records_without_values(self):
        write_id = self.crash_typed(entry="typed", plain={"api_key": TYPED})
        listed = io.StringIO()
        import importlib.util
        spec = importlib.util.spec_from_file_location("secrets_cli_typed", SCRIPTS / "brain_secrets.py")
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with mock.patch.object(SecretStore, "_sync", lambda *a, **k: None), contextlib.redirect_stdout(listed):
            self.assertEqual(cli.main(["unfinished"], store_factory=self.make_store), 0)
        self.assertIn(write_id, listed.getvalue())
        self.assertNotIn(TYPED, listed.getvalue() + self.a.status())


if __name__ == "__main__":
    unittest.main()
