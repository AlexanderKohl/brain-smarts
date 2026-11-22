"""Unit tests of the rehearsal script's own functions, with fakes only: no keychain, no agent, no
network, no cloud folder. Every file they write is in a temporary folder they remove."""

from __future__ import annotations

import io
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import cleanup  # noqa: E402
import guard  # noqa: E402
import names  # noqa: E402
import rehearse  # noqa: E402
import tls  # noqa: E402
import wrapper  # noqa: E402

SECRET = "invented-value-never-printed"


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cloud = self.root / "cloud"
        self.cloud.mkdir()
        self.names = names.new_names(temp_parent=self.root, cloud_root=self.cloud, run_id="0a1b2c3d")

    def good_probe(self, pc="pc1"):
        n = self.names
        config = names.config_for(n, pc)
        return {
            "root_vault": str(n.brain(pc)), "root_store": str(n.brain(pc)),
            "config": {k: v for k, v in config.items() if k != "enabled"},
            "vault_path": str(n.vault(pc)), "env_vault": None,
            "runtime_base": str(n.home(pc) / ".portable-ai-brain" / "vault-agent"),
            "ipc_address": rf"\\.\pipe\{n.pipe(pc)}",
            "backend": "keyring.backends.Windows.WinVaultKeyring",
            "keychain": {n.keychain_user("pc1"): False, n.keychain_user("pc2"): False},
            "env_secret_names": [], "gh_status": 1,
        }


class NamesTests(Case):
    def test_every_name_carries_the_run_id_and_stays_under_the_run_folder(self):
        n = self.names
        self.assertEqual(n.person, "rehearsal-0a1b2c3d")
        self.assertEqual(n.computer("pc2"), "rehearsal-pc2-0a1b2c3d")
        self.assertEqual(n.keychain_user("pc1"), "rehearsal-0a1b2c3d@rehearsal-pc1-0a1b2c3d")
        self.assertEqual(n.pipe("pc1"), "PortableAIBrainVaultAgent-rehearsal-0a1b2c3d-pc1")
        self.assertEqual(n.recovery_dir, self.cloud / "brain-rehearsal-0a1b2c3d")
        for path in (n.brain("pc1"), n.clone("pc2", "team"), n.checkpoint("pc1"), n.home("pc2"), n.vault("pc1")):
            self.assertTrue(guard.under(path, n.temp), path)

    def test_config_uses_only_known_keys_and_local_remotes(self):
        config = names.config_for(self.names, "pc1")
        self.assertLessEqual(set(config), names.CONFIG_KEYS)
        for key in ("personal_repo_url", "team_repo_url"):
            self.assertNotIn("://", config[key])
            self.assertTrue(guard.under(Path(config[key]), self.names.remotes))

    def test_child_environment_drops_secrets_and_moves_every_home(self):
        base = {"PORTABLE_VAULT_PASSPHRASE": "x", "gh_token": "x", "GITHUB_TOKEN": "x", "Path": "p",
                "HTTPS_PROXY": "http://proxy.example.com:1", "PORTABLE_VAULT_PATH": "x"}
        env = names.child_env(base, self.names, "pc2")
        upper = {k.upper() for k in env}
        for gone in ("PORTABLE_VAULT_PASSPHRASE", "GH_TOKEN", "GITHUB_TOKEN", "HTTPS_PROXY", "PORTABLE_VAULT_PATH"):
            self.assertNotIn(gone, upper)
        self.assertEqual(env["USERPROFILE"], str(self.names.home("pc2")))
        self.assertTrue(env["LOCALAPPDATA"].startswith(str(self.names.home("pc2"))))
        self.assertEqual(env["GH_CONFIG_DIR"], str(self.names.gh_empty))
        self.assertEqual(env["REHEARSAL_PIPE_NAME"], self.names.pipe("pc2"))
        self.assertEqual(env["GIT_AUTHOR_EMAIL"], "rehearsal@example.com")
        self.assertIn("Path", env)


