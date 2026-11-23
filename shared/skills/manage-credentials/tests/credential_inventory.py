"""The reviewed tables of CREDENTIAL-PATHS.md, section "Inside the store" (follow-up plan R11, rule 6).
tests/test_credential_paths.py compares them with the source (credential_scan.py) and
tests/test_credential_paths_runtime.py with what the running code does (credential_recorder.py).
A table here is a person's review of the code; a test fails when the code and a table disagree.
Change a table only after reading the code it describes, and change CREDENTIAL-PATHS.md with it.

Module names are scripts-relative ("secret_store/envelope.py"). A scope is "Class.method" or
"function" or "outer.inner" for a nested function, or "<module>"."""
from __future__ import annotations

# -- (a) external modules, closed ---------------------------------------------------------------
# Every external top-level module any script imports. An import of another one fails the test.
EXTERNAL_MODULES = frozenset({
    "PIL", "__future__", "argparse", "atexit", "base64", "binascii", "contextlib", "copy", "cryptography",
    "ctypes", "dataclasses", "datetime", "errno", "fcntl", "functools", "getpass", "hashlib", "hmac", "http",
    "json", "keyring", "math", "msvcrt", "multiprocessing", "os", "pathlib", "pystray", "re", "secrets", "shutil",
    "socket", "ssl", "stat", "struct", "subprocess", "sys", "tempfile", "threading", "time", "tkinter", "types",
    "typing", "urllib", "warnings",
})
# The modules that can carry data into or out of the process. For each, the skill modules allowed
# to import it and the exact symbols taken (an alias, a re-export, a bound name and getattr with a
# literal all count). An import anywhere else, or another symbol, fails.
DATA_CARRYING = ("cryptography", "keyring", "getpass", "tkinter", "socket", "ssl", "http", "urllib", "subprocess",
                 "multiprocessing", "ctypes", "msvcrt", "fcntl", "tempfile", "shutil")
