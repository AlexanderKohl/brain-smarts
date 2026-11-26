#!/usr/bin/env python3
"""The threads a host keeps on this computer, and which of them the user has archived.

A thread leaves things behind: a session copy, a compaction marker, working copies of a project. The
user says a thread is no longer needed by archiving it in the host, so what an archived thread left
is cleared at once and no age limit has to guess (cleanup.py). This module is the one place that
reads a host's own record of its threads. A host it cannot read yields None, never a guess, and the
caller then clears nothing on that ground.

    threads.py list            every thread this computer's hosts know: archived or not, last active
    threads.py current         the identifier of the thread this command runs in, when the host gives one

Hosts read: Claude Code desktop on Windows (its `claude-code-sessions` records under the local
application data folder). Another host is added here, with a test, when its record is known.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ENVIRONMENT_IDS = ("CLAUDE_CODE_SESSION_ID",)      # set by the host for every command a thread runs
RECORDS = "sessions"                               # under /temp: which thread started which session copy


@dataclass(frozen=True)
class Thread:
    id: str
    title: str
    archived: bool
    last_active: float        # seconds since the epoch; 0 when the host does not say


def current() -> str | None:
    """The thread this process runs in, as its host names it; None when no host says."""
    for name in ENVIRONMENT_IDS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def host_stores() -> list[Path]:
    """Folders that hold a host's thread records on this computer."""
    local = os.environ.get("LOCALAPPDATA", "").strip()
    return [Path(local) / "Claude-Data"] if local else []


def known(stores: list[Path] | None = None) -> dict[str, Thread] | None:
    """Every thread the hosts know, by each identifier it has had; None when no record can be read."""
    found: dict[str, Thread] = {}
    read_any = False
    for store in host_stores() if stores is None else stores:
        for record in store.glob("*/claude-code-sessions/*/*/local_*.json"):
            try:
                data = json.loads(record.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            read_any = True
            thread = Thread(id=str(data.get("cliSessionId") or ""), title=str(data.get("title") or ""),
                            archived=bool(data.get("isArchived")),
                            last_active=float(data.get("lastActivityAt") or 0) / 1000)
            for key in ("cliSessionId", "lastAssistantCliSessionId"):
                if data.get(key):
                    found[str(data[key])] = thread
    return found if read_any else None


def record_path(root: Path, copy_name: str) -> Path:
    return root / "temp" / RECORDS / f"{copy_name}.json"


def record_copy(root: Path, copy_name: str, now: str) -> bool:
    """Note which thread started a session copy, so the copy can go when that thread is archived."""
    thread = current()
    if not thread:
        return False
    path = record_path(root, copy_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"copy": copy_name, "thread": thread, "started": now}, indent=1), encoding="utf-8")
    return True


def copy_thread(root: Path, copy_name: str) -> str | None:
    try:
        return str(json.loads(record_path(root, copy_name).read_text(encoding="utf-8")).get("thread") or "") or None
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["list", "current"])
    args = parser.parse_args(argv)
    if args.command == "current":
        print(current() or "no host names the thread this command runs in")
        return 0
    threads = known()
    if threads is None:
        print("no host's thread records can be read on this computer")
        return 0
    rows = sorted({t for t in threads.values()}, key=lambda t: -t.last_active)
    for t in rows:
        when = datetime.datetime.fromtimestamp(t.last_active).strftime("%Y-%m-%d") if t.last_active else "?"
        print(f"{'archived' if t.archived else 'live':<8}  {when}  {t.id[:8]}  {t.title[:80]}")
    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