class GuardTests(Case):
    def failed(self, probe, check_mode=False):
        items = guard.evaluate(probe, self.names, "pc1", check_mode=check_mode)
        bad = guard.first_failure(items)
        return bad.number if bad else None

    def test_a_good_probe_passes_every_item(self):
        self.assertIsNone(self.failed(self.good_probe()))
        self.assertEqual([i.number for i in guard.evaluate(self.good_probe(), self.names, "pc1", check_mode=False)],
                         [1, 2, 3, 4, 5, 6])

    def test_item_1_brain_root(self):
        probe = self.good_probe()
        probe["root_store"] = str(self.root / "elsewhere")
        self.assertEqual(self.failed(probe), 1)

    def test_item_2_configuration(self):
        for key, value in (("person", "owner"), ("computer", "laptop"), ("personal_clone", str(self.root.parent)),
                           ("checkpoint_dir", str(self.root.parent / "x")), ("recovery_package_dir", str(self.cloud)),
                           ("team_repo_url", "https://github.example.com/x.git"), ("personal_repo_url", None)):
            probe = self.good_probe()
            probe["config"][key] = value
            self.assertEqual(self.failed(probe), 2, key)
        probe = self.good_probe()
        probe["config"] = {"error": "unreadable"}
        self.assertEqual(self.failed(probe), 2)

    def test_item_2_needs_a_cloud_folder(self):
        n = names.new_names(temp_parent=self.root, cloud_root=None, run_id="0a1b2c3d")
        probe = self.good_probe()
        self.assertEqual(guard.first_failure(guard.evaluate(probe, n, "pc1", check_mode=True)).number, 2)

    def test_item_3_vault_path(self):
        probe = self.good_probe()
        probe["vault_path"] = str(self.root.parent / "credentials.vault")
        self.assertEqual(self.failed(probe), 3)
        probe = self.good_probe()
        probe["env_vault"] = str(self.root.parent / "live.vault")
        self.assertEqual(self.failed(probe), 3)

    def test_item_4_agent_runtime_and_pipe(self):
        probe = self.good_probe()
        probe["ipc_address"] = guard.DEFAULT_PIPE
        self.assertEqual(self.failed(probe), 4)
        probe = self.good_probe()
        probe["runtime_base"] = str(self.root.parent / ".portable-ai-brain")
        self.assertEqual(self.failed(probe), 4)

    def test_item_5_keychain(self):
        probe = self.good_probe()
        probe["backend"] = "keyring.backends.fail.Keyring"
        self.assertEqual(self.failed(probe), 5)
        probe = self.good_probe()
        probe["keychain"][self.names.keychain_user("pc2")] = True
        self.assertEqual(self.failed(probe), 5)
        probe = self.good_probe()
        probe["keychain"] = None  # --check never reads the keychain
        self.assertEqual(self.failed(probe), 5)
        self.assertIsNone(self.failed(probe, check_mode=True))

    def test_item_6_environment_and_gh(self):
        probe = self.good_probe()
        probe["env_secret_names"] = ["GH_TOKEN"]
        self.assertEqual(self.failed(probe), 6)
        probe = self.good_probe()
        probe["gh_status"] = 0
        self.assertEqual(self.failed(probe), 6)
        probe = self.good_probe()
        probe["gh_status"] = None  # gh not installed: nothing can create a repository
        self.assertIsNone(self.failed(probe))

    def test_item_7_baseline_and_its_comparison(self):
        home = self.root / "owner"
        state = home / ".portable-ai-brain" / "vault-agent"
        state.mkdir(parents=True)
        (state / "agent-state.json").write_text('{"pid": 4242, "authkey": "' + SECRET + '"}', "utf-8")
        env = {"USERPROFILE": str(home), "LOCALAPPDATA": str(home / "AppData" / "Local"), "OneDrive": str(self.cloud)}
        before = guard.record_baseline(env)
        self.assertEqual(before["state"]["pid"], 4242)
        self.assertNotIn(SECRET, repr(before))
        self.assertEqual(guard.compare_baseline(before, guard.record_baseline(env)), [])
        (self.cloud / "brain-secrets-recovery").mkdir()
        self.assertEqual(len(guard.compare_baseline(before, guard.record_baseline(env))), 1)
        item = guard.baseline_item(None, "cannot read")
        self.assertEqual((item.number, item.ok), (7, False))