_AEAD = "cryptography.hazmat.primitives.ciphers.aead"
_ED = "cryptography.hazmat.primitives.asymmetric.ed25519"
_X = "cryptography.hazmat.primitives.asymmetric.x25519"
_SER = "cryptography.hazmat.primitives.serialization"
_EXC = "cryptography.exceptions"
_LOCK_F = ("LOCK_EX", "LOCK_NB", "LOCK_UN", "flock")
_LOCK_M = ("LK_NBLCK", "LK_UNLCK", "locking")
EXTERNAL_SYMBOLS: dict[tuple[str, str], tuple[str, ...]] = {
    (_EXC, "portable_vault.py"): ("InvalidTag",),
    (_EXC, "secret_store/envelope.py"): ("InvalidTag",),
    (_EXC, "secret_store/hpke.py"): ("InvalidTag",),
    (_EXC, "secret_store/policy.py"): ("InvalidSignature",),
    (_EXC, "secret_store/recovery_package.py"): ("InvalidTag",),
    (_EXC, "secret_store/signing.py"): ("InvalidSignature",),
    (_EXC, "token_relay_backend.py"): ("InvalidTag",),
    ("cryptography.hazmat.primitives", "secret_store/recovery.py"): ("hashes", "hashes.SHA256"),
    (_ED, "secret_store/checkpoint.py"): ("Ed25519PrivateKey", "Ed25519PublicKey"),
    (_ED, "secret_store/keys.py"): ("Ed25519PrivateKey", "Ed25519PrivateKey.from_private_bytes",
                                    "Ed25519PrivateKey.generate", "Ed25519PublicKey"),
    (_ED, "secret_store/policy.py"): ("Ed25519PrivateKey", "Ed25519PublicKey", "Ed25519PublicKey.from_public_bytes"),
    (_ED, "secret_store/recovery.py"): ("Ed25519PrivateKey", "Ed25519PrivateKey.from_private_bytes"),
    (_ED, "secret_store/recovery_package.py"): ("Ed25519PublicKey",),
    (_ED, "secret_store/signing.py"): ("Ed25519PrivateKey", "Ed25519PublicKey"),
    (_ED, "secret_store/store.py"): ("Ed25519PrivateKey",),
    (_ED, "secret_store/store_ops.py"): ("Ed25519PrivateKey",),
    (_X, "secret_store/envelope.py"): ("X25519PrivateKey", "X25519PublicKey"),
    (_X, "secret_store/hpke.py"): ("X25519PrivateKey", "X25519PrivateKey.from_private_bytes", "X25519PrivateKey.generate",
                                   "X25519PublicKey", "X25519PublicKey.from_public_bytes"),
    (_X, "secret_store/keys.py"): ("X25519PrivateKey", "X25519PrivateKey.from_private_bytes", "X25519PrivateKey.generate",
                                   "X25519PublicKey"),
    (_X, "secret_store/policy.py"): ("X25519PublicKey", "X25519PublicKey.from_public_bytes"),
    (_X, "secret_store/recovery.py"): ("X25519PrivateKey", "X25519PrivateKey.from_private_bytes"),
    (_X, "secret_store/recovery_package.py"): ("X25519PrivateKey", "X25519PublicKey"),
    (_X, "secret_store/store.py"): ("X25519PrivateKey",),
    (_AEAD, "portable_vault.py"): ("AESGCM",),
    (_AEAD, "secret_store/envelope.py"): ("AESGCM", "AESGCM.generate_key"),
    (_AEAD, "secret_store/hpke.py"): ("AESGCM",),
    (_AEAD, "secret_store/recovery_package.py"): ("AESGCM", "AESGCM.generate_key"),
    (_AEAD, "token_relay_backend.py"): ("AESGCM",),
    ("cryptography.hazmat.primitives.kdf.hkdf", "secret_store/recovery.py"): ("HKDF",),
    (_SER, "secret_store/hpke.py"): ("Encoding", "Encoding.Raw", "PublicFormat", "PublicFormat.Raw"),
    (_SER, "secret_store/keys.py"): ("Encoding", "Encoding.Raw", "NoEncryption", "PrivateFormat", "PrivateFormat.Raw",
                                     "PublicFormat", "PublicFormat.Raw"),
    ("ctypes", "secret_store/fileio.py"): ("WinDLL", "WinError", "get_last_error", "wintypes", "wintypes.BOOL",
                                           "wintypes.DWORD", "wintypes.LPCWSTR"),
    ("ctypes", "vault_agent_runtime.py"): ("CDLL", "POINTER", "Structure", "WinDLL", "byref", "c_int", "c_long", "c_long.from_buffer", "c_ubyte",
                                           "c_ushort", "c_void_p", "c_void_p.from_buffer", "cast",
                                           "create_string_buffer", "get_errno", "get_last_error", "sizeof", "windll", "windll.kernel32", "windll.kernel32.CloseHandle",
                                           "windll.kernel32.OpenProcess", "wintypes", "wintypes.BOOL",
                                           "wintypes.DWORD", "wintypes.HANDLE", "wintypes.LPCWSTR", "wintypes.LPWSTR",
                                           "wintypes.ULONG", "wintypes.WORD"),
    ("ctypes", "vault_credentials.py"): ("byref", "c_ulong", "c_void_p", "windll", "windll.kernel32",
                                         "windll.kernel32.GetConsoleMode"),
    ("ctypes", "vault_tray.py"): (
        "Structure", "WINFUNCTYPE", "byref", "c_int", "c_ssize_t", "c_void_p", "create_unicode_buffer", "windll",
        "windll.kernel32", "windll.kernel32.GetModuleHandleW", "windll.user32", "windll.user32.AdjustWindowRectEx",
        "windll.user32.CreateWindowExW", "windll.user32.DefWindowProcW", "windll.user32.DefWindowProcW.argtypes",
        "windll.user32.DefWindowProcW.restype", "windll.user32.DestroyWindow", "windll.user32.DispatchMessageW",
        "windll.user32.GetMessageW", "windll.user32.GetWindowTextLengthW", "windll.user32.GetWindowTextW",
        "windll.user32.IsDialogMessageW", "windll.user32.LoadCursorW", "windll.user32.MessageBoxW",
        "windll.user32.PostQuitMessage", "windll.user32.RegisterClassW", "windll.user32.SendMessageW",
        "windll.user32.SendMessageW.argtypes", "windll.user32.SendMessageW.restype", "windll.user32.SetFocus",
        "windll.user32.SetForegroundWindow", "windll.user32.SetWindowPos", "windll.user32.ShowWindow",
        "windll.user32.SystemParametersInfoW", "windll.user32.TranslateMessage", "windll.user32.UpdateWindow",
        "wintypes", "wintypes.HANDLE", "wintypes.HBRUSH", "wintypes.HICON", "wintypes.HINSTANCE", "wintypes.HWND",
        "wintypes.LONG", "wintypes.LPARAM", "wintypes.LPCWSTR", "wintypes.MSG", "wintypes.UINT", "wintypes.WPARAM"),
    ("fcntl", "secret_store/fileio.py"): _LOCK_F,
    ("fcntl", "secret_store/repo.py"): _LOCK_F,
    ("fcntl", "vault_agent.py"): _LOCK_F,
    ("getpass", "token_relay.py"): ("GetPassWarning", "getpass"),
    ("getpass", "vault_credentials.py"): ("GetPassWarning", "getpass"),
    ("getpass", "vaultctl.py"): ("GetPassWarning", "getpass"),
    ("http.client", "token_endpoint.py"): ("HTTPSConnection",),
    ("keyring", "secret_store/keys.py"): ("get_keyring",),
    ("msvcrt", "secret_store/fileio.py"): _LOCK_M,
    ("msvcrt", "secret_store/repo.py"): _LOCK_M,
    ("msvcrt", "vault_agent.py"): _LOCK_M,
    ("msvcrt", "vault_credentials.py"): ("get_osfhandle",),
    ("multiprocessing", "vault_agent.py"): ("AuthenticationError",),
    ("multiprocessing.connection", "vault_agent.py"): ("Client", "Listener"),
    ("multiprocessing.connection", "vault_broker_client.py"): ("Client",),
    ("shutil", "migrate_to_store.py"): ("copyfile",),
    ("shutil", "secret_store/recovery_package.py"): ("rmtree",),
    ("shutil", "secret_store/team.py"): ("rmtree",),
    ("socket", "secret_store/store_ops.py"): ("gethostname",),
    ("socket", "token_relay_store.py"): ("gethostname",),
    ("ssl", "token_endpoint.py"): ("create_default_context",),
    ("subprocess", "brain_secrets.py"): ("run",),
    ("subprocess", "secret_store/recovery_package.py"): ("run",),
    ("subprocess", "secret_store/repo.py"): ("CompletedProcess", "PIPE", "Popen", "run"),
    ("subprocess", "secret_store/store.py"): ("run",),
    ("subprocess", "secret_store/team.py"): ("run",),
    ("subprocess", "token_relay_backend.py"): ("TimeoutExpired", "run"),
    ("subprocess", "vault_credentials.py"): ("run",),
    ("subprocess", "vaultctl.py"): ("run",),
    ("tempfile", "portable_vault.py"): ("gettempdir", "mkstemp"),
    ("tempfile", "secret_store/recovery_package.py"): ("TemporaryDirectory", "mkstemp"),
    ("tempfile", "vault_agent_runtime.py"): ("mkstemp",),
    ("tkinter", "secret_window.py"): ("BooleanVar", "Button", "Checkbutton", "Entry", "Frame", "Label", "TclError", "Tk"),
    ("urllib.parse", "token_endpoint.py"): ("urlencode", "urlsplit"),
    ("urllib.parse", "token_relay_backend.py"): ("quote",),
    ("urllib.request", "token_endpoint.py"): ("getproxies", "proxy_bypass"),
}
# Why a no-credential module may hold a data-carrying import: one line per row above whose module
# is in NO_CREDENTIAL. The test requires a line for each.
NO_CREDENTIAL_EXTERNAL: dict[tuple[str, str], str] = {
    (_EXC, "secret_store/policy.py"): "InvalidSignature: a signature check, no key material",
    (_EXC, "secret_store/signing.py"): "InvalidSignature: a signature check",
    (_ED, "secret_store/checkpoint.py"): "key types for annotations; the signing key object is used, never its bytes",
    (_ED, "secret_store/policy.py"): "public keys are parsed; the signing key object is used, never its bytes",
    (_ED, "secret_store/signing.py"): "the signing key object signs; its bytes are never read",
    (_X, "secret_store/policy.py"): "public keys are parsed and validated",
    ("ctypes", "secret_store/fileio.py"): "MoveFileExW with write-through for a file of ciphertext or state",
    ("fcntl", "secret_store/fileio.py"): "the per-entry and vault locks",
    ("msvcrt", "secret_store/fileio.py"): "the per-entry and vault locks",
}

