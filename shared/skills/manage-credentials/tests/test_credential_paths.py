"""Follow-up plan F3.1 (round-9 row M11): every call of broker_request, every PortableVault( and
every migration= keyword in scripts/ is on a reviewed list. A new caller fails this test until
someone reviews it, adds it to REVIEWED with one line saying why it may call, and lists it in
CREDENTIAL-PATHS.md. Counts are per function, so a second call inside a listed function fails too.

What is found, by reading the source (ast), never by running it:
- "broker_request": a call of broker_request or of a stored _broker_request
- "broker_request passed": the function named without being called (passed on, stored, aliased)
- "PortableVault(": a call of PortableVault, the class whose load decrypts the vault
- "PortableVault passed": the class named without being called, outside imports and annotations
- "migration=": a migration keyword whose value is not the literal False (the store-on passphrase open)
- "name in a string": a string that is exactly one of the watched names (getattr and the like)
Any other file type under scripts/ may not hold the names at all."""
import ast
import re
import shutil
import tempfile
import unittest
from collections import Counter
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
PATHS_FILE = SKILL / "CREDENTIAL-PATHS.md"
BROKER = {"broker_request", "_broker_request"}
WATCHED = BROKER | {"PortableVault"}
TEXT = re.compile(r"broker_request|PortableVault|migration\s*=\s*True")

# (file under scripts/, enclosing function, what) -> (how many, why it may call)
REVIEWED: dict[tuple[str, str, str], tuple[int, str]] = {
    ("migrate_to_store.py", "main", "broker_request passed"): (
        2, "migrate and rollback reach the agent's vault, scrub and marker operations only through it, "
           "under the migration lock"),
    ("portable_vault.py", "BrokerOAuthStore.__init__", "PortableVault("): (
        1, "path only: names the store and its local rotation lock; reads and writes go through the agent"),
    ("portable_vault.py", "BrokerOAuthStore.__init__", "broker_request"): (
        2, "ping, and with the store on status: a vault-only agent is refused"),
    ("portable_vault.py", "BrokerOAuthStore.__init__", "broker_request passed"): (
        1, "keeps the broker function for the store's own calls below"),
    ("portable_vault.py", "BrokerOAuthStore.clear", "broker_request"): (
        1, "clear_signin: the agent checks the marker, the store switch and the refresher"),
    ("portable_vault.py", "BrokerOAuthStore.load", "broker_request"): (
        1, "get_json of one sign-in: the agent answers by role and refuses a migrated field"),
    ("portable_vault.py", "BrokerOAuthStore.save", "broker_request"): (
        1, "set_json of one sign-in, with the journalled operation in store mode"),
    ("portable_vault.py", "BrokerOAuthStore.store_mode", "broker_request"): (
        1, "status only, to learn whether the agent serves the store"),
    ("portable_vault.py", "BrokerOAuthStore.sync_store", "broker_request"): (
        1, "sync_store: the agent pulls the store; no credential is returned"),
    ("portable_vault.py", "PortableVaultJsonStore.__init__", "PortableVault("): (
        1, "the passphrase fallback's vault; its open refuses while the store is on"),
    ("secret_store/broker_backend.py", "agent_operation", "migration="): (
        1, "opens the old vault in store mode only while migrate_to_store.py holds a live migration lock"),
    ("token_relay.py", "_check_vault", "PortableVault("): (
        1, "path only: compares --vault with the vault the running agent serves"),
    ("token_relay.py", "_store_key", "broker_request"): (
        1, "key-import stores the relay key through the agent; refused in store mode before this"),
    ("token_relay.py", "config_candidates", "PortableVault("): (
        1, "path only: where token-relay.json may sit; the vault is never opened"),
    ("token_relay.py", "config_path", "PortableVault("): (
        1, "path only: token-relay.json beside the vault"),
    ("token_relay.py", "main", "PortableVault("): (
        1, "path only: reads the migration marker beside the vault, never the vault"),
    ("token_relay.py", "read_relay_key", "broker_request"): (
        1, "the relay key through the agent; no relay is built while the store is on"),
    ("token_relay_store.py", "holder_name", "PortableVault("): (
        1, "path only: the non-secret computer id file beside the vault"),
    ("vault_agent.py", "VaultAgent.__init__", "PortableVault("): (
        1, "the agent's vault; a vault-backed agent refuses every credential request while the store is on"),
    ("vault_agent.py", "VaultAgent.unlock", "PortableVault("): (
        1, "checks the passphrase without keeping a wrong one; in store mode only for migration and rollback"),
    ("vault_agent.py", "VaultAgent.unlock", "migration="): (
        1, "store mode only: the passphrase is held for the migration and rollback operations"),
    ("vault_broker_client.py", "_wait_for_refresher", "broker_request"): (
        1, "poll_refresh: waits for the refresher to publish, never calls the provider"),
    ("vault_broker_client.py", "broker_status", "broker_request"): (
        1, "status of the agent, no credential"),
    ("vault_broker_client.py", "store_refresh", "broker_request"): (
        1, "begin_refresh: the journalled refresh lock in the agent"),
    ("vault_broker_client.py", "store_refresh.end", "broker_request"): (
        1, "abort_refresh or release_refresh of the journalled refresh"),
    ("vault_credentials.py", "_put_entry_window", "broker_request"): (
        2, "put-entry --window writes typed values through the unlocked agent, which refuses a vault "
           "backend while the store is on"),
    ("vault_credentials.py", "_try_broker_fields", "broker_request"): (
        2, "run and session: the store agent is required, then static fields only"),
    ("vault_credentials.py", "main", "PortableVault("): (
        1, "the command's vault; every passphrase open refuses while the store is on"),
    ("vault_credentials.py", "main", "broker_request"): (
        1, "put through the unlocked agent, which refuses a vault backend while the store is on"),
    ("vaultctl.py", "_mapped_environment", "broker_request"): (
        1, "run: static fields, after main required the store agent"),
    ("vaultctl.py", "main", "broker_request"): (
        4, "unlock, lock, access-token and secret-put; the store agent is required except for unlock and lock"),
}


