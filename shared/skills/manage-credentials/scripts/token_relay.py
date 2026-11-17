"""Token relay: several brains share one rotating OAuth sign-in through an encrypted remote record.

Configuration lives in token-relay.json beside the vault file: the vault the running Vault Agent
serves when the work goes through it, else the named or default vault, else (a session copy, whose
own memory holds no vault) the default vault under brain_root in /memory/OWNER.md; resolve_config
lists the places in that order. An entry it does not list, or a missing file, leaves the store as
it was, with one exception: a token that carries a relay version and finds no file is refused a
refresh (refuse_unrelayed_refresh), so a stale refresh token never reaches the provider. For a listed entry the relayed store in
token_relay_store syncs with the remote record, takes a lease before a refresh and pushes saves
as new versions; token_relay_backend holds the record format and the backends.

Command line: status, key-new, key-export, key-import, seed --entry NAME [--replace]. seed --replace
overwrites an existing shared record, readable or not, at a version above both this computer's and
the old record's; it is the next step after a new authorisation the relay kept local-only. The
relay names this computer by token_relay_store.holder_name: the hostname plus a random id kept in
a non-secret file beside the vault. The key commands always go through the Vault Agent; status and seed do when it
is unlocked. Either way, --vault must then name the vault the agent serves.
Known limit: PortableVaultJsonStore itself (through BrokerOAuthStore) does not check that the
agent serves the vault its path names; that is left unchanged, so the relay-off behaviour is too.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
import types
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

import portable_vault
from portable_vault import CredentialError, PortableVault
from token_relay_backend import (
    MAX_LEASE_SECONDS,
    MIN_LEASE_SECONDS,
    Conflict,
    GitHubBackend,
    MemoryBackend,
    RelayError,
    RelayIntegrityError,
    RelayUnavailable,
    build_record,
    decode_key,
    dump_record,
    new_key_text,
    parse_record,
    remote_name,
    strip_bookkeeping,
    validate_entry,
)
import token_relay_store
from token_relay_store import DEFAULT_LEASE_SECONDS, RelayedStore, _now_iso, _version


CONFIG_NAME = "token-relay.json"
KEY_ENTRY = "token-relay"
KEY_FIELD = "relay_key"
RELAYED_FIELD = "oauth_token_json"

__all__ = [
    "Conflict",
    "MemoryBackend",
    "RelayConfig",
    "RelayError",
    "RelayIntegrityError",
    "RelayUnavailable",
    "RelayedStore",
    "config_candidates",
    "config_path",
    "load_config",
    "refuse_unrelayed_refresh",
    "relay_for",
    "resolve_config",
]


@dataclass
class RelayConfig:
    backend: str
    repository: str
    entries: list[str] = field(default_factory=list)
    lease_seconds: int = DEFAULT_LEASE_SECONDS


def config_path(vault_path: Path | str | None = None) -> Path:
    """token-relay.json in the vault's folder, the vault resolved as PortableVault resolves it."""
    return PortableVault(vault_path).path.parent / CONFIG_NAME


def _owner_brain_root(root: Path) -> Path | None:
    """brain_root from the front matter of <root>/memory/OWNER.md, or None."""
    try:
        lines = (root / "memory" / "OWNER.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip() == "brain_root":
            value = value.strip().strip("\"'")
            return Path(value) if value else None
    return None


def _agent_vault_path() -> Path | None:
    """The vault the unlocked Vault Agent serves, or None when no agent is unlocked."""
    from vault_broker_client import BrokerUnavailable, broker_status, broker_unlocked

    if not broker_unlocked():
        return None
    try:
        served = broker_status().get("vault_path")
    except (BrokerUnavailable, CredentialError, OSError):
        return None
    return Path(served) if isinstance(served, str) and served else None


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))