# -- (a) forms that need no import: the functions allowed each -------------------------------------
FORMS: dict[str, frozenset[tuple[str, str]]] = {
    # print, or a reference to sys.stdout or sys.stderr: names, presence and fingerprints, except the
    # two sinks below (vaultctl.py main prints an access token; token_relay.py main the relay key)
    "terminal": frozenset({
        ("brain_secrets.py", "_delete"), ("brain_secrets.py", "_recovery_package"), ("brain_secrets.py", "_restore"),
        ("brain_secrets.py", "_unfinished"), ("brain_secrets.py", "main"), ("migrate_to_store.py", "main"),
        ("migrate_to_store.py", "migrate"),
        ("migrate_to_store.py", "rollback"), ("token_relay.py", "_seed"), ("token_relay.py", "_status"),
        ("token_relay.py", "main"), ("token_relay_store.py", "RelayedStore._warn"),
        ("vault_agent.py", "VaultAgent._keep_state"), ("vault_agent.py", "VaultAgent.serve_forever"),
        ("vault_agent.py", "_end_process"), ("vault_agent.py", "main"), ("vault_credentials.py", "_cancelled"),
        ("vault_credentials.py", "_put_entry_window"), ("vault_credentials.py", "main"), ("vaultctl.py", "main")}),
    # input(): a typed confirmation (an entry name, a write id), never a value
    "input": frozenset({("brain_secrets.py", "_delete"), ("brain_secrets.py", "_unfinished"), ("vault_credentials.py", "main")}),
    # sys.stdin.read: a value piped in (vault_credentials.py put --stdin)
    "stdin-read": frozenset({("vault_credentials.py", "_secret_value")}),
    # os.environ[...] =, del, update, pop, setdefault, clear, os.putenv, os.unsetenv
    "environment-write": frozenset({("token_relay.py", "main")}),  # PORTABLE_VAULT_PATH, a path
    # open or Path.open in a writing mode, os.fdopen, write_text, write_bytes, os.replace, os.rename,
    # tempfile.mkstemp, NamedTemporaryFile, shutil.copyfile, copy, copy2, copytree, move
    "file-write": frozenset({
        ("migrate_to_store.py", "_backup"), ("migrate_to_store.py", "_migrate"), ("migration_lock.py", "MigrationLock._create"),
        ("portable_vault.py", "PortableVault._write_unlocked"), ("portable_vault.py", "write_migration_marker"),
        ("secret_store/checkpoint.py", "save"), ("secret_store/enrol.py", "_save_pending"),
        ("secret_store/fileio.py", "locked"), ("secret_store/fileio.py", "write_durable"),
        ("secret_store/recovery_package.py", "_write_atomic"), ("secret_store/recovery_package.py", "restore"),
        ("secret_store/repo.py", "SecretRepo._set_state"), ("secret_store/repo.py", "SecretRepo._stage"),
        ("secret_store/repo.py", "SecretRepo.clone_or_open"), ("secret_store/repo.py", "repo_lock"),
        ("secret_store/store.py", "SecretStore._save_pin"), ("secret_store/store_ops.py", "write_marker"),
        ("secret_store/store_ops.py", "write_upkeep_error"), ("token_relay_store.py", "holder_name"),
        ("vault_agent.py", "VaultAgent._acquire_singleton"), ("vault_agent_runtime.py", "log_tray"),
        ("vault_agent_runtime.py", "write_state")}),
    # eval, exec, __import__, compile, globals, locals, vars; getattr, setattr or delattr with a name that
    # is not a literal
    "reflection": frozenset({("secret_store/store_ops.py", "store_status")}),  # getattr over a tuple of two literals
    # the string PORTABLE_VAULT_PASSPHRASE: read from the environment, or removed from a child's
    "passphrase-variable": frozenset({
        ("portable_vault.py", "PortableVaultJsonStore.__init__"), ("vault_credentials.py", "_passphrase"),
        ("vault_credentials.py", "_credential_environment"), ("vaultctl.py", "_mapped_environment")}),
}