class TlsTests(Case):
    def test_certificate_is_for_loopback_and_trusted_only_by_its_own_context(self):
        cert, key = tls.make_certificate(self.root / "tls")
        self.assertTrue(cert.is_file() and key.is_file())
        self.assertEqual(tls.certificate_hosts(cert), ["127.0.0.1"])
        context = tls.trusted_context(cert)
        self.assertEqual(len(context.get_ca_certs()), 1)
        tls.server_context(cert, key)  # loads without a socket

    def test_handshake_in_memory_succeeds_only_with_the_run_context(self):
        cert, key = tls.make_certificate(self.root / "tls")
        self.assertTrue(tls.memory_handshake(tls.trusted_context(cert), tls.server_context(cert, key)))
        other, _ = tls.make_certificate(self.root / "other")
        self.assertFalse(tls.memory_handshake(tls.trusted_context(other), tls.server_context(cert, key)))

    def test_answers_by_mode(self):
        status, body = tls.answer("token", 3, b"seed")
        self.assertEqual(status, 200)
        self.assertIn(b"access_token", body)
        self.assertEqual(tls.answer("refuse", 1, b"seed"), (400, b'{"error": "invalid_grant"}'))
        self.assertIsNone(tls.answer("hang", 1, b"seed"))
        self.assertEqual(tls.token_hash(3, b"seed"), tls.token_hash(3, b"seed"))
        self.assertNotEqual(tls.token_hash(3, b"seed"), tls.token_hash(4, b"seed"))


class WrapperTests(unittest.TestCase):
    def test_sets_the_pipe_name_and_trusts_only_the_run_certificate(self):
        runtime = types.SimpleNamespace(AGENT_NAME="PortableAIBrainVaultAgent")
        endpoint = types.SimpleNamespace(ssl=__import__("ssl"))
        wrapper.install(runtime, endpoint, "PortableAIBrainVaultAgent-rehearsal-0a1b2c3d-pc1", "ca.pem",
                        context_factory=lambda cafile: ("context", cafile))
        self.assertEqual(runtime.AGENT_NAME, "PortableAIBrainVaultAgent-rehearsal-0a1b2c3d-pc1")
        self.assertEqual(endpoint.ssl.create_default_context(), ("context", "ca.pem"))
        self.assertTrue(hasattr(endpoint.ssl, "PROTOCOL_TLS_CLIENT"))

    def test_refuses_a_missing_or_shared_pipe_name(self):
        for pipe in ("", None, "PortableAIBrainVaultAgent", "something-else"):
            with self.assertRaises(SystemExit):
                wrapper.install(types.SimpleNamespace(AGENT_NAME="x"), types.SimpleNamespace(ssl=None), pipe, None)

    def test_scrub_hides_known_values(self):
        self.assertEqual(wrapper.scrub(f"failed near {SECRET}!", [SECRET]), "failed near [hidden]!")


