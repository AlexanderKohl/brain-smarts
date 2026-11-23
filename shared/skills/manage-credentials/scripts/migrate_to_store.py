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
The rollback walks every static object of the store, so an entry or field created after the
migration comes back too, a static field under a migrated sign-in's name included. Each static
field comes back at the kind recorded beside it in the store (plan N2: the migration records the
old vault's kind, every later writer the kind it wrote); nothing else decides. It names each entry
it restored and each it could not (a field with no recorded kind, from a store made before kinds
were kept: store the entry again; a token; a sign-in the store still holds under that name), and
one it could not makes the exit code 5 and keeps the migration marker.

  python migrate_to_store.py --dry-run            list entry and field names only
  python migrate_to_store.py [--replace]          copy; --replace overwrites entries the store holds
  python migrate_to_store.py rollback --dry-run   list what the rollback would restore
  python migrate_to_store.py rollback             restore static secrets; sign-ins need a browser sign-in
"""

from __future__ import annotations

import argparse
import contextlib
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

from migration_lock import MigrationLock  # noqa: E402
from portable_vault import CredentialError, migrated_signins  # noqa: E402
from secret_store import oauth_ops, provider_profiles  # noqa: E402
from secret_store.broker_backend import TOKEN_KEYS, StoreBackend, put_grant_fields  # noqa: E402
from secret_store.errors import SecretStoreError  # noqa: E402


def _say(text: str) -> None:
    """The default out: standard output, flushed at once, so each progress line shows as it happens
    (plan R23, rule 4: one entry takes a few seconds, and silence reads as a hang)."""
    print(text, flush=True)


def _field_names(plan: dict[str, Any]) -> str:
    """One entry's field names for its progress line; never a value."""
    return ", ".join(sorted(set(plan["static"]) | set(plan["signins"]) | set(plan["grant"])))


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
    kinds = {f: fields[f] for f in static}  # plan N2: the kind the old vault's listing gives
    return {"entry": entry, "static": static, "kinds": kinds, "signins": signins, "grant": grant, "names": names}


def _copy(store: Any, plan: dict[str, Any], replace: bool) -> None:
    for number, (field, record) in enumerate(sorted(plan["signins"].items())):
        oauth_ops.put_signin(store, plan["entry"], field, record,
                             grant_fields=plan["grant"] if number == 0 else None, replace=replace)
    if plan["grant"] and not plan["signins"]:
        put_grant_fields(store, store._group(None), plan["entry"], plan["grant"])
    if plan["static"]:
        store.put_entry(plan["entry"], plan["static"], field_kinds=plan["kinds"])


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


def _held(status: Any, command: str) -> Any:
    """The migration lock beside the agent's vault for the whole command (round-9 plan, M5)."""
    path = status.get("vault_path") if isinstance(status, dict) else None
    return MigrationLock(path, command) if path else contextlib.nullcontext()


def _remove_unverified(store: Any, unverified: list[tuple[str, str]]) -> list[str]:
    """Round-9 plan, M4: a sign-in whose read-back failed loses its store copy in this run, so it
    never lives in two places; returns the store names that could not be removed."""
    held, stuck = set(store.list_entries()), []
    for entry, field in unverified:
        for name in oauth_ops.signin_names(entry, field):
            if name in held:
                try:
                    store.delete_entry(name)
                except (CredentialError, SecretStoreError):
                    stuck.append(name)
    return stuck


def migrate(request: Callable, open_store: Callable[[], Any], *, dry_run: bool = False, replace: bool = False,
            backup_dir: Any = None, out: Callable[[str], None] = _say) -> int:
    status = _unlocked_status(request, out)
    if status is None:
        return 2
    with _held(status, "migrate"):
        return _migrate(request, open_store, status, dry_run, replace, backup_dir, out)


def _migrate(request: Callable, open_store: Callable[[], Any], status: Any, dry_run: bool, replace: bool,
             backup_dir: Any, out: Callable[[str], None]) -> int:
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
    out(f"Copying {len(plans)} entries; each is committed and pushed, which takes a few seconds an entry.")
    for number, plan in enumerate(plans, 1):
        _copy(store, plan, replace)
        out(f"  {number}/{len(plans)} {plan['entry']}: {_field_names(plan)}")
    backend, retired, unverified = StoreBackend(store, sync_seconds=0), [], []
    for plan in plans:
        for field, value in sorted(plan["signins"].items()):
            name = f"{plan['entry']}#{field}"
            if _verified(backend, plan["entry"], field, value):
                request("vault_scrub_signin", entry=plan["entry"], field=field)
                retired.append(name)
            else:
                unverified.append((plan["entry"], field))
    stuck = _remove_unverified(store, unverified) if unverified else []
    record = backup.with_name(backup.stem + ".migration.json")
    record.write_text(json.dumps({"entries": names, "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                                  "backup": str(backup), "replace": replace, "retired_signins": retired,
                                  "unverified_signins": [f"{e}#{f}" for e, f in unverified]},
                                 indent=2) + "\n", "utf-8")
    out(f"Copied {len(plans)} entries into the store. Sign-ins whose old vault copy is retired (tokens removed, "
        f"migration marker written): {', '.join(retired) or 'none'}. Verified backup: {backup}. "
        f"Migration record: {record}.")
    if unverified:
        out("The store could not be read back for " + ", ".join(f"{e}#{f}" for e, f in unverified)
            + "; their store copy was removed in this run and their old vault copy is unchanged and unmarked. "
            "Run the migration again with --replace, or sign them in again in the browser once the store is on.")
        if stuck:
            out("These store copies could not be removed; remove them before switching the store on: "
                + ", ".join(stuck) + ".")
        return 4
    return 0


def rollback(request: Callable, open_store: Callable[[], Any], *, dry_run: bool = False,
             out: Callable[[str], None] = _say) -> int:
    """Put the store's current static secrets back into the old vault (static secrets never rotate)
    and clear the migration marker. A migrated sign-in gets nothing back: no token ever leaves the
    store, and the old vault holds none, so each needs a browser sign-in."""
    status = _unlocked_status(request, out)
    if status is None:
        return 2
    with _held(status, "rollback"):
        return _rollback(request, open_store, status, dry_run, out)


def _value(text: str, kind: str | None) -> Any:
    """The old vault's value of one static store field at its recorded kind (plan N2: the kind kept
    in the store is the only authority). ValueError for a field with no recorded kind or a token."""
    if kind is None:
        raise ValueError("no kind")
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    if oauth_ops.looks_like_signin(parsed):
        raise ValueError("token")  # never a token out of the store, text or JSON
    return parsed if kind == "json" else text


def _static_plans(store: Any, marked: dict) -> tuple[list, list, list]:
    """Every static object of the store (Sol rounds 9 and 10): ([(entry, {field: {value, kind}})],
    [the same for fields under a migrated sign-in's name], [(entry, fields or None, reason)] that
    cannot be restored). A static field under a migrated sign-in's name is restored, unless the store
    still holds that sign-in: then it is shadowed and named."""
    plans, late, failed = [], [], []
    index = store._index(None)
    for entry, oid in sorted(index.items()):
        if store.policy.assignment(oid)[1] != "static":
            continue
        try:  # malformed or unknown kind data is refused here, before any value is used
            record, kinds = store.get_typed(entry)
        except (CredentialError, SecretStoreError) as error:
            failed.append((entry, None, str(error)))
            continue
        values, later, untyped, bad = {}, {}, [], []
        for field, text in sorted(record.items()):
            migrated = field in marked.get(entry, [])
            if migrated and oauth_ops.signin_names(entry, field)[0] in index:
                bad.append(field)  # the store still serves the sign-in under this name
                continue
            try:
                value = _value(text, kinds.get(field))
            except ValueError as error:
                (untyped if str(error) == "no kind" else bad).append(field)
                continue
            (later if migrated else values)[field] = {"value": value, "kind": kinds[field]}
        if untyped:
            failed.append((entry, untyped, "no kind is recorded for these fields (a store made before kinds were "
                                           f"kept); store the entry again, for example brain_secrets.py put --entry "
                                           f"{entry}, then run the rollback again"))
        if bad:
            failed.append((entry, bad, "a token, or a sign-in in the store has the same name"))
        if untyped or bad:
            continue
        if values:
            plans.append((entry, values))
        if later:
            late.append((entry, later))
    return plans, late, failed


def _names(items: list) -> str:
    return ", ".join(f"{e} ({', '.join(sorted(f))})" for e, f in items) or "none"


def _restore(request: Callable, plans: list, restored: list, failed: list, out: Callable[[str], None],
             operation: str = "vault_restore_static") -> None:
    for entry, values in plans:
        try:
            request(operation, entry=entry, values=values)
            restored.append((entry, values))
            out(f"  restored {entry}: {', '.join(sorted(values))}")
        except (CredentialError, SecretStoreError) as error:
            failed.append((entry, sorted(values), str(error)))
            out(f"  not restored {entry}: {', '.join(sorted(values))}")


def _restore_late(request: Callable, late: list, restored: list, failed: list, out: Callable[[str], None]) -> None:
    """Plan R11, rule 5: fields under a migrated sign-in's name come back through the agent's
    vault_restore_marked_static, which takes only names the marker holds and leaves the marker as it
    is. The marker is never cleared before the last step and nothing is scrubbed, so every marked
    name stays refused to every other caller until the clear, and a stop at any point keeps it."""
    _restore(request, late, restored, failed, out, "vault_restore_marked_static")


def _rollback(request: Callable, open_store: Callable[[], Any], status: Any, dry_run: bool,
              out: Callable[[str], None]) -> int:
    marked = migrated_signins(status["vault_path"])
    store = open_store()
    plans, late, failed = _static_plans(store, marked)
    signins = [f"{e}#{f}" for e, fields in sorted(marked.items()) for f in sorted(fields)]
    if dry_run:
        out(f"Dry run: the rollback would restore these static secrets from the store: {_names(plans + late)}. "
            "Nothing was changed.")
    restored = []
    if not dry_run:  # ordinary fields, then late fields; the marker is cleared below, only when all succeeded
        out(f"Restoring {len(plans) + len(late)} entries into the old vault through the agent.")
        _restore(request, plans, restored, failed, out)
        _restore_late(request, late, restored, failed, out)
    for name in signins:
        out(f"{name}: sign in again in the browser; no token is brought back from the store.")
    if failed:
        out(("Dry run: these entries could not be restored: " if dry_run else "These entries could not be restored: ")
            + "; ".join(f"{e}" + (f" ({', '.join(f)})" if f else "") + f": {why}" for e, f, why in failed) + ".")
    if dry_run:
        return 0 if not failed else 5
    if failed:
        out(f"Restored static secrets from the store: {_names(restored)}. The rollback is not complete: the "
            "migration marker stays. Settle the entries above, then run the rollback again.")
        return 5
    if marked:  # the last change to the old vault: every restore of both kinds succeeded
        request("vault_clear_migration_marker")
    out(f"Restored static secrets from the store: {_names(restored)}. Switch the secrets store off (enabled false "
        "in secret-store.json) and restart the Vault Agent before using the old vault.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=["migrate", "rollback"], default="migrate",
                        help="migrate (the default) or rollback")
    parser.add_argument("--dry-run", action="store_true", help="list entry and field names only")
    parser.add_argument("--replace", action="store_true", help="overwrite entries the store already holds")
    parser.add_argument("--backup-dir", help="folder for the backup; it must be inside the vault's own folder, where the "
                        "agent checks the copy (default: migration-backups beside the vault)")
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