# -- (b) primitives and sinks -------------------------------------------------------------------
# id -> (module, scope, kind, what). kind: P a primitive (a credential first exists in the clear in
# the process), S a sink (cleartext written or sent), PS both in one function.
ENDPOINTS: dict[str, tuple[str, str, str, str]] = {
    "open": ("secret_store/envelope.py", "open_", "P", "the payload of a store object: static values and kinds, a "
             "sign-in record, a grant, an index, a journal, pending-write or hand-over record"),
    "hpke-open": ("secret_store/hpke.py", "open_", "P", "the data key of an object or package; the enrolment challenge"),
    "package-open": ("secret_store/recovery_package.py", "_open", "P", "the package plaintext: the signed checkpoint "
                     "and the Git bundle of sealed objects (listed because it calls the cipher's decryption)"),
    "vault-load": ("portable_vault.py", "PortableVault._load_unlocked", "P", "the whole old vault"),
    "relay-decrypt": ("token_relay_backend.py", "decrypt_token", "P", "the relayed token record"),
    "keychain-read": ("secret_store/keys.py", "load_private_keys", "P", "this computer's private keys from the keychain"),
    "token-endpoint": ("token_endpoint.py", "post_token", "PS", "sends the refresh token or code; receives the token"),
    "window": ("secret_window.py", "_dialog", "P", "values typed into the masked window: secrets, passphrases, words"),
    "prompt-passphrase": ("vault_credentials.py", "_passphrase", "P", "the vault passphrase from the hidden prompt or "
                          "PORTABLE_VAULT_PASSPHRASE"),
    "prompt-value": ("vault_credentials.py", "_secret_value", "P", "a value from the hidden prompt or standard input"),
    "vaultctl-prompt": ("vaultctl.py", "_hidden_passphrase", "P", "the passphrase or a value from the hidden prompt"),
    "relay-prompt": ("token_relay.py", "_hidden_input", "P", "the relay key from the hidden prompt"),
    "tray-dialog": ("vault_tray.py", "_win_password_dialog", "P", "the passphrase from the Win32 dialog"),
    "session-passphrase": ("portable_vault.py", "PortableVaultJsonStore", "P", "PORTABLE_VAULT_PASSPHRASE from the "
                           "environment (its __init__)"),
    "agent-client": ("vault_broker_client.py", "broker_request", "PS", "sends a request (a value, the unlock "
                     "passphrase, and the authentication token in every request) and receives the agent's answer "
                     "(values, records, access tokens)"),
    "agent-pipe": ("vault_agent.py", "VaultAgent._serve_connection", "PS", "receives a request from the pipe (handle "
                   "compares its token) and sends the reply"),
    "agent-auth-make": ("vault_agent.py", "VaultAgent", "P", "the agent's authentication token and pipe key, made "
                        "fresh at each start (its __init__); serve_forever gives the key to the Listener"),
    "agent-state-write": ("vault_agent_runtime.py", "write_state", "S", "the token and key in the clear, written only "
                          "into the published file proved private in place (Windows; Linux on the ext family and "
                          "tmpfs; every other system refused), through a kept handle that empties it on any failure "
                          "after the first byte, inside a folder proved private the same way; the agent does not "
                          "start, or stops, when that cannot be proved"),
    "agent-state-read": ("vault_agent_runtime.py", "read_state", "P", "the token and key first in the client process"),
    "agent-connect": ("vault_broker_client.py", "_connect", "PS", "spends the key in the pipe's handshake and returns "
                      "the token to broker_request"),
    "keygen": ("secret_store/keys.py", "generate_key_pairs", "P", "new private keys"),
    "words": ("secret_store/recovery.py", "generate_mnemonic", "P", "new recovery words"),
    "recovery-keys": ("secret_store/recovery.py", "derive_recovery_keys", "P", "the recovery keys from typed words"),
    "relay-key": ("token_relay_backend.py", "new_key_text", "P", "a new relay key"),
    "seal": ("secret_store/envelope.py", "seal", "S", "encryption into a store object, a journal, pending-write or "
             "hand-over record"),
    "hpke-seal": ("secret_store/hpke.py", "seal", "S", "a data key wrapped to a reader; the sealed challenge"),
    "package": ("secret_store/recovery_package.py", "build", "S", "the recovery package"),
    "keychain-write": ("secret_store/keys.py", "store_private_keys", "S", "the keychain"),
    "vault-write": ("portable_vault.py", "PortableVault._write_unlocked", "S", "the old vault file"),
    "relay-encrypt": ("token_relay_backend.py", "encrypt_token", "S", "the relay record"),
    "vaultctl-main": ("vaultctl.py", "main", "S", "the terminal (access-token prints the token) and a child's "
                      "environment (run)"),
    "relay-main": ("token_relay.py", "main", "S", "the terminal (key-export prints the relay key, to a terminal only)"),
    "credentials-main": ("vault_credentials.py", "main", "S", "a child's environment (run, session)"),
    "words-window": ("secret_window.py", "show_recovery_words", "S", "the screen: the recovery words, once"),
}
# Attribute names that reach a primitive or sink through another receiver (self._load_unlocked,
# store._broker_request): each is unique in the skill and stands for one endpoint.
METHOD_NAMES: dict[str, tuple[str, str]] = {
    "_load_unlocked": ("portable_vault.py", "PortableVault._load_unlocked"),
    "_write_unlocked": ("portable_vault.py", "PortableVault._write_unlocked"),
    "_serve_connection": ("vault_agent.py", "VaultAgent._serve_connection"),
    "_broker_request": ("vault_broker_client.py", "broker_request"),
}
# The library symbols beneath the primitives and sinks (attribute names), and the functions allowed
# to use each. A use anywhere else, including through getattr with a literal, fails.
LIBRARY_SYMBOLS: dict[str, frozenset[tuple[str, str]]] = {
    "decrypt": frozenset({("secret_store/envelope.py", "open_"), ("secret_store/hpke.py", "open_"),
                          ("secret_store/recovery_package.py", "_open"), ("portable_vault.py", "PortableVault._load_unlocked"),
                          ("token_relay_backend.py", "decrypt_token")}),
    "encrypt": frozenset({("secret_store/envelope.py", "seal"), ("secret_store/hpke.py", "seal"),
                          ("secret_store/recovery_package.py", "build"), ("portable_vault.py", "PortableVault._write_unlocked"),
                          ("token_relay_backend.py", "encrypt_token")}),
    "generate_key": frozenset({("secret_store/envelope.py", "seal"), ("secret_store/recovery_package.py", "build")}),
    "get_password": frozenset({("secret_store/keys.py", "load_private_keys"), ("secret_store/keys.py", "store_private_keys")}),
    "set_password": frozenset({("secret_store/keys.py", "store_private_keys")}),
    "getpass": frozenset({("token_relay.py", "_hidden_input"), ("vault_credentials.py", "_passphrase"),
                          ("vault_credentials.py", "_secret_value"), ("vaultctl.py", "_hidden_passphrase")}),
    "scrypt": frozenset({("portable_vault.py", "_derive_key"), ("portable_vault.py", "PortableVault._write_unlocked")}),
    "derive": frozenset({("secret_store/recovery.py", "_hkdf")}),
    "from_private_bytes": frozenset({("secret_store/keys.py", "load_private_keys"),
                                     ("secret_store/recovery.py", "derive_recovery_keys"),
                                     ("secret_store/hpke.py", "derive_key_pair")}),  # RFC test vectors; no caller
    "private_bytes": frozenset({("secret_store/keys.py", "raw_private")}),
    "generate": frozenset({("secret_store/keys.py", "generate_key_pairs"), ("secret_store/hpke.py", "load_public_key"),
                           ("secret_store/hpke.py", "encap")}),  # the last two: ephemeral keys
    "exchange": frozenset({("secret_store/hpke.py", "_dh")}),
    "Entry": frozenset({("secret_window.py", "_dialog")}),
    "GetWindowTextW": frozenset({("vault_tray.py", "_win_password_dialog.wndproc")}),
    "recv": frozenset({("vault_agent.py", "VaultAgent._serve_connection"), ("vault_broker_client.py", "broker_request")}),
    "send": frozenset({("vault_agent.py", "VaultAgent._serve_connection"), ("vault_broker_client.py", "broker_request")}),
    "token_bytes": frozenset({("vault_agent.py", "VaultAgent.__init__")}),  # the pipe key (token_hex also names ids)
}
# The reviewed direct callers of each endpoint: every function that calls it or names it (passes,
# stores, aliases). endpoint id -> {(module, scope): why}.
DIRECT_CALLERS: dict[str, dict[tuple[str, str], str]] = {
    "open": {("secret_store/accept.py", "_content"): "opens every object this computer reads when a commit is judged",
             ("secret_store/journal.py", "Journal.read"): "a journal record, this computer's key only",
             ("secret_store/pending.py", "PendingWrites.read"): "a pending-write record, this computer's key only",
             ("secret_store/replace_ops.py", "_open"): "a hand-over file", ("secret_store/replace_ops.py", "discard_retired"):
             "the entry name of each journal record, to find a retired grant's",
             ("secret_store/store.py", "SecretStore._open_object"): "the store's one reader of an object"},
    "hpke-open": {("secret_store/enrol.py", "prove"): "the challenge sealed to this computer",
                  ("secret_store/envelope.py", "open_"): "the object's data key",
                  ("secret_store/recovery_package.py", "_open"): "the package's data key"},
    "package-open": {("secret_store/recovery_package.py", "restore"): "restore from a package"},
    "vault-load": {("portable_vault.py", f"PortableVault.{m}"): "the vault's own read-modify-write" for m in
                   ("load", "change_passphrase", "set_fields", "delete_entry", "delete_field")},
    "relay-decrypt": {("token_relay_store.py", "RelayedStore._verified"): "the remote record after its checks"},
    "keychain-read": {("secret_store/store.py", "SecretStore._identity"): "this computer's keys, once per store"},
    "token-endpoint": {},  # the library connectors call it; nothing under scripts/ does
    "window": {("secret_window.py", "ask_new_passphrase"): "a new passphrase twice",
               ("secret_window.py", "ask_secrets"): "secret fields, and the passphrase when the agent is locked"},
    "prompt-passphrase": {("vault_credentials.py", "_new_passphrase"): "a new passphrase twice",
                          ("vault_credentials.py", "main"): "every command that opens the vault itself"},
    "prompt-value": {("vault_credentials.py", "main"): "put and put-entry"},
    "vaultctl-prompt": {("vaultctl.py", "main"): "unlock and secret-put"},
    "relay-prompt": {("token_relay.py", "main"): "key-import"},
    "tray-dialog": {("vault_tray.py", "_prompt_passphrase.ui"): "on its own thread, with a time limit"},
    "session-passphrase": {("token_relay.py", "_seed"): "the local token to seed", ("token_relay.py", "_status"):
                           "the local version only"},
    "agent-client": {
        ("migrate_to_store.py", "main"): "passed to migrate and rollback", ("portable_vault.py", "BrokerOAuthStore.__init__"):
        "ping and status; the function is kept", ("portable_vault.py", "BrokerOAuthStore.clear"): "clear_signin",
        ("portable_vault.py", "BrokerOAuthStore.load"): "get_json", ("portable_vault.py", "BrokerOAuthStore.save"): "set_json",
        ("portable_vault.py", "BrokerOAuthStore.store_mode"): "status", ("portable_vault.py", "BrokerOAuthStore.sync_store"):
        "sync_store", ("token_relay.py", "_store_key"): "set_text of the relay key", ("token_relay.py", "read_relay_key"):
        "get_fields of the relay key", ("vault_broker_client.py", "_wait_for_refresher"): "poll_refresh",
        ("vault_broker_client.py", "broker_status"): "status", ("vault_broker_client.py", "store_refresh"): "begin_refresh",
        ("vault_broker_client.py", "store_refresh.end"): "abort_refresh or release_refresh",
        ("vault_credentials.py", "_put_entry_window"): "set_text and set_json", ("vault_credentials.py", "_try_broker_fields"):
        "status and get_fields", ("vault_credentials.py", "main"): "set_text (put)", ("vaultctl.py", "_mapped_environment"):
        "get_fields", ("vaultctl.py", "main"): "unlock, lock, get_access_token, set_text"},
    "agent-pipe": {("vault_agent.py", "VaultAgent._accept_loop"): "one thread per admitted connection"},
    "agent-auth-make": {("vault_agent.py", "build_agent"): "the one way serve and the tray build the agent",
                        ("vault_tray.py", "VaultTrayApp._start_broker"): "reads LOCK_WAIT_SECONDS only"},
    "agent-state-write": {("vault_agent.py", "VaultAgent.serve_forever"): "once the listener is up",
                          ("vault_agent.py", "VaultAgent._keep_state"): "again when the file went missing"},
    "agent-state-read": {("vault_broker_client.py", "_connect"): "the client's one read",
                         ("vault_agent.py", "VaultAgent._keep_state"): "compares the file with its own payload",
                         ("vault_agent_runtime.py", "clear_state"): "the pid only, to remove its own file",
                         ("vault_tray.py", "VaultTrayApp._start_broker"): "the pid only, to see its agent started"},
    "agent-connect": {("vault_broker_client.py", "broker_request"): "every request"},
    "keygen": {("secret_store/enrol.py", "request"): "a new computer", ("secret_store/store.py", "SecretStore.init_personal"):
               "the first computer", ("secret_store/team.py", "TeamStore.init_team"): "the first administrator"},
    "words": {("secret_store/store.py", "SecretStore.init_personal"): "shown once in the window",
              ("secret_store/team.py", "TeamStore.init_team"): "shown once in the window"},
    "recovery-keys": {("secret_store/store.py", "SecretStore.init_personal"): "to endorse the trust root",
                      ("secret_store/store.py", "SecretStore.restore_from_package"): "to open the package",
                      ("secret_store/team.py", "TeamStore.init_team"): "to endorse the trust root"},
    "relay-key": {("token_relay.py", "main"): "key-new"},
    "seal": {("secret_store/journal.py", "Journal.write"): "a journal record", ("secret_store/oauth_ops.py", "seal_revision"):
             "a sign-in, grant or static revision with an operation id", ("secret_store/pending.py", "PendingWrites.write"):
             "a pending-write record", ("secret_store/replace_ops.py", "_write"): "a hand-over file",
             ("secret_store/store_ops.py", "seal_object"): "a store object"},
    "hpke-seal": {("secret_store/enrol.py", "answer"): "the challenge", ("secret_store/envelope.py", "seal"): "the data key",
                  ("secret_store/recovery_package.py", "build"): "the package's data key"},
    "package": {("secret_store/store.py", "SecretStore.refresh_recovery_package"): "weekly, or after a policy change"},
    "keychain-write": {("secret_store/enrol.py", "request"): "a new computer", ("secret_store/store.py", "SecretStore.init_personal"):
                       "the first computer", ("secret_store/team.py", "TeamStore.init_team"): "the first administrator"},
    "vault-write": {("portable_vault.py", f"PortableVault.{m}"): "the vault's own writes" for m in
                    ("initialize", "save", "change_passphrase", "set_fields", "delete_entry", "delete_field")},
    "relay-encrypt": {("token_relay_backend.py", "build_record"): "every record written"},
    "vaultctl-main": {("vaultctl.py", "<module>"): "the command line"},
    "relay-main": {("token_relay.py", "<module>"): "the command line"},
    "credentials-main": {("vault_credentials.py", "<module>"): "the command line"},
    "words-window": {("secret_store/store.py", "_default_words_window"): "init and team-init"},
}
# A string constant equal to an endpoint's name, where it is not that endpoint.
STRING_EXEMPT: dict[tuple[str, str, str], str] = {
    ("secret_store/repo.py", "<module>", "main"): "the branch name",
    ("secret_store/store.py", "SecretStore._write", "build"): "a phase name of a typed write",
    ("secret_store/typed_write.py", "_isolated", "build"): "a phase name of a typed write",
    ("vault_agent.py", "build_agent", "VaultAgent"): "its return annotation",
}

