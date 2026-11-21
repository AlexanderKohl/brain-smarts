"""Copy the portable vault into the synced secrets store (design synced-secrets-repository.md).

Needs the Vault Agent unlocked on the OLD vault. First a verified backup copy of the vault (a byte
copy, then an authenticated load of the copy by the agent), then every entry into the store: text
fields as a static object, JSON sign-in fields (oauth_token_json) as an oauth plus a grant object
with this computer as refresher. Grant fields (client_secret and the like) always go to a grant,
never a static object: with no sign-in yet, to an empty sign-in created for them. No value is ever
printed. A migration record (entry names, time, backup path) is written beside the backup.

Round-8 review: once the store is verified to hold a sign-in, the old vault's copy has its tokens
removed (access, refresh and every grant or token field) and a migration marker beside the vault
(credentials.vault.migrated.json) names it; every legacy OAuth path refuses a marked sign-in, store
on or off, and a later migration leaves marked entries alone. The rollback restores static
secrets only (they never rotate), from the store's current value; it never writes a token out of
the store. Every migrated sign-in keeps no token in the old vault and needs a browser sign-in.

  python migrate_to_store.py --dry-run            list entry and field names only
  python migrate_to_store.py [--replace]          copy; --replace overwrites entries the store holds
  python migrate_to_store.py rollback --dry-run   list what the rollback would restore
  python migrate_to_store.py rollback             restore static secrets; sign-ins need a browser sign-in
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from portable_vault import CredentialError, migrated_signins  # noqa: E402
from secret_store import oauth_ops, provider_profiles  # noqa: E402
from secret_store.broker_backend import TOKEN_KEYS, StoreBackend, put_grant_fields  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402


def _plan(request: Callable, entry: str, fields: dict[str, str]) -> dict[str, Any]:
    """What the store will hold for one entry; values stay in memory and are never printed."""
    text = sorted(f for f, kind in fields.items() if kind == "text")
    values = request("vault_get_fields", entry=entry, fields=text) if text else {}
    signins, static = {}, {}
    for field in sorted(f for f, kind in fields.items() if kind == "json"):
        value = request("vault_get_json", entry=entry, field=field)
        if oauth_ops.looks_like_signin(value):
            signins[field] = value
        else:
            static[field] = json.dumps(value, sort_keys=True)
    grant_keys = provider_profiles.grant_fields(provider_profiles.provider_for(entry))
    grant = {f: v for f, v in values.items() if f in grant_keys}
    static.update({f: v for f, v in values.items() if f not in grant})
    fields_of_signins = list(signins)
    if grant and not signins:  # an empty sign-in holds them; its placeholder leaves the static object
        if static.get(oauth_ops.DEFAULT_FIELD) == "{}":
            del static[oauth_ops.DEFAULT_FIELD]
        fields_of_signins = [oauth_ops.DEFAULT_FIELD]
    names = ([entry] if static else []) + [n for f in fields_of_signins for n in oauth_ops.signin_names(entry, f)]
    return {"entry": entry, "static": static, "signins": signins, "grant": grant, "names": names}


def _copy(store: Any, plan: dict[str, Any], replace: bool) -> None:
    for number, (field, record) in enumerate(sorted(plan["signins"].items())):
        oauth_ops.put_signin(store, plan["entry"], field, record,
                             grant_fields=plan["grant"] if number == 0 else None, replace=replace)
    if plan["grant"] and not plan["signins"]:
        put_grant_fields(store, store._group(None), plan["entry"], plan["grant"])
    if plan["static"]:
        store.put_entry(plan["entry"], plan["static"])


def _backup(request: Callable, vault_path: Path, backup_dir: Any, names: list[str]) -> Path:
    folder = Path(backup_dir) if backup_dir else vault_path.parent / "migration-backups"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target, number = folder / f"{vault_path.stem}-{stamp}{vault_path.suffix}", 1
    while target.exists():
        number += 1
        target = folder / f"{vault_path.stem}-{stamp}-{number}{vault_path.suffix}"
    shutil.copyfile(vault_path, target)
    if target.read_bytes() != vault_path.read_bytes():
        raise CredentialError("the backup copy differs from the vault; nothing was copied")
    if sorted(request("vault_verify_copy", path=str(target))) != names:
        raise CredentialError("the backup copy did not load with the same entries; nothing was copied")
    return target


def _unlocked_status(request: Callable, out: Callable[[str], None]) -> Any:
    status = request("status")
    unlocked = status.get("vault_unlocked", status.get("unlocked")) if isinstance(status, dict) else False
    if not unlocked:
        out("The Vault Agent is not unlocked on the old vault. Unlock it from the tray, then run this again.")
        return None
    return status


def _verified(backend: StoreBackend, entry: str, field: str, record: dict) -> bool:
    """The store, read back, holds the sign-in's tokens as the vault had them."""
    try:
        held = backend.get_json(entry, field)
    except (CredentialError, SecretStoreError):
        return False
    keys = (TOKEN_KEYS | {"user_token"}) & set(record)
    return all(held.get(k) == record[k] for k in keys)


