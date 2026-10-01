#!/usr/bin/env python3
"""Context guard for delegation.py (trial of an amendment to SMART-RULE-0019).

A conductor must not open a run or a packet when its context is too full to carry the work
to a committed, validated state, or after its context was compacted and the handover
checkpoint has not been confirmed. delegation.py imports this module; it has no other caller.

Two inputs, one of which every guarded command must receive:
  --context-tokens N        the conductor's current context size in tokens, read from the host
  --context-unknown REASON  the host cannot report it; the reason is recorded

Compaction markers: a host hook drops <brain_root>/temp/conductor/compacted/<session_id>.json
(keys session_id, at, cwd) when a conductor's context is compacted. The brain root means both
the root discovered upward from the current directory and the `brain_root` value in the front
matter of /memory/OWNER.md when that file exists and the value differs. A marker younger than
MARKER_MAX_AGE blocks new-run and new-packet until `checkpoint-done --session ID` removes it,
unless --session ID names this thread and no marker is named ID.json.

Standard library only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Thresholds in tokens of the conductor's context (SMART-RULE-0019, context handoff checkpoint).
# At or above DRAIN_TOKENS no new run is opened: let the workers in flight finish, take the
# checkpoint, hand over. At or above STOP_TOKENS not even a packet is opened.
DRAIN_TOKENS = 750000
STOP_TOKENS = 850000
# A compaction marker older than this is stale and ignored; the hook that writes it and the
# checkpoint that clears it both happen within a working day.
MARKER_MAX_AGE = timedelta(hours=24)
COMPACTED_SUBDIR = Path("temp") / "conductor" / "compacted"
OWNER_PROFILE = Path("memory") / "OWNER.md"
CLEAR_COMMAND = "python shared/skills/delegate-work/scripts/delegation.py checkpoint-done --session {session}"
BRAIN_ROOT_RE = re.compile(r"^brain_root:\s*(.+?)\s*$", re.MULTILINE)


@dataclass
class Marker:
    path: Path
    session_id: str
    at: str
    when: datetime


# ---------------------------------------------------------------- arguments


def add_context_arguments(parser, guarded: bool = True) -> None:
    """Add the context flags to a subcommand parser; `guarded` adds the override and session flags."""
    parser.add_argument("--context-tokens", type=int, metavar="N",
                        help="the conductor's current context size in tokens, read from the host")
    parser.add_argument("--context-unknown", metavar="REASON",
                        help="the host cannot report the context size; say why")
    if guarded:
        parser.add_argument("--owner-override", metavar="REASON",
                            help="proceed past the context guard; the reason is recorded")
        parser.add_argument("--session", metavar="ID",
                            help="this conductor's session id; another session's compaction marker then does not block")


def context_value(args, command: str) -> int | str:
    """Exactly one of --context-tokens and --context-unknown: an int, or 'unknown: REASON'."""
    tokens = getattr(args, "context_tokens", None)
    unknown = getattr(args, "context_unknown", None)
    if tokens is None and not unknown:
        raise SystemExit(f"error: {command} needs --context-tokens N (the conductor's context size in "
                         "tokens, read from the host) or --context-unknown REASON (the host cannot report it)")
    if tokens is not None and unknown:
        raise SystemExit(f"error: {command} takes exactly one of --context-tokens and --context-unknown")
    if tokens is not None:
        if tokens < 0:
            raise SystemExit("error: --context-tokens must be zero or more")
        return tokens
    return f"unknown: {unknown}"


# ---------------------------------------------------------------- markers


def parse_when(text: str) -> datetime | None:
    """An ISO 8601 stamp as an aware datetime; a naive one is taken as local time."""
    if not text:
        return None
    try:
        when = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()


def marker_roots(root: Path) -> list[Path]:
    """The discovered root, plus the owner profile's brain_root when it names a different place."""
    roots = [root.resolve()]
    profile = root / OWNER_PROFILE
    if profile.exists():
        text = profile.read_text(encoding="utf-8", errors="replace")
        end = text.find("\n---", 4) if text.startswith("---") else -1
        match = BRAIN_ROOT_RE.search(text[:end] if end > 0 else "")
        if match:
            value = match.group(1).strip().strip("'\"")
            other = Path(value)
            if value and other.resolve() != roots[0]:
                roots.append(other)
    return roots