class _Finder(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel, self.scope, self.found, self.skip = rel, [], Counter(), set()

    def add(self, kind: str) -> None:
        self.found[(self.rel, ".".join(self.scope) or "<module>", kind)] += 1

    def _scoped(self, node):
        self.scope.append(node.name)
        for annotation in _annotations(node):
            self.skip.update(id(n) for n in ast.walk(annotation))
        self.generic_visit(node)
        self.scope.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = visit_ClassDef = _scoped

    def visit_AnnAssign(self, node):
        self.skip.update(id(n) for n in ast.walk(node.annotation))
        self.generic_visit(node)

    def visit_Call(self, node):
        name = _name(node.func)
        if name in BROKER:
            self.add("broker_request")
            self.skip.add(id(node.func))
        elif name == "PortableVault":
            self.add("PortableVault(")
            self.skip.add(id(node.func))
        for keyword in node.keywords:
            if keyword.arg == "migration" and not (isinstance(keyword.value, ast.Constant)
                                                   and keyword.value.value is False):
                self.add("migration=")
        self.generic_visit(node)

    def visit_Name(self, node):
        self._reference(node, node.id)

    def visit_Attribute(self, node):
        self._reference(node, node.attr)
        self.generic_visit(node)

    def _reference(self, node, name):
        if name in WATCHED and id(node) not in self.skip and isinstance(node.ctx, ast.Load):
            self.add(("broker_request" if name in BROKER else "PortableVault") + " passed")

    def visit_alias(self, node):
        if node.name.split(".")[-1] in WATCHED and node.asname not in (None, node.name.split(".")[-1]):
            self.add("broker_request passed" if node.name.split(".")[-1] in BROKER else "PortableVault passed")

    def visit_Constant(self, node):
        if isinstance(node.value, str) and node.value.strip() in WATCHED:
            self.add("name in a string")


def _name(node) -> str | None:
    return node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else None


def _annotations(node):
    if isinstance(node, ast.ClassDef):
        return []
    args = node.args
    every = args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
    return [a.annotation for a in every if a.annotation is not None] + ([node.returns] if node.returns else [])


def scan(root: Path) -> Counter:
    """Every watched use under root, keyed (file, function, what). A file that does not parse, or a
    non-Python file holding a watched name, is reported as a use of its own."""
    found = Counter()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        rel = path.relative_to(root).as_posix()
        if path.suffix != ".py":
            try:
                text = path.read_text("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if TEXT.search(text):
                found[(rel, "<file>", "watched name in a non-Python file")] += 1
            continue
        try:
            tree = ast.parse(path.read_text("utf-8"), filename=str(path))
        except SyntaxError:
            found[(rel, "<file>", "does not parse")] += 1
            continue
        finder = _Finder(rel)
        finder.visit(tree)
        found.update(finder.found)
    return found


def differences(found: Counter, reviewed=None) -> list[str]:
    reviewed = REVIEWED if reviewed is None else reviewed
    problems = []
    for key in sorted(set(found) | set(reviewed)):
        have, want = found.get(key, 0), reviewed.get(key, (0, ""))[0]
        if have != want:
            problems.append(f"{key[0]} {key[1]} {key[2]}: found {have}, reviewed {want}")
    return problems


class CredentialCallers(unittest.TestCase):
    def test_every_caller_is_on_the_reviewed_list(self):
        problems = differences(scan(SCRIPTS))
        self.assertEqual(problems, [], "\nA credential caller is not on the reviewed list. Review it, then add it to "
                                       "REVIEWED with its reason and to CREDENTIAL-PATHS.md:\n" + "\n".join(problems))

    def test_every_reviewed_caller_has_a_reason_and_is_in_the_paths_file(self):
        text = PATHS_FILE.read_text("utf-8")
        for (rel, function, kind), (count, why) in REVIEWED.items():
            self.assertGreater(count, 0, (rel, function, kind))
            self.assertGreater(len(why.split()), 3, f"{rel} {function}: give the reason in a line")
            self.assertIn(f"`{rel}` `{function}`", text, f"{rel} {function} is missing from CREDENTIAL-PATHS.md")


class TheCheckCatchesANewCaller(unittest.TestCase):
    """A copy of scripts/ with one added use: the check reports it. Each watched form once."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="credential-paths-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        shutil.copytree(SCRIPTS, self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.scripts = self.root / "scripts"

    def add(self, name, text):
        path = self.scripts / name
        path.write_text(path.read_text("utf-8") + "\n\n" + text + "\n", encoding="utf-8")
        return differences(scan(self.scripts))

    def test_the_copy_matches_before_any_change(self):
        self.assertEqual(differences(scan(self.scripts)), [])

    def test_a_new_broker_request(self):
        problems = self.add("vault_tray.py", "def read_more():\n    from vault_broker_client import broker_request\n"
                                             "    return broker_request('get_fields', entry='x', fields=['y'])")
        self.assertEqual(problems, ["vault_tray.py read_more broker_request: found 1, reviewed 0"])

    def test_a_second_call_in_a_listed_function(self):
        path = self.scripts / "vaultctl.py"
        text = path.read_text("utf-8")
        anchor = '        if args.operation == "lock":\n'
        self.assertIn(anchor, text)
        path.write_text(text.replace(anchor, '            broker_request("lock")\n' + anchor, 1), encoding="utf-8")
        self.assertEqual(differences(scan(self.scripts)), ["vaultctl.py main broker_request: found 5, reviewed 4"])

    def test_a_new_portable_vault(self):
        problems = self.add("vault_tray.py", "def open_it(path):\n    return PortableVault(path).load('x')")
        self.assertEqual(problems, ["vault_tray.py open_it PortableVault(: found 1, reviewed 0"])

    def test_a_new_migration_true(self):
        problems = self.add("vault_tray.py", "def open_it(cls, path):\n    return cls(path, migration=True)")
        self.assertEqual(problems, ["vault_tray.py open_it migration=: found 1, reviewed 0"])

    def test_hidden_forms(self):
        problems = self.add("vault_tray.py", "from vault_broker_client import broker_request as ask\n"
                                             "def sneak(module):\n    return getattr(module, 'PortableVault')")
        self.assertEqual(problems, ["vault_tray.py <module> broker_request passed: found 1, reviewed 0",
                                    "vault_tray.py sneak name in a string: found 1, reviewed 0"])

    def test_a_non_python_file(self):
        (self.scripts / "helper.ps1").write_text("python -c \"PortableVault(None)\"\n", encoding="utf-8")
        self.assertEqual(differences(scan(self.scripts)),
                         ["helper.ps1 <file> watched name in a non-Python file: found 1, reviewed 0"])


if __name__ == "__main__":
    unittest.main()