def migrate(request: Callable, open_store: Callable[[], Any], *, dry_run: bool = False, replace: bool = False,
            backup_dir: Any = None, out: Callable[[str], None] = print) -> int:
    status = _unlocked_status(request, out)
    if status is None:
        return 2
    listing = request("vault_list_entries")
    marked = migrated_signins(status["vault_path"]) if status.get("vault_path") else {}
    done = sorted(e for e in listing if e in marked)
    if done:
        out("Already migrated, left as they are: " + ", ".join(done) + ".")
    if dry_run:
        out(f"Dry run: {len(listing) - len(done)} entries would be copied into the store; nothing was changed.")
        for entry in sorted(e for e in listing if e not in marked):
            out(f"  {entry}: " + ", ".join(f"{f} ({k})" for f, k in sorted(listing[entry].items())))
        return 0
    store = open_store()
    plans = [_plan(request, entry, fields) for entry, fields in sorted(listing.items()) if entry not in marked]
    existing = set(store.list_entries())
    clashes = sorted(n for plan in plans for n in plan["names"] if n in existing)
    if clashes and not replace:
        out("The store already holds " + ", ".join(clashes)
            + ". Nothing was copied; run again with --replace to overwrite them.")
        return 3
    names = sorted(listing)
    backup = _backup(request, Path(status["vault_path"]), backup_dir, names)
    for plan in plans:
        _copy(store, plan, replace)
    backend, retired, unverified = StoreBackend(store, sync_seconds=0), [], []
    for plan in plans:
        for field, value in sorted(plan["signins"].items()):
            name = f"{plan['entry']}#{field}"
            if _verified(backend, plan["entry"], field, value):
                request("vault_scrub_signin", entry=plan["entry"], field=field)
                retired.append(name)
            else:
                unverified.append(name)
    record = backup.with_name(backup.stem + ".migration.json")
    record.write_text(json.dumps({"entries": names, "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                                  "backup": str(backup), "replace": replace, "retired_signins": retired},
                                 indent=2) + "\n", "utf-8")
    out(f"Copied {len(plans)} entries into the store. Sign-ins whose old vault copy is retired (tokens removed, "
        f"migration marker written): {', '.join(retired) or 'none'}. Verified backup: {backup}. "
        f"Migration record: {record}.")
    if unverified:
        out("The store could not be read back for " + ", ".join(unverified)
            + "; their old vault copy is unchanged. Run the migration again with --replace.")
        return 4
    return 0


def rollback(request: Callable, open_store: Callable[[], Any], *, dry_run: bool = False,
             out: Callable[[str], None] = print) -> int:
    """Put the store's current static secrets back into the old vault (static secrets never rotate)
    and clear the migration marker. A migrated sign-in gets nothing back: no token ever leaves the
    store, and the old vault holds none, so each needs a browser sign-in."""
    status = _unlocked_status(request, out)
    if status is None:
        return 2
    marked = migrated_signins(status["vault_path"])
    listing = request("vault_list_entries")
    store = open_store()
    statics = []
    for entry, kinds in sorted(listing.items()):
        try:
            record = store.get_record(entry)
        except (CredentialError, SecretStoreError, KeyError):
            continue
        fields = {f: v for f, v in (record or {}).items()
                  if isinstance(v, str) and f not in marked.get(entry, []) and f in kinds}
        if fields:
            statics.append((entry, fields, kinds))
    restored = ", ".join(f"{e} ({', '.join(sorted(f))})" for e, f, _k in statics) or "none"
    signins = [f"{e}#{f}" for e, fields in sorted(marked.items()) for f in sorted(fields)]
    if dry_run:
        out(f"Dry run: the rollback would restore these static secrets from the store: {restored}. "
            "Nothing was changed.")
    for entry, fields, kinds in ([] if dry_run else statics):
        request("vault_restore_static", entry=entry, values={
            f: {"value": json.loads(v) if kinds[f] == "json" else v, "kind": kinds[f]} for f, v in fields.items()})
    for name in signins:
        out(f"{name}: sign in again in the browser; no token is brought back from the store.")
    if dry_run:
        return 0
    if marked:
        request("vault_clear_migration_marker")
    out(f"Restored static secrets from the store: {restored}. Switch the secrets store off (enabled false in "
        "secret-store.json) and restart the Vault Agent before using the old vault.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["migrate", "rollback"], default="migrate",
                        help="migrate (the default) or rollback")
    parser.add_argument("--dry-run", action="store_true", help="list entry and field names only")
    parser.add_argument("--replace", action="store_true", help="overwrite entries the store already holds")
    parser.add_argument("--backup-dir", help="folder for the backup (default: migration-backups beside the vault)")
    args = parser.parse_args(argv)
    from secret_store.store import SecretStore
    from vault_broker_client import broker_request
    try:
        if args.command == "rollback":
            return rollback(broker_request, lambda: SecretStore().open(), dry_run=args.dry_run)
        return migrate(broker_request, lambda: SecretStore().open(), dry_run=args.dry_run,
                       replace=args.replace, backup_dir=args.backup_dir)
    except (CredentialError, SecretStoreError) as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