def load_marker(path: Path) -> Marker:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    at = str(data.get("at") or "")
    when = parse_when(at)
    if when is None:                      # an unreadable marker is dated by its file
        when = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        at = at or when.isoformat(timespec="seconds")
    return Marker(path, str(data.get("session_id") or path.stem), at, when)


def markers(root: Path) -> list[Marker]:
    """Every compaction marker in either place, by path."""
    found: list[Marker] = []
    for base in marker_roots(root):
        folder = base / COMPACTED_SUBDIR
        if folder.is_dir():
            found.extend(load_marker(path) for path in sorted(folder.glob("*.json")))
    return found


def blocking_markers(root: Path, now: datetime, session: str | None) -> list[Marker]:
    """Markers younger than MARKER_MAX_AGE; with a session id, only the marker named after it."""
    fresh = [m for m in markers(root) if now - m.when < MARKER_MAX_AGE]
    if session:
        return [m for m in fresh if m.path.stem == session]
    return fresh


# ---------------------------------------------------------------- the guard


def guard(root: Path, args, command: str, now: datetime) -> tuple[int | str, str | None]:
    """Refuse `command` under SMART-RULE-0019, or return (context value, owner override).

    new-run is refused at or above DRAIN_TOKENS, new-packet at or above STOP_TOKENS, and both
    while a fresh compaction marker blocks. --owner-override REASON passes every check and is
    returned so the caller records it.
    """
    value = context_value(args, command)
    override = getattr(args, "owner_override", None)
    if override:
        return value, override
    if isinstance(value, int):
        if command == "new-run" and value >= DRAIN_TOKENS:
            raise SystemExit(
                f"error: context is {value} tokens, at or above the drain threshold of {DRAIN_TOKENS} "
                "(SMART-RULE-0019): drain – no new run, let the workers in flight finish, take the "
                "checkpoint, hand over. --owner-override REASON proceeds anyway and records the reason.")
        if command == "new-packet" and value >= STOP_TOKENS:
            raise SystemExit(
                f"error: context is {value} tokens, at or above the stop threshold of {STOP_TOKENS} "
                "(SMART-RULE-0019): stop – no new packet, take the checkpoint, hand over. "
                "--owner-override REASON proceeds anyway and records the reason.")
    blocking = blocking_markers(root, now, getattr(args, "session", None))
    if blocking:
        lines = [f"error: {command} refused: a conductor's context was compacted and the handover "
                 "checkpoint is not confirmed (SMART-RULE-0019)."]
        for m in blocking:
            lines.append(f"  session {m.session_id} compacted at {m.at} ({m.path})")
            lines.append(f"    clears it: {CLEAR_COMMAND.format(session=m.path.stem)}")
        lines.append("Another thread's compaction does not block this one: give --session ID for this "
                     "thread. --owner-override REASON proceeds anyway and records the reason.")
        raise SystemExit("\n".join(lines))
    return value, None


def checkpoint_done(root: Path, session: str) -> int:
    """Delete <session>.json from both places and print what was removed."""
    removed = []
    for base in marker_roots(root):
        path = base / COMPACTED_SUBDIR / f"{session}.json"
        if path.exists():
            path.unlink()
            removed.append(path)
    for path in removed:
        print(f"removed {path}")
    if not removed:
        places = ", ".join(str(base / COMPACTED_SUBDIR) for base in marker_roots(root))
        print(f"no compaction marker named {session}.json under {places}")
    return 0