# -- (d) every module in exactly one table ---------------------------------------------------------
CREDENTIAL: dict[str, str] = {  # module -> what passes through it in the clear
    "brain_secrets.py": "typed values from the window (put) and the recovery words (restore); prints names only",
    "migrate_to_store.py": "every old-vault value read through the agent and copied into the store; the store's "
                           "static values sent back to the agent at rollback",
    "portable_vault.py": "the whole old vault (decrypt, encrypt); sign-in records through the agent (BrokerOAuthStore); "
                         "the session passphrase (PortableVaultJsonStore)",
    "secret_window.py": "typed secrets and passphrases; the recovery words shown",
    "token_endpoint.py": "the refresh token or code sent; the token answer",
    "token_relay.py": "the relay key (read, stored, printed by key-export); the token seeded",
    "token_relay_backend.py": "the token record encrypted and decrypted",
    "token_relay_store.py": "the token held, synced, pushed and adopted",
    "vault_agent.py": "every request's value and every answer; the unlock passphrase held in memory",
    "vault_agent_runtime.py": "the agent's IPC key and token, written to and read from the state file (written only "
                              "into a file and a folder proved private to the user and the system account)",
    "vault_broker_client.py": "every request and answer; the IPC key read from the state file",
    "vault_credentials.py": "the passphrase and typed values; vault reads; a child's environment",
    "vault_tray.py": "the passphrase from the Win32 dialog to the agent",
    "vaultctl.py": "the passphrase and a typed value; the access token printed; a child's environment",
    "secret_store/accept.py": "the payload of every object this computer reads, opened to judge a commit",
    "secret_store/accept_rules.py": "an oauth payload and its baseline, compared field by field",
    "secret_store/broker_backend.py": "every value the agent serves or saves; the old vault's values for the migration",
    "secret_store/canonical.py": "the canonical bytes of every payload before encryption and after decryption",
    "secret_store/delete_ops.py": "no value: the tombstones it seals carry the empty payload {}; listed here because "
                                  "build_delete and build_signin_delete reach envelope.seal through _tombstone_commit and "
                                  "seal_object (the stricter class)",
    "secret_store/enrol.py": "new private keys; every object re-keyed at approval; the challenge",
    "secret_store/envelope.py": "the payload sealed and opened",
    "secret_store/handover.py": "the grant re-sealed to the new refresher; every object re-keyed",
    "secret_store/hpke.py": "data keys and the challenge: the cipher's seal and open",
    "secret_store/journal.py": "refresh records with the provider's answer",
    "secret_store/keys.py": "this computer's private keys, generated, stored and loaded",
    "secret_store/oauth_ops.py": "sign-in records, grants and static payloads read, merged, split and sealed",
    "secret_store/pending.py": "pending-write records with the typed values",
    "secret_store/recovery.py": "the recovery words and the keys derived from them",
    "secret_store/recovery_package.py": "the package: the data key, and the checkpoint and bundle it encrypts",
    "secret_store/replace_ops.py": "the kept shared settings of a replaced sign-in; journal records opened",
    "secret_store/repo.py": "no value of its own: git over sealed objects and the policy; listed here because pull "
                            "runs the store's verify callback inside its frames, which opens every object this "
                            "computer reads, so SecretRepo.pull is on every recorded chain to open (the stricter class)",
    "secret_store/static_fields.py": "every static payload: its values and kinds, read, copied and rewritten",
    "secret_store/store.py": "every payload read (get_record, get_typed, get_fields, static_payload) and written; the "
                             "recovery words at init and restore",
    "secret_store/store_ops.py": "payloads sealed (build_put, seal_object) and re-keyed (build_policy_change)",
    "secret_store/team.py": "the team recovery words and keys; every object re-keyed at a policy change",
    "secret_store/typed_write.py": "the typed plain and grant values of one write, and its record",
}
NO_CREDENTIAL: dict[str, str] = {  # module -> why none does
    "migration_lock.py": "a lock file with a process id, a time and a command name",
    "secret_store/__init__.py": "re-exports the error class",
    "secret_store/checkpoint.py": "object ids, revisions and hashes, signed with the key object",
    "secret_store/errors.py": "the error classes",
    "secret_store/fileio.py": "locks, and bytes already sealed (the journal, pending and hand-over files)",
    "secret_store/policy.py": "public keys, assignments, groups and signatures",
    "secret_store/provider_profiles.py": "field names per provider",
    "secret_store/signing.py": "signatures over documents and sealed objects, with the key object",
}
# What a no-credential module may import from a credential module: (importer, imported) -> names.
# A whole-module import ("from . import canonical") is allowed only with the attributes it uses.
EXEMPT_IMPORTS: dict[tuple[str, str], tuple[tuple[str, ...], str]] = {
    ("migration_lock.py", "portable_vault.py"): (("CredentialError",), "the error class"),
    ("migration_lock.py", "vault_agent_runtime.py"): (("_pid_is_running",), "a process-id check; reads no state file"),
    ("secret_store/checkpoint.py", "secret_store/canonical.py"): (("dumps", "loads"), "the signed checkpoint document"),
    ("secret_store/checkpoint.py", "secret_store/keys.py"): (("key_id",), "the hash of a public key"),
    ("secret_store/policy.py", "secret_store/canonical.py"): (("dumps",), "hashes and endorsement bytes of documents"),
    ("secret_store/policy.py", "secret_store/hpke.py"): (("load_public_key",), "validates a public key"),
    ("secret_store/policy.py", "secret_store/keys.py"): (("key_id", "raw_public"), "public keys"),
    ("secret_store/signing.py", "secret_store/canonical.py"): (("dumps",), "the bytes signed or verified"),
}