def config_candidates(vault_path: Path | str | None = None, *, use_agent: bool = True) -> list[Path]:
    """Where token-relay.json is looked for, in this order (the vault actually in use first):
    1. beside the vault the unlocked Vault Agent serves, when use_agent (the work goes through it);
    2. beside the named vault, else PORTABLE_VAULT_PATH, else the default under this brain root;
    3. when that vault is this brain root's default one, beside the default vault under brain_root
       in /memory/OWNER.md: in a session copy that is the shared checkout, which holds the vault.
    Never only the script's own root, so a session copy finds the shared checkout's config."""
    vaults: list[Path] = []
    if use_agent:
        served = _agent_vault_path()
        if served is not None:
            vaults.append(served)
    named = PortableVault(vault_path).path
    vaults.append(named)
    own_root = portable_vault.find_brain_root()
    default = portable_vault.default_vault_path()
    if _same(named, default):
        owner_root = _owner_brain_root(own_root)
        if owner_root is not None:
            vaults.append(owner_root / default.relative_to(own_root))
    unique: list[Path] = []
    for vault in vaults:
        if not any(_same(vault, seen) for seen in unique):
            unique.append(vault)
    return [vault.parent / CONFIG_NAME for vault in unique]


def resolve_config(
    vault_path: Path | str | None = None, *, use_agent: bool = True
) -> tuple[Path | None, list[Path]]:
    """The first token-relay.json that exists among config_candidates, and every place looked."""
    looked = config_candidates(vault_path, use_agent=use_agent)
    return next((path for path in looked if path.is_file()), None), looked


def _expires_within(token: dict[str, Any], seconds: float) -> bool:
    try:
        return float(token.get("expires_at", 0)) <= time.time() + seconds
    except (TypeError, ValueError):
        return True


def refuse_unrelayed_refresh(
    store: Any,
    *,
    refresh: bool = False,
    leeway_seconds: float | None = None,
    new_authorisation: bool = False,
) -> None:
    """Fail closed. A store relay_for left off because no token-relay.json was found, whose stored
    token carries a relay version, is refused a forced refresh, a new authorisation, or a refresh
    the leeway makes due: nothing goes to the provider. A store with a config (its entry unlisted),
    another field, or a token never relayed is left alone, and a plain lock is not refused."""
    if getattr(store, "relay_config_path", None) is not None or store.field != RELAYED_FIELD:
        return
    due = refresh or new_authorisation
    if not due and leeway_seconds is None:
        return
    token = store._local_load()
    version = _version(token)
    if not version or not (due or _expires_within(token, leeway_seconds)):
        return
    looked = "; ".join(str(path) for path in getattr(store, "relay_config_looked", None) or [])
    raise CredentialError(
        f"Refresh of {store.entry} refused: its stored token carries token relay version {version}, "
        f"but no {CONFIG_NAME} was found (looked in: {looked}). Nothing was sent to the provider. "
        "Run from the checkout whose vault holds the relay config, or put the config beside the "
        "vault in use."
    )


def load_config(path: Path) -> RelayConfig | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CredentialError(f"The token relay configuration cannot be read: {path}") from exc
    if not isinstance(raw, dict):
        raise CredentialError("The token relay configuration must be a JSON object.")
    backend = raw.get("backend")
    if backend != "github":
        raise CredentialError("The token relay backend must be \"github\".")
    entries = raw.get("entries", [])
    if not isinstance(entries, list) or not all(isinstance(item, str) for item in entries):
        raise CredentialError("The token relay entries must be a list of vault entry names.")
    for entry in entries:
        validate_entry(entry)
    lease = raw.get("lease_seconds", DEFAULT_LEASE_SECONDS)
    if (
        not isinstance(lease, int)
        or isinstance(lease, bool)
        or not MIN_LEASE_SECONDS <= lease <= MAX_LEASE_SECONDS
    ):
        raise CredentialError(
            "The token relay lease_seconds must be a whole number from "
            f"{MIN_LEASE_SECONDS} to {MAX_LEASE_SECONDS}."
        )
    repository = raw.get("repository")
    if not isinstance(repository, str):
        raise CredentialError("The token relay repository must be written as owner/name.")
    return RelayConfig(backend, repository, [e for e in entries if e != KEY_ENTRY], lease)


def make_backend(config: RelayConfig) -> Any:
    return GitHubBackend(config.repository)


# -- integration with PortableVaultJsonStore ---------------------------------------------------