class CleanupTests(Case):
    def test_only_the_run_users_and_folders_may_be_removed(self):
        n = self.names
        self.assertTrue(cleanup.safe_user(n.keychain_user("pc1"), n))
        for user in ("owner@laptop", "rehearsal-ffffffff@rehearsal-pc1-ffffffff", ""):
            self.assertFalse(cleanup.safe_user(user, n), user)
        self.assertTrue(cleanup.safe_folder(n.temp, n))
        self.assertTrue(cleanup.safe_folder(n.recovery_dir, n))
        for folder in (self.root, self.cloud, self.cloud / "brain-secrets-recovery"):
            self.assertFalse(cleanup.safe_folder(folder, n), folder)

    def test_clean_up_removes_the_run_folder_and_names_what_is_left(self):
        n = self.names
        (n.temp / "pc1").mkdir(parents=True)
        (n.temp / "pc1" / "file.txt").write_text("x", "utf-8")
        deleted = []
        report = cleanup.clean_up(n, check_mode=False, processes=[], delete_user=deleted.append,
                                  user_present=lambda user: user.endswith("pc2-0a1b2c3d"),
                                  pipes=lambda: ["PortableAIBrainVaultAgent-rehearsal-0a1b2c3d-pc1", "other"],
                                  credential_names=lambda: [])
        self.assertFalse(n.temp.exists())
        self.assertEqual(deleted, [n.keychain_user("pc1"), n.keychain_user("pc2")])
        self.assertIn("keychain entry " + n.keychain_user("pc2"), report.left)
        self.assertIn("pipe PortableAIBrainVaultAgent-rehearsal-0a1b2c3d-pc1", report.left)
        self.assertTrue(any("removed" in line for line in report.removed))

    def test_check_mode_never_touches_the_keychain(self):
        def boom(*_a):
            raise AssertionError("keychain touched")
        report = cleanup.clean_up(self.names, check_mode=True, processes=[], delete_user=boom, user_present=boom,
                                  pipes=lambda: [], credential_names=boom)
        self.assertEqual(report.left, [])


