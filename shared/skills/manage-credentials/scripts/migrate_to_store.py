"""Copy the portable vault into the synced secrets store (design synced-secrets-repository.md).

Needs the Vault Agent unlocked on the OLD vault. First a verified backup copy of the vault (a byte
copy, then an authenticated load of the copy by the agent), then every entry into the store: text
fields as a static object, JSON sign-in fields (oauth_token_json) as an oauth plus a grant object
with this computer as refresher. Grant fields (client_secret and the like) always go to a grant,
never a static object: with no sign-in yet, to an empty sign-in created for them. The old vault is never changed or deleted and no value is ever
printed. A migration record (entry names, time, backup path) is written beside the backup.

  python migrate_to_store.py --dry-run     list entry and field names only
  python migrate_to_store.py [--replace]   copy; --replace overwrites entries the store holds
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

from portable_vault import CredentialError  # noqa: E402
from secret_store import oauth_ops, provider_profiles  # noqa: E402
from secret_store.broker_backend import put_grant_fields  # noqa: E402
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


def migrate(request: Callable, open_store: Callable[[], Any], *, dry_run: bool = False, replace: bool = False,
            backup_dir: Any = None, out: Callable[[str], None] = print) -> int:
    status = request("status")
    unlocked = status.get("vault_unlocked", status.get("unlocked")) if isinstance(status, dict) else False
    if not unlocked:
        out("The Vault Agent is not unlocked on the old vault. Unlock it from the tray, then run this again.")
        return 2
    listing = request("vault_list_entries")
    if dry_run:
        out(f"Dry run: {len(listing)} entries would be copied into the store; nothing was changed.")
        for entry in sorted(listing):
            out(f"  {entry}: " + ", ".join(f"{f} ({k})" for f, k in sorted(listing[entry].items())))
        return 0
    store = open_store()
    plans = [_plan(request, entry, fields) for entry, fields in sorted(listing.items())]
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
    record = backup.with_name(backup.stem + ".migration.json")
    record.write_text(json.dumps({"entries": names, "time": datetime.now().astimezone().isoformat(timespec="seconds"),
                                  "backup": str(backup), "replace": replace}, indent=2) + "\n", "utf-8")
    out(f"Copied {len(names)} entries into the store. The old vault is unchanged. "
        f"Verified backup: {backup}. Migration record: {record}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="list entry and field names only")
    parser.add_argument("--replace", action="store_true", help="overwrite entries the store already holds")
    parser.add_argument("--backup-dir", help="folder for the backup (default: migration-backups beside the vault)")
    args = parser.parse_args(argv)
    from secret_store.store import SecretStore
    from vault_broker_client import broker_request
    try:
        return migrate(broker_request, lambda: SecretStore().open(), dry_run=args.dry_run,
                       replace=args.replace, backup_dir=args.backup_dir)
    except (CredentialError, SecretStoreError) as error:
        print(f"Migration stopped: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