def read_relay_key(store: Any = None) -> bytes:
    """The relay key from the vault: through the Vault Agent broker, else an in-process unlock."""
    broker = getattr(store, "_broker", None) if store is not None else None
    if store is None or broker is not None:
        from vault_broker_client import broker_request, broker_unlocked

        if not broker_unlocked():
            raise CredentialError("Vault Agent is locked or unavailable; the relay key cannot be read.")
        values = broker_request("get_fields", entry=KEY_ENTRY, fields=[KEY_FIELD])
    else:
        values = store.vault.get_fields(KEY_ENTRY, [KEY_FIELD], store.passphrase)
    if not isinstance(values, dict):
        raise CredentialError("The relay key is missing or malformed.")
    return decode_key(values.get(KEY_FIELD))


def relay_for(store: Any) -> RelayedStore | None:
    """The relayed behaviour for a PortableVaultJsonStore, or None when the relay is off. The
    config used (or None) and the places looked are left on the store as relay_config_path and
    relay_config_looked, for refuse_unrelayed_refresh and for callers that report them."""
    found, looked = resolve_config(
        store.vault.path, use_agent=getattr(store, "_broker", None) is not None
    )
    store.relay_config_path = found
    store.relay_config_looked = looked
    config = load_config(found) if found is not None else None
    if config is None or store.field != RELAYED_FIELD or store.entry not in config.entries:
        return None
    local = types.SimpleNamespace(
        load=store._local_load, save=store._local_save, rotation_lock=store._local_rotation_lock
    )
    return RelayedStore(
        local,
        store.entry,
        backend=make_backend(config),
        key_provider=lambda: read_relay_key(store),
        lease_seconds=config.lease_seconds,
        holder=token_relay_store.holder_name(store.vault.path),
    )


# -- command line ------------------------------------------------------------------------------


def _store_key(text: str) -> None:
    from vault_broker_client import broker_request, broker_unlocked

    decode_key(text)
    if not broker_unlocked():
        raise CredentialError("Unlock the Vault Agent first: the relay key is stored through it.")
    broker_request("set_text", entry=KEY_ENTRY, field=KEY_FIELD, value=text)


def _check_vault(vault: str | None) -> None:
    """The key commands go through the running Vault Agent, so --vault must name its vault."""
    if not vault:
        return
    from vault_broker_client import broker_status

    served = broker_status().get("vault_path")
    wanted = os.path.normcase(str(PortableVault(vault).path.resolve()))
    if not isinstance(served, str) or os.path.normcase(str(Path(served).resolve())) != wanted:
        raise CredentialError(
            "--vault names a vault other than the one the running Vault Agent serves; the key "
            "commands work through the agent, so they are refused."
        )


def _hidden_input(prompt: str) -> str:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", getpass.GetPassWarning)
        value = getpass.getpass(prompt)
        if any(issubclass(item.category, getpass.GetPassWarning) for item in caught):
            raise CredentialError("Hidden input is unavailable here; refusing echoed input.")
    return value


def _key_exists() -> bool:
    try:
        read_relay_key()
    except CredentialError:
        return False
    return True


def _status(vault: str | None, out: TextIO) -> int:
    from portable_vault import PortableVaultJsonStore

    found, looked = resolve_config(vault)
    config = load_config(found) if found is not None else None
    if config is None:
        reason = f"no {CONFIG_NAME} found; looked in: " + "; ".join(str(path) for path in looked)
        print(json.dumps({"relay": "off", "reason": reason}), file=out)
        return 0
    backend = make_backend(config)
    for entry in config.entries:
        row: dict[str, Any] = {"entry": entry, "relay": "on", "relay_config": str(found)}
        try:
            content, _ = backend.get(remote_name(entry))
            record = parse_record(content, entry) if content else None
            row["remote_version"] = record["version"] if record else None
            lease = record.get("lease") if record else None
            row["lease_holder"] = lease["holder"] if lease else None
            row["lease_seconds"] = lease["seconds"] if lease else None
        except RelayError as exc:
            row["remote_error"] = str(exc)
        try:
            raw = PortableVaultJsonStore(entry, path=vault)._local_load()
            row["local_version"] = _version(raw)
            row["unpushed"] = bool(raw.get("_relay_unpushed"))
        except CredentialError as exc:
            row["local_error"] = str(exc)
        print(json.dumps(row), file=out)
    return 0