class RunTests(Case):
    def run_steps(self, steps, check_mode=True):
        out = io.StringIO()
        cleaned = []
        with redirect_stdout(out):
            code = rehearse.run(steps, lambda: cleaned.append(True) or cleanup.Report([], ["nothing left"]),
                                secrets=[SECRET])
        return code, out.getvalue(), cleaned

    def test_each_step_prints_one_line_and_a_failure_stops_the_run_but_not_the_clean_up(self):
        ran = []

        def ok(name):
            return rehearse.Step(name, lambda: ran.append(name) or "checked " + name)

        def fail():
            raise rehearse.StepFailed("the value " + SECRET + " was wrong")
        code, text, cleaned = self.run_steps([ok("one"), rehearse.Step("two", fail), ok("three")])
        self.assertEqual(code, 1)
        self.assertEqual(ran, ["one"])
        self.assertEqual(cleaned, [True])
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "one: ok – checked one")
        self.assertTrue(lines[1].startswith("two: FAILED – "))
        self.assertNotIn(SECRET, text)
        self.assertNotIn("\u2014", text)

    def test_a_guard_failure_refuses_to_start_naming_the_item(self):
        def guard_step():
            raise rehearse.GuardRefused(guard.Item(4, "agent runtime and pipe", False, "the pipe is the shared one"))
        code, text, cleaned = self.run_steps([rehearse.Step("guard pc1", guard_step), rehearse.Step("x", lambda: "x")])
        self.assertEqual(code, 2)
        self.assertIn("refused to start: guard item 4 (agent runtime and pipe)", text)
        self.assertEqual(cleaned, [True])

    def test_something_left_after_clean_up_exits_non_zero(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = rehearse.run([rehearse.Step("one", lambda: "fine")],
                                lambda: cleanup.Report(["keychain entry x"], []), secrets=[])
        self.assertEqual(code, 3)
        self.assertIn("clean-up: FAILED – left: keychain entry x", out.getvalue())


class SessionProtocolTests(unittest.TestCase):
    def test_one_reply_per_command_and_no_value_in_a_reply(self):
        import steps
        seed = bytes(range(32))
        state = steps.Session(seed)
        lines = [json_line({"seed": seed.hex()}), json_line({"command": "no_such"}),
                 json_line({"command": "marker", "path": state.value("static"), "present": True})]
        out = io.StringIO()
        self.assertEqual(steps.session(io.StringIO("".join(lines)), out), 0)
        replies = [__import__("json").loads(line) for line in out.getvalue().splitlines()]
        self.assertEqual(len(replies), 2)
        self.assertFalse(replies[0]["ok"])
        self.assertIn("unknown command", replies[0]["checked"])
        self.assertFalse(replies[1]["ok"])  # portable_vault is not importable here: fails, reported
        self.assertNotIn(state.value("static"), out.getvalue())

    def test_stale_agent_refusal_needs_both_refusals_and_the_restart_message(self):
        import steps

        class CredentialError(RuntimeError):
            pass

        def fake(answer):
            def broker_request(operation, **_payload):
                if answer(operation) is not None:
                    raise CredentialError(answer(operation))
                return {"fields": {}}
            saved = {k: sys.modules.get(k) for k in ("portable_vault", "vault_broker_client")}
            sys.modules["portable_vault"] = types.SimpleNamespace(CredentialError=CredentialError)
            sys.modules["vault_broker_client"] = types.SimpleNamespace(broker_request=broker_request)
            self.addCleanup(lambda: [sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
                                     for k, v in saved.items()])
        state = steps.Session(b"s" * 32)
        fake(lambda op: "the Vault Agent was started before the secrets store was switched on; restart it")
        self.assertIn("refuses", state.stale_refusal()[0])
        fake(lambda op: None if op == "vault_scrub_signin" else "restart it")
        with self.assertRaises(steps.Failed):
            state.stale_refusal()
        fake(lambda op: "refused")  # get_fields refused without the restart message
        with self.assertRaises(steps.Failed):
            state.stale_refusal()

    def test_values_are_derived_from_the_seed(self):
        import steps
        self.assertEqual(steps.Session(b"a" * 32).value("static"), steps.Session(b"a" * 32).value("static"))
        self.assertNotEqual(steps.Session(b"a" * 32).value("static"), steps.Session(b"b" * 32).value("static"))


class LateRestoreSteps(unittest.TestCase):
    """Plan R11, rules 3 and 5 in the rehearsal: delete --field, a late static field, and the old
    vault's copy after the rollback, with fake product modules (no store, agent or keychain)."""

    def setUp(self):
        import steps
        self.steps = steps
        self.state = steps.Session(bytes(range(32)))
        self.pair = {f"{steps.OLD_SIGNIN}#{steps.SIGNIN_FIELD}", f"{steps.OLD_SIGNIN}#{steps.SIGNIN_FIELD}#grant"}
        self.world = {"names": set(self.pair) | {steps.OLD_SIGNIN},
                      "record": {"value": self.state.value("old-signin-static")}}
        self.seen = []
        self.delete_keeps_signin = self.delete_takes_static = False
        self.vault_fields = {}
        self.migrate_says = ""
        self.fake_modules()

    def fake_modules(self):
        steps, world = self.steps, self.world

        def main(argv, ask=None, confirm=None, **_callbacks):
            self.seen.append((argv, confirm and confirm("prompt")))
            if argv[0] == "delete" and confirm("prompt") == steps.OLD_SIGNIN:
                world["names"] -= set() if self.delete_keeps_signin else self.pair
                if self.delete_takes_static:
                    world["record"].clear()
            elif argv[0] == "put":
                world["record"].update(ask("title", [argv[-1]])[0])
            return 0

        class SecretStore:
            def open(self):
                return self

            def list_entries(self):
                return sorted(world["names"])

            def get_record(self, _entry):
                return dict(world["record"])

        def migrate_main(_argv):
            print(self.migrate_says)
            return 0
        modules = {
            "brain_secrets": types.SimpleNamespace(main=main),
            "secret_store": types.SimpleNamespace(),
            "secret_store.store": types.SimpleNamespace(SecretStore=SecretStore),
            "secret_store.oauth_ops": types.SimpleNamespace(signin_names=lambda e, f: (f"{e}#{f}", f"{e}#{f}#grant")),
            "vault_broker_client": types.SimpleNamespace(broker_request=lambda _op, **_p: {"fields": self.vault_fields}),
            "migrate_to_store": types.SimpleNamespace(main=migrate_main),
        }
        saved = {k: sys.modules.get(k) for k in modules}
        sys.modules.update(modules)
        self.addCleanup(lambda: [sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
                                 for k, v in saved.items()])

    def assert_no_value(self, text):
        for value in self.state.known_values():
            self.assertNotIn(value, text)

    def test_delete_field_removes_the_signin_and_keeps_the_static_field(self):
        checked, _data = self.state.delete_signin()
        self.assertEqual(self.seen, [(["delete", "--entry", self.steps.OLD_SIGNIN, "--field", self.steps.SIGNIN_FIELD],
                                      self.steps.OLD_SIGNIN)])
        self.assertFalse(self.pair & self.world["names"])
        self.assertIn("hash unchanged", checked)
        self.assert_no_value(checked)

    def test_delete_field_fails_when_the_signin_stays_or_the_static_field_goes(self):
        self.delete_keeps_signin = True
        with self.assertRaisesRegex(self.steps.Failed, "still in the store"):
            self.state.delete_signin()
        self.delete_keeps_signin, self.delete_takes_static = False, True
        self.world["names"] |= self.pair
        with self.assertRaisesRegex(self.steps.Failed, "static field"):
            self.state.delete_signin()

    def test_delete_field_needs_the_signin_before_it_runs(self):
        self.world["names"] -= self.pair
        with self.assertRaisesRegex(self.steps.Failed, "before the delete"):
            self.state.delete_signin()
        self.assertEqual(self.seen, [])

    def test_the_late_field_is_stored_and_its_hash_handed_to_the_parent(self):
        self.world["names"] -= self.pair
        checked, data = self.state.put_late()
        self.assertEqual(data["late_hash"], self.steps.digest(self.state.value("late")))
        self.assertEqual(self.seen[0][0], ["put", "--entry", self.steps.OLD_SIGNIN, "--secret", self.steps.SIGNIN_FIELD])
        self.assert_no_value(checked + str(data))

    def test_the_late_field_back_in_the_old_vault_is_compared_by_hash(self):
        self.vault_fields.update({self.steps.SIGNIN_FIELD: self.state.value("late"),
                                  "value": self.state.value("old-signin-static")})
        checked, data = self.state.late_field_back()
        self.assertEqual(data["late_hash"], self.steps.digest(self.state.value("late")))
        self.assert_no_value(checked)
        self.vault_fields[self.steps.SIGNIN_FIELD] = {}  # the scrubbed sign-in, not the store's value
        with self.assertRaisesRegex(self.steps.Failed, "not the store's value"):
            self.state.late_field_back()
        self.vault_fields[self.steps.SIGNIN_FIELD] = self.state.value("late")
        del self.vault_fields["value"]
        with self.assertRaisesRegex(self.steps.Failed, "other static field"):
            self.state.late_field_back()

    def test_the_rollback_dry_run_must_name_the_late_field(self):
        self.migrate_says = "Dry run: ... rehearsal-old-signin (value), rehearsal-old-static (value)"
        with self.assertRaisesRegex(self.steps.Failed, "does not name"):
            self.state.migrate(["rollback", "--dry-run"], names_late=True)
        self.assertIn("returned 0", self.state.migrate(["rollback", "--dry-run"])[0])
        self.migrate_says += f", {self.steps.OLD_SIGNIN} ({self.steps.SIGNIN_FIELD})"
        self.assertIn("names", self.state.migrate(["rollback", "--dry-run"], names_late=True)[0])

    def test_the_parent_compares_the_old_vault_hash_with_the_stores(self):
        r = rehearse.Rehearsal(False, "HEAD", environ={})
        r.recheck = lambda _pc: None
        replies = {"put_late": {"checked": "stored", "data": {"late_hash": "a" * 64}},
                   "late_field_back": {"checked": "back", "data": {"late_hash": "b" * 64}}}
        r.once = lambda _pc, command, **_kw: replies[command]
        by_name = {step.name: step for step in r.full_steps()}
        by_name["step 7 late static field"].action()
        with self.assertRaises(rehearse.StepFailed):
            by_name["step 7 late field back"].action()
        replies["late_field_back"]["data"]["late_hash"] = "a" * 64
        self.assertIn("by hash", by_name["step 7 late field back"].action())


STEP_7_TAIL = ["step 7 store-on refusal", "step 7 delete --field", "step 7 late static field",
               "step 7 agent on the old vault again", "step 7 unlock again", "step 7 store on again",
               "step 7 rollback dry run", "step 7 marker before the rollback", "step 7 rollback",
               "step 7 marker cleared", "step 7 store off", "step 7 static back", "step 7 late field back"]


class ModeTests(unittest.TestCase):
    def test_check_runs_no_step_that_touches_the_keychain_a_process_or_the_cloud_folder(self):
        check = [s.name for s in rehearse.Rehearsal(True, "HEAD", environ={}).steps()]
        self.assertEqual(check, ["guard item 7: owner baseline", "prepare", "certificate", "guard pc1", "guard pc2"])
        full = [s.name for s in rehearse.Rehearsal(False, "HEAD", environ={}).steps()]
        self.assertEqual(full[:5], check)
        self.assertTrue(any(name.startswith("step 7") for name in full))

    def test_the_new_steps_close_step_7_in_order(self):
        full = [s.name for s in rehearse.Rehearsal(False, "HEAD", environ={}).steps()]
        self.assertEqual(full[-len(STEP_7_TAIL):], STEP_7_TAIL)
        self.assertLess(full.index("step 7 migrate"), full.index("step 7 delete --field"))

    def test_check_lists_the_full_run_steps_and_runs_none_of_them(self):
        def forbidden(*_args, **_kwargs):
            raise AssertionError("a full-run step was run or prepared in --check")
        saved = (rehearse.run, rehearse.tls.free_closed_port, rehearse.subprocess.Popen)
        rehearse.run = lambda steps, _clean: 0 if [s.name for s in steps][-1] == "guard pc2" else 9
        rehearse.tls.free_closed_port = rehearse.subprocess.Popen = forbidden
        self.addCleanup(lambda: setattr(rehearse, "run", saved[0]) or setattr(rehearse.tls, "free_closed_port", saved[1])
                        or setattr(rehearse.subprocess, "Popen", saved[2]))
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(rehearse.main(["--check"]), 0)
        listed = [line.split(": ", 1)[1] for line in out.getvalue().splitlines()
                  if line.startswith("full run only, not run with --check: ")]
        self.assertEqual(listed[-len(STEP_7_TAIL):], STEP_7_TAIL)


class GuardStepTests(Case):
    def rehearsal(self, probe):
        r = rehearse.Rehearsal(True, "HEAD", environ={})
        r.n = self.names
        r.probe = lambda pc, full: probe
        return r

    def test_guard_step_refuses_naming_the_item_and_needs_the_wrapper_trust(self):
        probe = self.good_probe()
        probe["token_trust"] = 1
        self.assertIn("items 1-6 hold", self.rehearsal(probe).guard_step("pc1"))
        probe["token_trust"] = 140  # the system store: the wrapper did not take effect
        with self.assertRaises(rehearse.StepFailed):
            self.rehearsal(probe).guard_step("pc1")
        probe["ipc_address"] = guard.DEFAULT_PIPE
        with self.assertRaises(rehearse.GuardRefused) as refused:
            self.rehearsal(probe).guard_step("pc1")
        self.assertEqual(refused.exception.item.number, 4)


def json_line(value):
    return __import__("json").dumps(value) + "\n"


if __name__ == "__main__":
    unittest.main()