# -- (c) public operations ------------------------------------------------------------------------
# parser (a module with an argparse parser, or "agent" for the names VaultAgent.handle dispatches on)
# -> operation -> (uses: the endpoint ids the scenario must produce; may: ids other branches add, each
# explained in the note; the scenario of test_credential_paths_runtime.py, or None with the reason no
# test can run it; the note). A person's review of the code, corroborated by the recorder, never derived.
_PULL = ("open", "hpke-open")  # a pull with new commits opens every object this computer reads
_STORE_READ = ("keychain-read", "open", "hpke-open")
_STORE_WRITE = _STORE_READ + ("seal", "hpke-seal")
_POLICY_WRITE = _STORE_WRITE + ("package",)
_NONE: tuple[str, ...] = ()
# the agent client: it reads the state file (agent-state-read) and spends the key (agent-connect) before every
# request; the scenarios' stand-in answers in-process without a state file, so those two pairs are excused
# there (the scenario "agent-state" records them on their own); agent-pipe is the in-process agent's handler
_AGENT = ("agent-client", "agent-state-read", "agent-connect", "agent-pipe")
OPERATIONS: dict[str, dict[str, tuple[tuple[str, ...], tuple[str, ...], str | None, str]]] = {
    "brain_secrets.py": {
        "init": (("words", "recovery-keys", "keygen", "keychain-write", "package", "hpke-seal"), _NONE, "cli-init",
                 "the words window (words-window) needs a display: the callback is injected"),
        "status": (("keychain-read",), _PULL, "cli-status", "names, state and pending-write ids only; a hand-over "
                   "file or a pending-write record, when one exists, is opened to name it"),
        "list": (_STORE_READ, _NONE, "cli-list", "the index: entry names"),
        "put": (_POLICY_WRITE + ("window",), _NONE, "cli-put", "the window needs a display: the typed values are "
                "injected; the record, the object, the index and the package follow"),
        "get-check": (_STORE_READ, _NONE, "cli-get-check", "field names printed"),
        "delete": (_POLICY_WRITE, _NONE, "cli-delete", "tombstones and the index, of the whole entry or with --field of "
                   "exactly one sign-in's oauth and grant objects; the typed name is a confirmation"),
        "recovery-package": (("keychain-read", "package", "hpke-seal"), _PULL, "cli-recovery-package",
                             "a pull with new commits opens every object this computer reads"),
        "restore": (("recovery-keys", "package-open", "hpke-open", "open", "window"), _NONE, "cli-restore",
                    "the words window needs a display: the words are injected"),
        "replace-signin": (_POLICY_WRITE, _NONE, "cli-replace-signin", "the hand-over file, the tombstones and the index"),
        "enrol-request": (("keychain-read", "keygen", "keychain-write", "hpke-open", "package", "hpke-seal"), _NONE,
                          "cli-enrol", "--fingerprint makes keys, a signed request and the computer's first package; "
                          "--request opens the challenge"),
        "enrol-approve": (_POLICY_WRITE, _NONE, "cli-enrol", "the challenge sealed, then every object re-keyed"),
        "team-init": (("keychain-read", "words", "recovery-keys", "keygen", "keychain-write", "package", "hpke-seal"),
                      _NONE, "cli-team", "as init, for the team repository"),
        "team-admit": (_POLICY_WRITE, _NONE, "cli-team", "objects whose readers change are re-keyed"),
        "team-groups": (_POLICY_WRITE, _NONE, "cli-team", "objects whose readers change are re-keyed"),
        "team-remove": (_POLICY_WRITE, _NONE, "cli-team", "every object the removed computer could read is re-keyed"),
        "handover-release": (_STORE_WRITE, _NONE, "cli-handover", "the grant re-sealed to the new refresher"),
        "handover-accept": (_STORE_READ + ("package", "hpke-seal"), _NONE, "cli-handover", "the policy change and the "
                            "prepared revision, then the package; no object is re-keyed (the moved grant is the prepared "
                            "revision)"),
        "supersede": (_STORE_READ + ("package", "hpke-seal"), _NONE, "cli-supersede", "no object is re-keyed (a disabled "
                      "refresher changes no readers); needs a verified provider profile: none is, so the scenario patches "
                      "the refusal away, and a restore of that history is refused by the real profiles"),
        "grant-scan": (_STORE_READ, _NONE, "cli-grant-scan", "static payloads opened; names printed"),
        "unfinished": (_STORE_WRITE, ("package",), "cli-unfinished", "list and --discard read records; --apply writes "
                       "through the normal path, and a record that adds an entry changes the policy (package)"),
    },
    # agent-pipe below the command lines: the scenarios' stand-in for the agent client answers through
    # the in-process agent's pipe handler, so the agent's own pairs are recorded under the command too
    "migrate_to_store.py": {
        "migrate": (_AGENT + ("vault-load", "vault-write") + _POLICY_WRITE, _NONE, "migrate",
                    "the old vault through the agent; every entry into the store; the scrub"),
        "rollback": (_AGENT + ("vault-load", "vault-write") + _STORE_READ, _NONE, "rollback",
                     "static values read from the store and restored through the agent"),
    },
    "vaultctl.py": {
        # the store-backed agent's own pairs come with each command; it loads its keys at its first one
        "status": (_AGENT + ("vaultctl-main", "keychain-read"), _PULL, "vaultctl", "status only; main is the sink "
                   "function; a hand-over file or pending-write record is opened to name it"),
        "unlock": (("vaultctl-prompt",) + _AGENT + ("vaultctl-main", "vault-load"), _NONE, "vaultctl",
                   "the passphrase, checked by the agent against the vault"),
        "lock": (_AGENT + ("vaultctl-main",), _NONE, "vaultctl", "no credential: the agent drops its held passphrase"),
        "access-token": (_AGENT + ("vaultctl-main", "open", "hpke-open"), ("keychain-read",), "vaultctl",
                         "the sign-in record opened; the access token printed, for piping"),
        "secret-put": (("vaultctl-prompt",) + _AGENT + ("vaultctl-main", "open", "hpke-open", "seal", "hpke-seal"),
                       ("keychain-read", "package"), "vaultctl", "a typed value to the agent: its record and object; the "
                       "package when the entry is new"),
        "run": (_AGENT + ("vaultctl-main", "open", "hpke-open"), ("keychain-read",), "vaultctl",
                "mapped fields read and put into the child's environment"),
    },
    "vault_credentials.py": {
        "init": (("prompt-passphrase", "vault-write", "credentials-main"), ("window",), "vault-credentials",
                 "--window asks in the masked window, which needs a display"),
        "check": (("prompt-passphrase", "vault-load", "credentials-main"), _NONE, "vault-credentials", ""),
        "list": (("prompt-passphrase", "vault-load", "credentials-main"), _NONE, "vault-credentials", "entry names printed"),
        "change-passphrase": (("prompt-passphrase", "vault-load", "vault-write", "credentials-main"), _NONE,
                              "vault-credentials", ""),
        "delete-entry": (("prompt-passphrase", "vault-load", "vault-write", "credentials-main"), _NONE, "vault-credentials",
                         "the typed name is a confirmation"),
        "delete-field": (("prompt-passphrase", "vault-load", "vault-write", "credentials-main"), _NONE, "vault-credentials",
                         "the typed name is a confirmation"),
        "put": (_AGENT + ("prompt-passphrase", "prompt-value", "vault-load", "vault-write", "credentials-main"),
                _NONE, "vault-credentials", "through the unlocked agent, else the vault"),
        "put-entry": (("prompt-passphrase", "prompt-value", "vault-load", "vault-write", "credentials-main"),
                      ("window",) + _AGENT, "vault-credentials", "--window asks in the masked window, which needs "
                      "a display, and with the agent unlocked writes through it"),
        "init-json": (("prompt-passphrase", "vault-load", "vault-write", "credentials-main"), _NONE, "vault-credentials", ""),
        "run": (_AGENT + ("prompt-passphrase", "vault-load", "credentials-main"), _NONE, "vault-credentials",
                "mapped fields into the child's environment"),
        "session": (("prompt-passphrase", "vault-load", "credentials-main"), _AGENT, "vault-credentials",
                    "mapped fields into the shell's environment; through the unlocked agent when it answers"),
    },
    "token_relay.py": {
        "status": (("session-passphrase", "vault-load", "relay-main"), _NONE, "token-relay", "versions and holders printed"),
        # the key commands go through the agent, which is vault-backed when the relay is in use (store off)
        "key-new": (("relay-key",) + _AGENT + ("vault-load", "vault-write", "relay-main"), _NONE, "token-relay",
                    "a new key, checked for an old one and stored through the agent"),
        "key-export": (_AGENT + ("vault-load", "relay-main"), _NONE, "token-relay", "the key read through the agent and "
                       "printed, to a terminal only"),
        "key-import": (("relay-prompt",) + _AGENT + ("vault-load", "vault-write", "relay-main"), _NONE, "token-relay",
                       "a typed key stored through the agent"),
        "seed": (("session-passphrase", "vault-load", "vault-write", "relay-encrypt", "relay-main"), _AGENT, "token-relay",
                 "the local token pushed as the shared record and saved with its version; through the agent when it is "
                 "unlocked, else the session passphrase"),
    },
    "vault_agent.py": {
        "serve": (("agent-auth-make", "agent-state-write", "agent-state-read", "agent-pipe"), _NONE, None,
                  "serve starts the real listener on this user's pipe with the key the agent made, writes the token and "
                  "key to the state file and reads it back to keep it there; its one caller of the pipe primitive, "
                  "_serve_connection, is run with a fake connection in every agent scenario, and the state file is "
                  "written and read in a temporary folder by the scenario agent-state"),
    },
    "vault_tray.py": {
        "(the tray)": (("tray-dialog", "agent-auth-make", "agent-state-write", "agent-state-read", "agent-pipe"), _NONE,
                       None, "pystray and the Win32 dialog need a desktop; the tray builds the same agent as serve (its "
                       "token and key) and runs serve_forever in its own process (_start_broker), which writes the token "
                       "and key to the state file and accepts connections; the tray reads the state file for its pid and "
                       "hands the typed passphrase to agent.unlock"),
    },
    "agent": {
        "status": (("agent-pipe", "keychain-read"), _PULL, "agent-store, agent-vault", "state only; with the store, a "
                   "hand-over file or a pending-write record, when one exists, is opened to name it"),
        "ping": (("agent-pipe",), _NONE, "agent-store", "no credential"),
        "lock": (("agent-pipe",), _NONE, "agent-store", "drops the held passphrase"),
        "unlock": (("agent-pipe", "vault-load"), _NONE, "agent-store, agent-vault", "the passphrase checked against the "
                   "vault, then held"),
        "get_fields": (("agent-pipe",) + _STORE_READ + ("vault-load",), _NONE, "agent-store, agent-vault",
                       "static fields; the vault when the store is off"),
        "get_json": (("agent-pipe",) + _STORE_READ + ("vault-load",), _NONE, "agent-store, agent-vault",
                     "a sign-in record by role; the vault when the store is off"),
        "set_json": (("agent-pipe",) + _POLICY_WRITE + ("vault-load", "vault-write"), _NONE, "agent-store, agent-vault",
                     "a typed JSON value with its record, or a refresh's save; the vault when the store is off"),
        "set_text": (("agent-pipe",) + _POLICY_WRITE + ("vault-load", "vault-write"), _NONE, "agent-store, agent-vault",
                     "a typed value with its record; the vault when the store is off"),
        "get_access_token": (("agent-pipe",) + _STORE_READ + ("vault-load",), _NONE, "agent-store, agent-vault",
                             "the access token only; the vault when the store is off"),
        "begin_refresh": (("agent-pipe",) + _STORE_WRITE, _NONE, "agent-store", "the record read; the calling record sealed"),
        "abort_refresh": (("agent-pipe", "open", "hpke-open"), _NONE, "agent-store", "the calling record read and removed"),
        "release_refresh": (("agent-pipe",), _NONE, "agent-store", "the lock released; nothing read"),
        "poll_refresh": (("agent-pipe",) + _STORE_READ, ("package", "hpke-seal"), "agent-store", "the published record "
                         "after a pull; a computer's first open builds its recovery package"),
        "clear_signin": (("agent-pipe",) + _STORE_WRITE, _NONE, "agent-store", "a revision without the tokens"),
        "sync_store": (("agent-pipe", "keychain-read"), _PULL, "agent-store", "a pull; new commits open every object "
                       "this computer reads"),
        "shutdown": (("agent-pipe",), _NONE, "agent-store", "refused as unsupported, then the connection closes"),
        "vault_list_entries": (("agent-pipe", "vault-load"), _NONE, "agent-vault", "names and kinds"),
        "vault_get_fields": (("agent-pipe", "vault-load"), _NONE, "agent-vault", "values for the migration"),
        "vault_get_json": (("agent-pipe", "vault-load"), _NONE, "agent-vault", "a sign-in for the migration"),
        "vault_verify_copy": (("agent-pipe", "vault-load"), _NONE, "agent-vault", "the backup copy's entry names"),
        "vault_scrub_signin": (("agent-pipe", "vault-load", "vault-write"), _NONE, "agent-vault", "the tokens removed"),
        "vault_restore_static": (("agent-pipe", "vault-load", "vault-write"), _NONE, "agent-vault", "static values restored "
                                 "under names the marker does not hold; the whole request checked before one write"),
        "vault_restore_marked_static": (("agent-pipe", "vault-load", "vault-write"), _NONE, "agent-vault", "static values "
                                        "restored under names the marker holds, the marker left as it is; the whole "
                                        "request checked before one write (the rollback's late fields)"),
        "vault_clear_migration_marker": (("agent-pipe",), _NONE, "agent-vault", "the marker file only"),
    },
}
# Operations the scenarios reach only through another operation's code: the connector's refresh path.
EXTRA_OPERATIONS: dict[str, tuple[tuple[str, ...], tuple[str, ...], str | None, str]] = {
    "refresh path": (("token-endpoint", "session-passphrase") + _AGENT + _STORE_WRITE, _NONE, "refresh-path",
                     "a connector's PortableVaultJsonStore (the session passphrase read, unused with the agent), its "
                     "token call under the store's refresh: token_endpoint.post_token, the agent's begin_refresh and "
                     "the publication"),
    "the agent's state file": (("agent-auth-make", "agent-state-write", "agent-state-read"), _NONE, "agent-state",
                               "an agent made in-process, its token and key written to and read from a state file in a "
                               "temporary folder, then removed; agent-connect needs the real pipe and is never run"),
}