def _seed(entry: str, vault: str | None, out: TextIO, replace: bool = False) -> int:
    """Push this computer's token as the shared record. With replace, an existing record,
    readable or not (a rotated key, a corrupt file), is overwritten; the new version is one more
    than both this computer's version and the old record's, when that parses, so it never goes
    down for any brain."""
    from portable_vault import PortableVaultJsonStore

    found, _ = resolve_config(vault)
    config = load_config(found) if found is not None else None
    if config is None or entry not in config.entries:
        raise CredentialError(f"{entry} is not listed in {CONFIG_NAME}.")
    store = PortableVaultJsonStore(entry, path=vault)
    backend = make_backend(config)
    with store._local_rotation_lock():
        content, tag = backend.get(remote_name(entry))
        if content is not None and not replace:
            raise CredentialError(
                f"{entry} already has a shared record; seed refused (pass --replace to overwrite it)."
            )
        raw = store._local_load()
        token = strip_bookkeeping(raw)
        if not token.get("refresh_token"):
            raise CredentialError(f"{entry} holds no refresh token on this computer to seed.")
        remote_version = 0
        if content is not None:
            try:
                remote_version = parse_record(content, entry)["version"]
            except RelayIntegrityError:
                remote_version = 0
        version = max(_version(raw), remote_version) + 1
        holder = token_relay_store.holder_name(store.vault.path)
        record = build_record(
            read_relay_key(store), entry, version, token, lease=None, holder=holder,
            updated_at=_now_iso(time.time),
        )
        action = "seed --replace" if content is not None else "seed"
        backend.put(
            remote_name(entry), dump_record(record), tag if content is not None else None,
            f"token-relay: {entry} {action} version {version} by {holder}",
        )
        store._local_save({**token, "_relay_version": version})
    print(f"Seeded {entry} as version {version}.", file=out)
    return 0


def _agent_unlocked() -> bool:
    from vault_broker_client import broker_unlocked

    return broker_unlocked()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Share a rotating OAuth sign-in between brains.")
    parser.add_argument("--vault", help="Vault path (defaults as PortableVault resolves it)")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Relay state per listed entry; never a secret")
    new = commands.add_parser("key-new", help="Make a relay key and store it in the vault")
    new.add_argument("--replace", action="store_true", help="Replace an existing key")
    commands.add_parser("key-export", help="Print the relay key, to a terminal only")
    imported = commands.add_parser("key-import", help="Store a relay key typed at a hidden prompt")
    imported.add_argument("--replace", action="store_true", help="Replace an existing key")
    seed = commands.add_parser("seed", help="Push this computer's token as the shared record")
    seed.add_argument("--entry", required=True)
    seed.add_argument(
        "--replace", action="store_true",
        help="Overwrite an existing shared record, readable or not, at a higher version",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.vault:
        os.environ["PORTABLE_VAULT_PATH"] = args.vault
    try:
        if args.command in {"key-new", "key-import", "key-export"}:
            _check_vault(args.vault)
        elif args.vault and _agent_unlocked():
            # status and seed read the vault through the running Vault Agent when it is
            # unlocked, so --vault must name the vault it serves, as for the key commands.
            _check_vault(args.vault)
        if args.command == "status":
            return _status(args.vault, sys.stdout)
        if args.command in {"key-new", "key-import"}:
            if _key_exists() and not args.replace:
                raise CredentialError("A relay key is already stored; pass --replace to change it.")
            text = new_key_text() if args.command == "key-new" else _hidden_input("Relay key: ")
            _store_key(text.strip())
            print(f"The relay key is stored in the vault entry {KEY_ENTRY}.")
            return 0
        if args.command == "key-export":
            if not sys.stdout.isatty():
                raise CredentialError("key-export prints only to a terminal, never to a pipe or file.")
            import base64

            print(base64.b64encode(read_relay_key()).decode("ascii"))
            return 0
        if args.command == "seed":
            return _seed(args.entry, args.vault, sys.stdout, replace=args.replace)
    except CredentialError as exc:
        print(f"Token relay failed: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
