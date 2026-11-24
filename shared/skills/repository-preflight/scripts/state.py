#!/usr/bin/env python3
"""Keep a node's STATE.md to its position: move what is superseded out of it.

A state file says what is true now (CONTRACT §4). Under its `## Handover` section each checkpoint of
a thread is one entry; this script moves the entries a later checkpoint has superseded, unchanged,
into `STATE-HISTORY.md` beside the state file, which no bootstrap names and an agent reads only when
it needs what happened earlier. Nothing is rewritten and nothing is deleted.

    state.py list <STATE.md>                         the entries under ## Handover, numbered, with sizes
    state.py history <STATE.md> --keep 1,4           move every entry but these to STATE-HISTORY.md
    state.py history <STATE.md> --move 5-41          move these entries
    state.py history <STATE.md> --move-matching TEXT move the entries whose first line contains TEXT
    state.py detail <STATE.md> --entry 1 --name N    move one entry's body to HANDOVER-<N>.md, keep its
                                                     first line and a pointer in the state file
    state.py check [--root <brain root>] [paths]     name every STATE.md longer than the limit; exit 1

An entry is a `### ` heading and what follows it; in a section without such headings it is a
paragraph that opens in bold (`**Checkpoint of ...`) after a blank line, and what follows it.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

LIMIT = 28_000  # characters: what a host shows whole, the limit of the core files (core.py)
SECTION = "## Handover"
HISTORY = "STATE-HISTORY.md"
POINTER = (f"Earlier entries: `{HISTORY}` beside this file, moved there unchanged; read it only when what happened "
           "earlier is needed.")


def now() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def read(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    return raw.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in raw


def write(path: Path, text: str, crlf: bool) -> None:
    path.write_bytes((text.replace("\n", "\r\n") if crlf else text).encode("utf-8"))


def stamp(text: str, when: str) -> str:
    return re.sub(r"^updated: .*$", f"updated: {when}", text, count=1, flags=re.M)


def front(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, flags=re.S)
    out: dict[str, str] = {}
    for line in (m.group(1).splitlines() if m else []):
        if re.match(r"^[A-Za-z_]+: ", line):
            key, value = line.split(": ", 1)
            out[key] = value
    return out


class Handover:
    """The `## Handover` section of a state file, cut into what precedes it, its opening text, its
    entries and what follows it. `text()` puts the parts back exactly as they were read."""

    def __init__(self, text: str) -> None:
        m = re.search(rf"^{re.escape(SECTION)}[ \t]*\n", text, flags=re.M)
        if not m:
            raise ValueError(f"no `{SECTION}` section")
        nxt = re.search(r"^## ", text[m.end():], flags=re.M)
        end = m.end() + nxt.start() if nxt else len(text)
        self.before, self.heading, self.after = text[:m.start()], m.group(0), text[end:]
        body = text[m.end():end]
        starts = [h.start() for h in re.finditer(r"^### ", body, flags=re.M)]
        if not starts:
            # a bold opening on the section's first line, or after a blank line
            starts = [h.start() for h in re.finditer(r"^\*\*", body, flags=re.M)
                      if not body[:h.start()].strip() or re.search(r"\n[ \t]*\n\Z", body[:h.start()])]
        self.opening = body[:starts[0]] if starts else body
        self.entries = [body[a:b] for a, b in zip(starts, starts[1:] + [len(body)])]

    def text(self) -> str:
        return self.before + self.heading + self.opening + "".join(self.entries) + self.after


def first_line(entry: str) -> str:
    return entry.strip().splitlines()[0] if entry.strip() else ""


def numbers(spec: str, count: int) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        a, _, b = part.partition("-")
        lo, hi = int(a), int(b or a)
        if lo < 1 or hi > count or lo > hi:
            raise ValueError(f"entry {part} is outside 1-{count}")
        out.update(range(lo, hi + 1))
    return out


def history_header(state_text: str, when: str) -> str:
    meta = front(state_text)
    lines = ["---", f"id: {meta.get('id', 'state')}-history", f"title: {meta.get('title', 'State')} – history",
             "type: state_history", f"schema_version: {meta.get('schema_version', '0.2')}", "contract: /CONTRACT.md",
             f"created: {when}", f"updated: {when}"]
    if "owner" in meta:
        lines.append(f"owner: {meta['owner']}")
    lines += ["---", "", f"# {meta.get('title', 'State')} – history", "", "Read `/CONTRACT.md` first.", "",
              "Entries a later checkpoint superseded, moved here unchanged from `STATE.md` beside this file. No "
              "bootstrap names this file: read it only when what happened earlier is needed. The newest move is "
              "last.", ""]
    return "\n".join(lines)


def cmd_list(args: argparse.Namespace) -> int:
    text, _ = read(args.state)
    section = Handover(text)
    print(f"{args.state}: {len(text):,} characters; `{SECTION}` holds {len(section.entries)} entries")
    for i, entry in enumerate(section.entries, 1):
        print(f"{i:>3}  {len(entry):>7,}  {first_line(entry)[:110]}")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    text, crlf = read(args.state)
    section = Handover(text)
    count = len(section.entries)
    if args.keep is not None:
        move = set(range(1, count + 1)) - numbers(args.keep, count)
    elif args.move is not None:
        move = numbers(args.move, count)
    else:
        move = {i for i, e in enumerate(section.entries, 1) if args.move_matching in first_line(e)}
    if not move:
        print("nothing to move")
        return 0
    when = args.now or now()
    moved = [section.entries[i - 1] for i in sorted(move)]
    section.entries = [e for i, e in enumerate(section.entries, 1) if i not in move]
    if POINTER not in section.text():
        if section.entries:
            section.entries[-1] = section.entries[-1].rstrip("\n") + "\n\n" + POINTER + "\n\n"
        else:
            section.opening = section.opening.rstrip("\n") + "\n\n" + POINTER + "\n\n"
    history = args.state.with_name(HISTORY)
    if history.exists():
        old, history_crlf = read(history)
        old = stamp(old, when).rstrip("\n") + "\n"
    else:
        old, history_crlf = history_header(text, when), crlf
    block = f"\n## Moved from the state file at {when}\n\n" + "".join(moved).rstrip("\n") + "\n"
    write(history, old + block, history_crlf)
    write(args.state, stamp(section.text(), when), crlf)
    size = len(section.text())
    print(f"moved {len(moved)} entries ({sum(len(m) for m in moved):,} characters) to {history}")
    print(f"{args.state}: {len(text):,} -> {size:,} characters" + ("" if size <= LIMIT else f"; still over {LIMIT:,}"))
    return 0


def cmd_detail(args: argparse.Namespace) -> int:
    text, crlf = read(args.state)
    section = Handover(text)
    index = next(iter(numbers(str(args.entry), len(section.entries)))) - 1
    entry = section.entries[index]
    head, _, body = entry.partition("\n")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", args.name):
        raise ValueError("--name takes lower-case letters, digits and hyphens")
    target = args.state.with_name(f"HANDOVER-{args.name}.md")
    if target.exists():
        raise ValueError(f"{target} exists; give the thread's own name, or move the old file to the history first")
    if not body.strip():
        print("the entry has no body to move")
        return 0
    when = args.now or now()
    meta = front(text)
    lines = ["---", f"id: {meta.get('id', 'state')}-handover-{args.name}",
             f"title: {meta.get('title', 'State')} – handover of {args.name}", "type: handover",
             f"schema_version: {meta.get('schema_version', '0.2')}", "contract: /CONTRACT.md",
             f"created: {when}", f"updated: {when}"]
    if "owner" in meta:
        lines.append(f"owner: {meta['owner']}")
    lines += ["---", "", f"# Handover of {args.name}", "", "Read `/CONTRACT.md` first.", "",
              "The detail behind this thread's entry under `## Handover` in `STATE.md` beside this file. The thread "
              "that continues this work reads it; no other thread needs to.", "", head.lstrip("# ").strip(), ""]
    write(target, "\n".join(lines) + body.strip("\n") + "\n", crlf)
    section.entries[index] = (head + "\n\n" + f"- Detail: `{target.name}` beside this file, read by the thread that "
                              "continues this work.\n\n")
    write(args.state, stamp(section.text(), when), crlf)
    print(f"moved {len(body):,} characters to {target}; {args.state} is now {len(section.text()):,} characters")
    return 0


def state_files(root: Path) -> list[Path]:
    """Every node's STATE.md under a brain root: the mechanics' system nodes and the memory. A task
    store's STATE.md is generated from its records and is not a node's state."""
    found: list[Path] = []
    for base in (root / "systems", root / "memory"):
        if not base.is_dir():
            continue
        for path in base.rglob("STATE.md"):
            parts = path.relative_to(root).parts
            if "tasks" in parts or "raw" in parts or "templates" in parts or any(p.startswith(".") for p in parts):
                continue
            found.append(path)
    return sorted(found)


def oversized(paths: list[Path], limit: int = LIMIT) -> list[tuple[Path, int]]:
    out = []
    for path in paths:
        try:
            size = len(read(path)[0])
        except (OSError, UnicodeDecodeError):
            continue
        if size > limit:
            out.append((path, size))
    return sorted(out, key=lambda item: (-item[1], str(item[0])))


def cmd_check(args: argparse.Namespace) -> int:
    paths = [Path(p) for p in args.paths] or state_files(args.root)
    over = oversized(paths, args.limit)
    for path, size in over:  # largest first: the one that costs a reader most
        print(f"{size:>9,}  {path}")
    print(f"{len(over)} of {len(paths)} state files are over {args.limit:,} characters")
    return 1 if over else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list")
    p.add_argument("state", type=Path)
    p.set_defaults(run=cmd_list)
    p = sub.add_parser("history")
    p.add_argument("state", type=Path)
    which = p.add_mutually_exclusive_group(required=True)
    which.add_argument("--keep")
    which.add_argument("--move")
    which.add_argument("--move-matching")
    p.add_argument("--now", help="timestamp to record; the clock when absent")
    p.set_defaults(run=cmd_history)
    p = sub.add_parser("detail")
    p.add_argument("state", type=Path)
    p.add_argument("--entry", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--now")
    p.set_defaults(run=cmd_detail)
    p = sub.add_parser("check")
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    p.add_argument("--limit", type=int, default=LIMIT)
    p.add_argument("paths", nargs="*")
    p.set_defaults(run=cmd_check)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError) as exc:
        print(f"state.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
