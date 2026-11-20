"""Write the host pointer and settings files of SETUP.md steps E and F.

  python shared/skills/repository-preflight/scripts/host_wiring.py plan  --host claude-code --host codex
  python shared/skills/repository-preflight/scripts/host_wiring.py apply --host codex --level edits

`plan` prints one line per file (create | replace | merge | unchanged, the path, the backup it would make) and
any kept-value conflicts, and writes nothing. `apply` backs up a differing file once per date
(<file>.bak-YYYYMMDD), writes, re-reads to verify, and prints the same lines with `done`.
Levels: routine (user and local settings), edits (user-level settings only), defaults (no settings;
Codex still gets its trust entry). Exit 0 on success, 2 on refusal or error.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tomllib
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import host_wiring_files as files  # noqa: E402
import setup_guard  # noqa: E402


def find_root(start: Path) -> Path | None:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file():
            return folder
    return None


def backup_path(item: files.Item, stamp: str) -> Path | None:
    """The backup this item needs: the file exists, will change, and none exists for the date."""
    if item.action in ("create", "unchanged") or not item.path.exists():
        return None
    target = item.path.with_name(f"{item.path.name}.bak-{stamp}")
    return None if target.exists() else target


def verify(item: files.Item) -> None:
    text = item.path.read_bytes().decode("utf-8")
    if item.kind == "json":
        json.loads(text)
    elif item.kind == "toml":
        tomllib.loads(text)
    if text.replace("\r\n", "\n") != item.content.replace("\r\n", "\n"):
        raise ValueError(f"{item.path}: written text does not match")


def run(command: str, items: list[files.Item]) -> None:
    stamp = date.today().strftime("%Y%m%d")
    for item in items:
        backup = backup_path(item, stamp)
        if command == "apply" and item.action != "unchanged":
            if backup:
                shutil.copy2(item.path, backup)
            item.path.parent.mkdir(parents=True, exist_ok=True)
            with open(item.path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(item.content)
            verify(item)
        note = f"backup {backup}" if backup else "no backup"
        print(f"{'done ' if command == 'apply' else ''}{item.action:<9} {item.path}  ({note})")
        for conflict in item.conflicts:
            print(f"  conflict, kept yours: {conflict}")


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=("plan", "apply"))
    parser.add_argument("--host", action="append", choices=files.HOSTS, required=True)
    parser.add_argument("--level", choices=files.LEVELS, default="routine")
    parser.add_argument("--home", default=str(Path.home()))
    parser.add_argument("--root", default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 0 if exc.code == 0 else 2
    message = setup_guard.refusal(Path(__file__).resolve(), f"python {Path(__file__).name} {' '.join(argv)}")
    if message:
        print(message, file=sys.stderr)
        return 2
    root = Path(args.root).absolute() if args.root else find_root(Path(__file__).resolve().parent)
    if root is None or not (root / "CONTRACT.md").is_file():
        print("host_wiring: no brain root (CONTRACT.md) found", file=sys.stderr)
        return 2
    try:
        run(args.command, files.build(root, Path(args.home), args.host, args.level))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"host_wiring: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
