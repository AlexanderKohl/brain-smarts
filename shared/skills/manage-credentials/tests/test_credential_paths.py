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
Any other file type under scripts/ may not hold the names at all.

Follow-up plan K.3: when the brain holds a library (/library/skills/*/scripts, found from the brain
root above this skill), every connector's scripts are scanned for the same names against
LIBRARY_REVIEWED, keyed "<skill>/scripts/<file>". Test files there (a tests folder or a test_*.py
file) are left out: they hold fakes and refusal checks, not credential paths. Without a library the
library test is skipped with a message.

Follow-up plan R11, rule 6 (parts a to d), the classes from InsideTheStore down: the tables of
credential_inventory.py (CREDENTIAL-PATHS.md, section "Inside the store") against the source as
credential_scan.py reads it: the closed list of external modules and the exact symbols each skill
module takes from a data-carrying one; the forms that need no import; the library symbols beneath
the primitives and sinks; every direct caller of a primitive or sink (a reference counts); every
module in exactly one table, a no-credential module importing from a credential module only what
its exemption row allows; every public operation of every parser and of the agent. Each check is
shown failing on a copy of scripts/ with one change, or on a patched table, never on a file added
to the skill. The runtime recorder is tests/test_credential_paths_runtime.py."""
import hermetic  # noqa: F401 (first: plan R24, tests/hermetic.py)
import ast
import re
import shutil
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import credential_inventory as inventory  # noqa: E402
import credential_scan as scan_module  # noqa: E402

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL / "scripts"
PATHS_FILE = SKILL / "CREDENTIAL-PATHS.md"
LIBRARY = SKILL.parent.parent.parent / "library" / "skills"  # the brain root's library
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
    ("secret_store/broker_backend.py", "vault_request", "migration="): (
        1, "the verify-copy backup inherits the given vault's permission: under a live migration lock only"),
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

# ("<skill>/scripts/<file>", enclosing function, what) -> (how many, why it may call)
LIBRARY_REVIEWED: dict[tuple[str, str, str], tuple[int, str]] = {
    ("abr-access/scripts/abr_import_guid_from_gmail.py", "_store_guid", "PortableVault("): (
        1, "the passphrase fallback writes the GUID text field; its open refuses while the store is on"),
    ("abr-access/scripts/abr_import_guid_from_gmail.py", "_store_guid", "broker_request"): (
        1, "set_text of the GUID through the unlocked agent, which routes it to the store when on"),
    ("gohighlevel-access/scripts/ghl_oauth/vault_store.py", "_credential_modules", "PortableVault passed"): (
        1, "returns the class to _vault_static_fields below; no vault is opened here"),
    ("gohighlevel-access/scripts/ghl_oauth/vault_store.py", "_vault_static_fields", "PortableVault("): (
        1, "the passphrase fallback for static fields; its open refuses while the store is on"),
    ("gohighlevel-access/scripts/ghl_oauth/vault_store.py", "_vault_static_fields", "broker_request"): (
        1, "get_fields of static fields; off the refresher a client secret is refused by the agent"),
    ("google-workspace-access/scripts/google_oauth/client.py", "client_from_vault", "broker_request"): (
        2, "get_fields of the client ID and secret, then the client ID alone when the agent says the "
           "secret lives on the refresher"),
    ("google-workspace-access/scripts/google_tray_token.py", "_broker", "broker_request passed"): (
        1, "imports the agent client and hands it to the two tray functions below"),
    ("google-workspace-access/scripts/google_tray_token.py", "_refresh_under_lock", "broker_request"): (
        1, "get_fields of the client ID and secret inside the store's rotation lock, on the refresher"),
    ("google-workspace-access/scripts/google_tray_token.py", "load_tray_access_token", "broker_request"): (
        1, "get_json of the account's sign-in: the agent answers by role and refuses a migrated field"),
    ("google-workspace-access/scripts/google_tray_token.py", "refresh_tray_access_token", "broker_request passed"): (
        1, "passes the agent client to _refresh_under_lock; no call of its own"),
    ("linkedin-access/scripts/linkedin_client.py", "vault_static_fields", "broker_request"): (
        1, "get_fields of static fields through the unlocked agent; no passphrase fallback"),
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


def _test_file(rel: str) -> bool:
    parts = rel.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


def scan_library(library: Path) -> Counter:
    """scan() of every /library/skills/<skill>/scripts folder, test files left out, keyed
    ("<skill>/scripts/<file>", function, what)."""
    found = Counter()
    for scripts in sorted(p for p in library.glob("*/scripts") if p.is_dir()):
        for (rel, function, kind), count in scan(scripts).items():
            if not _test_file(rel):
                found[(f"{scripts.parent.name}/scripts/{rel}", function, kind)] += count
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


class LibraryCallers(unittest.TestCase):
    def test_every_library_caller_is_on_the_reviewed_list(self):
        if not LIBRARY.is_dir():
            self.skipTest(f"no library at {LIBRARY}: the connectors' credential paths are checked where the "
                          "brain holds /library/skills")
        problems = differences(scan_library(LIBRARY), LIBRARY_REVIEWED)
        self.assertEqual(problems, [], "\nA library credential caller is not on the reviewed list. Review it, then "
                                       "add it to LIBRARY_REVIEWED with its reason and to CREDENTIAL-PATHS.md:\n"
                                       + "\n".join(problems))

    def test_every_reviewed_library_caller_has_a_reason_and_is_in_the_paths_file(self):
        text = PATHS_FILE.read_text("utf-8")
        for (rel, function, kind), (count, why) in LIBRARY_REVIEWED.items():
            self.assertGreater(count, 0, (rel, function, kind))
            self.assertGreater(len(why.split()), 3, f"{rel} {function}: give the reason in a line")
            self.assertIn(f"`{rel}` `{function}`", text, f"{rel} {function} is missing from CREDENTIAL-PATHS.md")

    def test_a_new_caller_in_a_copied_library_is_reported_and_test_files_are_not(self):
        if not LIBRARY.is_dir():
            self.skipTest(f"no library at {LIBRARY}")
        root = Path(tempfile.mkdtemp(prefix="credential-paths-library-"))
        self.addCleanup(shutil.rmtree, root, True)
        for scripts in LIBRARY.glob("*/scripts"):
            shutil.copytree(scripts, root / scripts.parent.name / "scripts",
                            ignore=shutil.ignore_patterns("__pycache__"))
        self.assertEqual(differences(scan_library(root), LIBRARY_REVIEWED), [])
        target = root / "linkedin-access" / "scripts"
        (target / "tests").mkdir(exist_ok=True)
        (target / "tests" / "test_extra.py").write_text("PortableVault(None)\n", encoding="utf-8")
        (target / "extra.py").write_text("def more():\n    return broker_request('get_fields')\n", encoding="utf-8")
        self.assertEqual(differences(scan_library(root), LIBRARY_REVIEWED),
                         ["linkedin-access/scripts/extra.py more broker_request: found 1, reviewed 0"])


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


# -- R11 rule 6: the inventory against the source -------------------------------------------------------
ENDPOINT_KEYS = {(module, scope): endpoint_id for endpoint_id, (module, scope, _k, _w) in inventory.ENDPOINTS.items()}
TERMINAL_FORMS = ("print", "sys-stream", "sys-stream-write")


def scan_inventory(scripts: Path, tables=inventory):
    return scan_module.scan(scripts, ENDPOINT_KEYS, tables.METHOD_NAMES, set(tables.LIBRARY_SYMBOLS))


def module_problems(skill, tables=inventory) -> list[str]:
    """(d) every module in exactly one table; no table row for a module that is not there."""
    problems, modules = [], set(skill.modules) | set(skill.unparsable)
    for rel in sorted(modules):
        places = (rel in tables.CREDENTIAL) + (rel in tables.NO_CREDENTIAL)
        if places != 1:
            problems.append(f"{rel}: in {'both tables' if places else 'neither table'}")
    for rel in sorted((set(tables.CREDENTIAL) | set(tables.NO_CREDENTIAL)) - modules):
        problems.append(f"{rel}: in a table but not under scripts/")
    return problems


def external_problems(findings, tables=inventory) -> list[str]:
    """(a) the closed list, and the exact symbols per data-carrying module and skill module."""
    problems = []
    for (module, rel), symbols in sorted(findings.external.items()):
        top = module.split(".")[0]
        if top not in tables.EXTERNAL_MODULES:
            problems.append(f"{rel}: imports {module}, which is not on the closed list")
        if top in tables.DATA_CARRYING:
            allowed = set(tables.EXTERNAL_SYMBOLS.get((module, rel), ()))
            if (module, rel) not in tables.EXTERNAL_SYMBOLS:
                problems.append(f"{rel}: imports {module}, not allowed there (symbols {sorted(symbols)})")
            elif set(symbols) != allowed:
                problems.append(f"{rel}: takes from {module} {sorted(set(symbols) - allowed)} beyond, "
                                f"{sorted(allowed - set(symbols))} short of its row")
            if rel in tables.NO_CREDENTIAL and (module, rel) not in tables.NO_CREDENTIAL_EXTERNAL:
                problems.append(f"{rel}: a no-credential module with {module}: say why in NO_CREDENTIAL_EXTERNAL")
    for key in sorted(set(tables.EXTERNAL_SYMBOLS) - set(findings.external)):
        problems.append(f"{key[1]}: the row for {key[0]} names an import the code no longer has")
    return problems


def form_problems(findings, tables=inventory) -> list[str]:
    """(a) print, input, stdin, environment and file writes, reflection, the passphrase variable."""
    found = {form: set(sites) for form, sites in findings.forms.items() if form not in TERMINAL_FORMS}
    found["terminal"] = set().union(*(findings.forms.get(f, set()) for f in TERMINAL_FORMS))
    problems = []
    for form in sorted(set(found) | set(tables.FORMS)):
        have, allowed = found.get(form, set()), set(tables.FORMS.get(form, ()))
        for rel, scope in sorted(have - allowed):
            problems.append(f"{rel} {scope}: {form}, not allowed there")
        for rel, scope in sorted(allowed - have):
            problems.append(f"{rel} {scope}: allowed {form} but no longer uses it")
    return problems


def library_problems(findings, tables=inventory) -> list[str]:
    """(b) the cipher, keychain, prompt, window, pipe and key-material symbols outside their functions."""
    problems = []
    for attribute in sorted(set(findings.library) | set(tables.LIBRARY_SYMBOLS)):
        have, allowed = findings.library.get(attribute, set()), set(tables.LIBRARY_SYMBOLS.get(attribute, ()))
        for rel, scope in sorted(have - allowed):
            problems.append(f"{rel} {scope}: uses {attribute} outside a listed primitive or sink")
        for rel, scope in sorted(allowed - have):
            problems.append(f"{rel} {scope}: listed for {attribute} but no longer uses it")
    return problems


def caller_problems(findings, tables=inventory) -> list[str]:
    """(b) every function that calls or names a primitive or sink is a reviewed direct caller."""
    problems = []
    for key, endpoint_id in sorted(ENDPOINT_KEYS.items(), key=lambda item: item[1]):
        have, reviewed = findings.references.get(key, set()), set(tables.DIRECT_CALLERS.get(endpoint_id, {}))
        for rel, scope in sorted(have - reviewed):
            problems.append(f"{rel} {scope}: calls or names {endpoint_id} ({key[1]}) and is not a reviewed caller")
        for rel, scope in sorted(reviewed - have):
            problems.append(f"{rel} {scope}: reviewed caller of {endpoint_id} but no longer names it")
    for rel, scope, name in sorted(findings.string_names):
        if (rel, scope, name) not in tables.STRING_EXEMPT:
            problems.append(f"{rel} {scope}: the string {name!r} names a primitive or sink")
    return problems


def import_problems(findings, tables=inventory) -> list[str]:
    """(d) a no-credential module imports from a credential module only what its exemption row allows."""
    problems, seen = [], set()
    for (importer, imported), names in sorted(findings.skill_imports.items()):
        if importer not in tables.NO_CREDENTIAL or imported not in tables.CREDENTIAL:
            continue
        taken = (set(names) - {"*"}) | set(findings.skill_uses.get((importer, imported), ()))
        allowed = set(tables.EXEMPT_IMPORTS.get((importer, imported), ((), ""))[0])
        seen.add((importer, imported))
        if taken - allowed:
            problems.append(f"{importer}: a no-credential module takes {sorted(taken - allowed)} from {imported}")
        if allowed - taken:
            problems.append(f"{importer}: the exemption for {imported} names {sorted(allowed - taken)}, no longer used")
    for key in sorted(set(tables.EXEMPT_IMPORTS) - seen):
        problems.append(f"{key[0]}: an exemption for {key[1]}, which it does not import, or a module changed table")
    return problems


def operation_problems(findings, tables=inventory) -> list[str]:
    """(c) every parser and every subcommand; every name the agent dispatches on; every id used exists."""
    problems = []
    parsers = set(findings.parsers) | {"agent"}
    for parser in sorted(parsers | set(tables.OPERATIONS)):
        if parser not in tables.OPERATIONS:
            problems.append(f"{parser}: a parser the list does not name")
            continue
        if parser not in parsers:
            problems.append(f"{parser}: in the list but has no parser")
            continue
        found = set(findings.operations.get(parser, set())) or {"(the tray)" if parser == "vault_tray.py" else "(the command)"}
        listed = set(tables.OPERATIONS[parser])
        for operation in sorted(found - listed):
            problems.append(f"{parser} {operation}: an operation the list does not name")
        for operation in sorted(listed - found):
            problems.append(f"{parser} {operation}: in the list, not in the code")
        for operation, (uses, may, _scenario, _note) in tables.OPERATIONS[parser].items():
            for endpoint_id in set(uses) | set(may):
                if endpoint_id not in tables.ENDPOINTS:
                    problems.append(f"{parser} {operation}: uses unknown endpoint {endpoint_id}")
    return problems


def endpoint_problems(skill, tables=inventory) -> list[str]:
    """Every primitive and sink of the table is defined where the table says."""
    problems = []
    for endpoint_id, (rel, scope, kind, _what) in tables.ENDPOINTS.items():
        info = skill.modules.get(rel)
        head = scope.split(".")[0]
        if info is None or head not in info.defs:
            problems.append(f"{endpoint_id}: {rel} does not define {scope}")
        elif "." in scope and scope.split(".")[1] not in {n.name for n in ast.walk(info.defs[head])
                                                            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}:
            problems.append(f"{endpoint_id}: {rel} {head} has no method {scope.split('.')[1]}")
        if kind not in ("P", "S", "PS"):
            problems.append(f"{endpoint_id}: kind {kind}")
    return problems


def all_problems(scripts: Path, tables=inventory) -> list[str]:
    skill, findings = scan_inventory(scripts, tables)
    return (module_problems(skill, tables) + external_problems(findings, tables) + form_problems(findings, tables)
            + library_problems(findings, tables) + caller_problems(findings, tables) + import_problems(findings, tables)
            + operation_problems(findings, tables) + endpoint_problems(skill, tables)
            + [f"{rel}: does not parse" for rel in skill.unparsable])


class InsideTheStore(unittest.TestCase):
    """The tables agree with the code, check by check, so a failure names its check."""

    @classmethod
    def setUpClass(cls):
        cls.skill, cls.findings = scan_inventory(SCRIPTS)

    def test_every_module_is_in_exactly_one_table(self):
        self.assertEqual(module_problems(self.skill), [])
        self.assertEqual(len(self.skill.modules), len(inventory.CREDENTIAL) + len(inventory.NO_CREDENTIAL))

    def test_external_modules_are_the_closed_list_with_exact_symbols(self):
        self.assertEqual(external_problems(self.findings), [])

    def test_forms_that_need_no_import_are_where_the_list_allows(self):
        self.assertEqual(form_problems(self.findings), [])

    def test_library_symbols_are_used_only_inside_primitives_and_sinks(self):
        self.assertEqual(library_problems(self.findings), [])

    def test_every_direct_caller_of_a_primitive_or_sink_is_reviewed(self):
        self.assertEqual(caller_problems(self.findings), [])
        broker = {(rel, function) for (rel, function, kind) in REVIEWED if kind.startswith("broker_request")}
        self.assertEqual(broker, set(inventory.DIRECT_CALLERS["agent-client"]))

    def test_no_credential_modules_import_only_what_their_rows_allow(self):
        self.assertEqual(import_problems(self.findings), [])

    def test_every_public_operation_is_listed(self):
        self.assertEqual(operation_problems(self.findings), [])
        self.assertEqual(endpoint_problems(self.skill), [])

    def test_the_paths_file_names_every_module_endpoint_and_operation(self):
        text = PATHS_FILE.read_text("utf-8")
        for rel in list(inventory.CREDENTIAL) + list(inventory.NO_CREDENTIAL):
            self.assertIn(f"`{rel}`", text, rel)
        for endpoint_id, (rel, scope, _kind, _what) in inventory.ENDPOINTS.items():
            self.assertIn(f"`{scope}`", text, endpoint_id)
        for parser, operations in inventory.OPERATIONS.items():
            for operation in operations:
                self.assertIn(f"`{operation}`", text, f"{parser} {operation}")
        self.assertNotRegex(text, r"prove[sd]? (that )?(the )?(list|inventory) (is )?complete", "no claim of proof")


class _Patched:
    """A copy of the inventory with one table changed."""

    def __init__(self, **changes):
        for name in dir(inventory):
            if name.isupper():
                setattr(self, name, getattr(inventory, name))
        for name, value in changes.items():
            setattr(self, name, value)


class TheCheckCatchesAnUnlistedPath(unittest.TestCase):
    """A copy of scripts/ with one added use, or a patched table: the check reports it."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="credential-inventory-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        shutil.copytree(SCRIPTS, self.root / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
        self.scripts = self.root / "scripts"

    def add(self, name, text):
        path = self.scripts / name
        path.write_text(path.read_text("utf-8") + "\n\n" + text + "\n", encoding="utf-8")

    def problems(self, check, tables=inventory):
        skill, findings = scan_inventory(self.scripts, tables)
        return check(skill if check is module_problems or check is endpoint_problems else findings, tables)

    def test_the_copy_matches_before_any_change(self):
        self.assertEqual(all_problems(self.scripts), [])

    def test_a_module_in_neither_table_or_in_both(self):
        (self.scripts / "secret_store" / "status_extra.py").write_text("def describe(store):\n    return 1\n", "utf-8")
        self.assertEqual(self.problems(module_problems), ["secret_store/status_extra.py: in neither table"])
        both = _Patched(NO_CREDENTIAL={**inventory.NO_CREDENTIAL, "secret_store/envelope.py": "x"})
        self.assertIn("secret_store/envelope.py: in both tables", all_problems(SCRIPTS, both))

    def test_a_no_credential_module_that_imports_a_credential_module(self):
        self.add("migration_lock.py", "from secret_store.oauth_ops import read_shared\n\ndef describe(store, signin):\n"
                                      "    return read_shared(store, signin)")
        self.assertEqual(self.problems(import_problems),
                         ["migration_lock.py: a no-credential module takes ['read_shared'] from secret_store/oauth_ops.py"])
        self.add("secret_store/fileio.py", "from . import oauth_ops\n\ndef more(store, signin):\n"
                                           "    return oauth_ops.read_shared(store, signin)")
        self.assertIn("secret_store/fileio.py: a no-credential module takes ['read_shared'] from secret_store/oauth_ops.py",
                      self.problems(import_problems))

    def test_a_no_credential_module_with_a_data_carrying_import_or_a_form(self):
        self.add("secret_store/provider_profiles.py", "import socket\n\ndef host():\n    return socket.gethostname()")
        problems = self.problems(external_problems)
        self.assertIn("secret_store/provider_profiles.py: imports socket, not allowed there (symbols ['gethostname'])", problems)
        self.add("secret_store/fileio.py", "def shout(x):\n    print(x)\n    os.environ['X'] = x\n"
                                           "    getattr(x, x.name)()")
        self.add("secret_store/canonical.py", "from pathlib import Path\n\ndef keep(x):\n    Path('k').write_text(x)")
        self.assertEqual(self.problems(form_problems), [
            "secret_store/fileio.py shout: environment-write, not allowed there",
            "secret_store/canonical.py keep: file-write, not allowed there",
            "secret_store/fileio.py shout: reflection, not allowed there",
            "secret_store/fileio.py shout: terminal, not allowed there"])

    def test_a_new_function_calling_or_naming_a_primitive_or_sink(self):
        self.add("vault_tray.py", "def more(obj, key):\n    from secret_store import envelope\n"
                                  "    return envelope.open_(obj, 'k', key)\n\n"
                                  "def passed():\n    from secret_store.envelope import seal\n    return seal\n\n"
                                  "def bound(obj, key):\n    from secret_store import envelope\n"
                                  "    opener = envelope.open_\n    return opener(obj, 'k', key)\n\n"
                                  "def vault(v, p):\n    return v._load_unlocked(p)\n\n"
                                  "def peek():\n    from vault_agent_runtime import read_state\n    return read_state()")
        self.assertEqual(self.problems(caller_problems), [  # by endpoint id, then caller
            "vault_tray.py peek: calls or names agent-state-read (read_state) and is not a reviewed caller",
            "vault_tray.py bound: calls or names open (open_) and is not a reviewed caller",
            "vault_tray.py more: calls or names open (open_) and is not a reviewed caller",
            "vault_tray.py passed: calls or names seal (seal) and is not a reviewed caller",
            "vault_tray.py vault: calls or names vault-load (PortableVault._load_unlocked) and is not a reviewed caller"])
        stale = _Patched(DIRECT_CALLERS={**inventory.DIRECT_CALLERS, "open": {**inventory.DIRECT_CALLERS["open"],
                                                                                ("vault_tray.py", "gone"): "x"}})
        self.assertIn("vault_tray.py gone: reviewed caller of open but no longer names it", all_problems(SCRIPTS, stale))

    def test_a_library_symbol_outside_a_primitive_through_every_indirect_form(self):
        self.add("vault_tray.py", "from cryptography.hazmat.primitives.ciphers.aead import AESGCM as Cipher\n"
                                  "from secret_store.envelope import AESGCM\n"
                                  "import keyring as kr\n\n"
                                  "def direct(k, n, c):\n    return Cipher(k).decrypt(n, c, b'')\n\n"
                                  "def bound(k, n, c):\n    dec = AESGCM(k).decrypt\n    return dec(n, c, b'')\n\n"
                                  "def literal(k):\n    return getattr(Cipher(k), 'decrypt')\n\n"
                                  "def keychain():\n    return getattr(kr.get_keyring(), 'get_password')('s', 'u')")
        self.assertEqual(self.problems(library_problems), [
            "vault_tray.py bound: uses decrypt outside a listed primitive or sink",
            "vault_tray.py direct: uses decrypt outside a listed primitive or sink",
            "vault_tray.py literal: uses decrypt outside a listed primitive or sink",
            "vault_tray.py keychain: uses get_password outside a listed primitive or sink"])
        problems = self.problems(external_problems)
        self.assertIn("vault_tray.py: imports cryptography.hazmat.primitives.ciphers.aead, not allowed there (symbols "
                      "['AESGCM'])", problems)  # the alias and the re-export both resolve to the symbol
        self.assertIn("vault_tray.py: imports keyring, not allowed there (symbols ['get_keyring'])", problems)

    def test_an_external_module_off_the_list_and_a_socket_in_the_wrong_module(self):
        self.add("vault_tray.py", "import requests\nimport socket\n\ndef fetch():\n    return requests.get, socket.socket")
        problems = self.problems(external_problems)
        self.assertIn("vault_tray.py: imports requests, which is not on the closed list", problems)
        self.assertIn("vault_tray.py: imports socket, not allowed there (symbols ['socket'])", problems)

    def test_a_new_subcommand_in_each_parser_and_a_new_agent_operation(self):
        for name, anchor, text in (  # text is put in front of the anchor line, or replaces it
                ("brain_secrets.py", '    sub.add_parser("status", help="plain-words state of the store")\n',
                 '    sub.add_parser("export-all")\n'),
                ("vaultctl.py", '    commands.add_parser("status", help="Show Vault Agent lock state")\n',
                 '    commands.add_parser("dump")\n'),
                ("vault_agent.py", '            elif operation == "ping":\n',
                 '            elif operation == "get_everything":\n                result = {}\n'),
                ("secret_store/broker_backend.py", 'STORE_OPS = frozenset({"abort_refresh", ',
                 'STORE_OPS = frozenset({"read_all", "abort_refresh", ')):
            path = self.scripts / name
            source = path.read_text("utf-8")
            self.assertIn(anchor, source, name)
            replacement = text if "frozenset" in text else text + anchor
            path.write_text(source.replace(anchor, replacement, 1), "utf-8")
        self.assertEqual(self.problems(operation_problems), [
            "agent get_everything: an operation the list does not name",
            "agent read_all: an operation the list does not name",
            "brain_secrets.py export-all: an operation the list does not name",
            "vaultctl.py dump: an operation the list does not name"])
        (self.scripts / "newtool.py").write_text("import argparse\np = argparse.ArgumentParser()\n", "utf-8")
        self.assertIn("newtool.py: a parser the list does not name", self.problems(operation_problems))
        stale = _Patched(OPERATIONS={**inventory.OPERATIONS, "vaultctl.py": {**inventory.OPERATIONS["vaultctl.py"],
                                                                              "gone": ((), (), "x", "")}})
        self.assertIn("vaultctl.py gone: in the list, not in the code", all_problems(SCRIPTS, stale))


if __name__ == "__main__":
    unittest.main()
