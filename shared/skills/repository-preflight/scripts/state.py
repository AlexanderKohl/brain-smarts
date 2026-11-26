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
    state.py history <STATE.md> --section HEADING    move a whole section that is history, anywhere in the
                                                     file (repeat the option for several)
    state.py detail <STATE.md> --entry 1 --name N    move one entry's body to HANDOVER-<N>.md, keep its
                                                     first line and a pointer in the state file
    state.py subjects <file.md> --plan <plan.json>   move whole sections into subject files under
                                                     knowledge/ and list them in KNOWLEDGE.md (CONTRACT §4)
    state.py check [--root <brain root>] [paths]     name every STATE.md longer than the limit; exit 1
    state.py check --knowledge [paths]               the same for KNOWLEDGE.md files
    state.py since <file> [--from WHEN] [--repo DIR] what Git recorded since the file last changed

An entry is a `### ` heading and what follows it; in a section without such headings it is a
paragraph that opens in bold (`**Checkpoint of ...`) after a blank line, and what follows it; in a
section with neither, a top-level bullet that opens in bold (`- **24 November: ...`).

A section is a `## ` or `### ` heading and everything down to the next heading of its level or
above. It is named by its heading's text, or by the start of it when no other heading starts so.

`subjects` reads a plan: `{"subjects": [{"name": "pricing", "title": "Pricing", "holds": "how a
quote is priced", "sections": ["Price lists", "Margins"]}]}`. Each subject's sections move,
unchanged, to `knowledge/<name>.md` beside the file, and `KNOWLEDGE.md` beside it gains the line that
says what the subject file holds. The file may be the `KNOWLEDGE.md` itself, or a `STATE.md` whose
sections are durable facts; a state file keeps a line naming where they went.
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
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
        if not starts:
            # a list of checkpoints: top-level bullets that open in bold
            starts = [h.start() for h in re.finditer(r"^- \*\*", body, flags=re.M)]
        self.opening = body[:starts[0]] if starts else body
        self.entries = [body[a:b] for a, b in zip(starts, starts[1:] + [len(body)])]

    def text(self) -> str:
        return self.before + self.heading + self.opening + "".join(self.entries) + self.after


def sections(text: str) -> list[tuple[int, str, int, int]]:
    """Every `## ` and `### ` section outside a code fence: (level, heading text, start, end)."""
    heads: list[tuple[int, str, int]] = []
    fenced, offset = False, 0
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced:
            m = re.match(r"(#{2,3}) (.*)", line)
            if m:
                heads.append((len(m.group(1)), m.group(2).strip(), offset))
        offset += len(line)
    out = []
    for i, (level, title, start) in enumerate(heads):
        end = next((st for lv, _, st in heads[i + 1:] if lv <= level), len(text))
        out.append((level, title, start, end))
    return out


def find_sections(text: str, names: list[str]) -> list[tuple[int, str, int, int]]:
    """The sections these names mean, in the order given. A name is a heading's whole text, or the
    start of exactly one heading. No section may lie inside another one named."""
    known = sections(text)
    chosen = []
    for name in names:
        hits = [x for x in known if x[1] == name] or [x for x in known if x[1].startswith(name)]
        if len(hits) != 1:
            raise ValueError(f"{len(hits)} sections are headed {name!r}; name exactly one")
        chosen.append(hits[0])
    ordered = sorted(chosen, key=lambda x: x[2])
    for a, b in zip(ordered, ordered[1:]):
        if b[2] < a[3]:
            raise ValueError(f"{b[1]!r} lies inside {a[1]!r}, or is named twice; name one of them once")
    return chosen


def cut(text: str, spans: list[tuple[int, int, str]]) -> str:
    """The text without these (start, end) spans; each span's third item is put in its place."""
    for start, end, instead in sorted(spans, reverse=True):
        text = text[:start] + instead + text[end:]
    return text


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


def cmd_history_sections(args: argparse.Namespace) -> int:
    text, crlf = read(args.state)
    found = find_sections(text, args.section)
    if any(title == SECTION[3:] and level == 2 for level, title, _, _ in found):
        raise ValueError(f"`{SECTION}` itself stays; move its entries with --keep or --move")
    when = args.now or now()
    moved = [text[start:end] for _, _, start, end in sorted(found, key=lambda x: x[2])]
    rest = cut(text, [(start, end, "") for _, _, start, end in found])
    assert len(rest) + sum(len(m) for m in moved) == len(text)
    if POINTER not in rest:
        rest = rest.rstrip("\n") + "\n\n" + POINTER + "\n"
    history = args.state.with_name(HISTORY)
    if history.exists():
        old, history_crlf = read(history)
        old = stamp(old, when).rstrip("\n") + "\n"
    else:
        old, history_crlf = history_header(text, when), crlf
    block = f"\n## Moved from the state file at {when}\n\n" + "".join(moved).rstrip("\n") + "\n"
    write(history, old + block, history_crlf)
    write(args.state, stamp(rest, when), crlf)
    print(f"moved {len(moved)} sections ({sum(len(m) for m in moved):,} characters) to {history}")
    print(f"{args.state}: {len(text):,} -> {len(rest):,} characters" + ("" if len(rest) <= LIMIT else f"; still over {LIMIT:,}"))
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    if args.section:
        return cmd_history_sections(args)
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


SUBJECTS = "## Subjects"
SUBJECTS_INTRO = ("This node keeps its knowledge by subject (CONTRACT §4). Read a subject file when its subject is the "
                  "work's. A new fact goes into its subject file; one that fits no subject goes into this file, "
                  "below the list. A reference elsewhere that names a section of this file by its heading means "
                  "that heading in a subject file.")


def subject_header(index_text: str, name: str, title: str, holds: str, when: str) -> str:
    meta = front(index_text)
    lines = ["---", f"id: {meta.get('id', 'knowledge')}-{name}", f"title: {meta.get('title', 'Knowledge')} – {title}",
             "type: knowledge", f"schema_version: {meta.get('schema_version', '0.2')}", "contract: /CONTRACT.md"]
    if "status" in meta:
        lines.append(f"status: {meta['status']}")
    lines += [f"created: {when}", f"updated: {when}"]
    if "owner" in meta:
        lines.append(f"owner: {meta['owner']}")
    lines += ["---", "", f"# {title}", "", "Read `/CONTRACT.md` first.", "",
              f"One subject of this node's knowledge (CONTRACT §4): {holds}. `KNOWLEDGE.md` one folder up lists the "
              "subject files.", "", ""]
    return "\n".join(lines)


def with_index(index_text: str, lines: dict[str, str]) -> str:
    """The index file with these subject lines in its `## Subjects` list, in alphabetical order."""
    row = re.compile(r"^- `knowledge/([a-z0-9-]+)\.md` – (.*)$", flags=re.M)
    known = sections(index_text)
    old = next((x for x in known if x[0] == 2 and x[1] == SUBJECTS[3:]), None)
    merged = dict(row.findall(index_text[old[2]:old[3]])) if old else {}
    merged.update(lines)
    block = (SUBJECTS + "\n\n" + SUBJECTS_INTRO + "\n\n"
             + "".join(f"- `knowledge/{name}.md` – {holds}\n" for name, holds in sorted(merged.items())) + "\n")
    if old:
        return index_text[:old[2]] + block + index_text[old[3]:]
    first = next((x[2] for x in known if x[0] == 2), None)
    if first is None:
        return index_text.rstrip("\n") + "\n\n" + block
    return index_text[:first] + block + index_text[first:]


def cmd_subjects(args: argparse.Namespace) -> int:
    text, crlf = read(args.file)
    index = args.file.with_name("KNOWLEDGE.md")
    if not index.exists():
        raise ValueError(f"{index} does not exist; a node's subject files are listed in its KNOWLEDGE.md")
    is_index = args.file.resolve() == index.resolve()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))["subjects"]
    for subject in plan:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", subject["name"]):
            raise ValueError(f"{subject['name']!r}: a subject's name takes lower-case letters, digits and hyphens")
        if not subject["sections"]:
            raise ValueError(f"{subject['name']}: no sections named")
    names = [name for subject in plan for name in subject["sections"]]
    found = find_sections(text, names)
    if any(title == SUBJECTS[3:] and level == 2 for level, title, _, _ in found):
        raise ValueError(f"`{SUBJECTS}` is the list of subject files and stays")
    when = args.now or now()
    index_text, index_crlf = (text, crlf) if is_index else read(index)
    folder = args.file.with_name("knowledge")
    made_folder = not folder.exists()
    spans, lines, position, report = [], {}, 0, []
    for subject in plan:
        mine = found[position:position + len(subject["sections"])]
        position += len(mine)
        body = "".join(text[start:end].rstrip("\n") + "\n\n" for _, _, start, end in mine).rstrip("\n") + "\n"
        target = folder / f"{subject['name']}.md"
        if target.exists():
            old, target_crlf = read(target)
            new = stamp(old, when).rstrip("\n") + "\n\n" + body
        else:
            target_crlf = crlf
            new = subject_header(index_text, subject["name"], subject["title"], subject["holds"], when) + body
        note = "" if is_index else (f"Kept as knowledge since {when[:10]}, moved unchanged: `knowledge/{subject['name']}.md` "
                                    f"beside this file – {subject['holds']}.\n\n")
        first = min(start for _, _, start, _ in mine)
        spans += [(start, end, note if start == first else "") for _, _, start, end in mine]
        lines[subject["name"]] = subject["holds"]
        report.append((target, new, target_crlf, sum(end - start for _, _, start, end in mine)))
    rest = cut(text, spans)
    if args.dry_run:
        for target, new, _, moved in report:
            print(f"would write {target.name}: {len(new):,} characters ({moved:,} moved)")
        after = len(with_index(rest, lines)) if is_index else len(rest)
        print(f"{args.file}: {len(text):,} -> {after:,} characters" + ("" if after <= LIMIT else f"; still over {LIMIT:,}"))
        return 0
    folder.mkdir(exist_ok=True)
    for target, new, target_crlf, moved in report:
        write(target, new, target_crlf)
        print(f"{target}: {len(new):,} characters ({moved:,} moved)" + ("" if len(new) <= LIMIT else f"; longer than {LIMIT:,}"))
    if is_index:
        rest = with_index(rest, lines)
    else:
        write(index, stamp(with_index(index_text, lines), when), index_crlf)
    write(args.file, stamp(rest, when), crlf)
    print(f"{args.file}: {len(text):,} -> {len(rest):,} characters" + ("" if len(rest) <= LIMIT else f"; still over {LIMIT:,}"))
    if made_folder:
        print(f"new folder {folder}: name it in the node's README.md (CONTRACT §4)")
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


def knowledge_files(root: Path) -> list[Path]:
    """Every node's KNOWLEDGE.md under a brain root: the index of its knowledge, read whole."""
    found: list[Path] = []
    for base in (root / "systems", root / "memory"):
        if base.is_dir():
            found += [path for path in base.rglob("KNOWLEDGE.md")
                      if not {"raw", "templates"} & set(path.relative_to(root).parts)
                      and not any(p.startswith(".") for p in path.relative_to(root).parts)]
    if (root / "KNOWLEDGE.md").is_file():
        found.append(root / "KNOWLEDGE.md")
    return sorted(found)


def shown(root: Path, path: Path) -> str:
    return "/" + path.relative_to(root).as_posix()


def validate_state_sizes(root: Path, errors: list[str]) -> None:
    """SMART-RULE-0019: a node's STATE.md in the mechanics or the memory is short enough to be read whole."""
    for path, size in oversized(state_files(root)):
        errors.append(f"{shown(root, path)}: {size:,} characters, over the {LIMIT:,} a host shows whole; move superseded "
                      "handover entries to the history file beside it with scripts/state.py history, or a long entry's "
                      "detail to a handover file with scripts/state.py detail (SMART-RULE-0019)")


def validate_knowledge_sizes(root: Path, errors: list[str]) -> None:
    """CONTRACT section 4: a KNOWLEDGE.md in the mechanics or the memory is short enough to be read whole."""
    for path, size in oversized(knowledge_files(root)):
        errors.append(f"{shown(root, path)}: {size:,} characters, over the {LIMIT:,} a host shows whole; keep the "
                      "knowledge by subject under knowledge/ and make this file its index (CONTRACT section 4)")


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
    paths = [Path(p) for p in args.paths] or (knowledge_files(args.root) if args.knowledge else state_files(args.root))
    over = oversized(paths, args.limit)
    for path, size in over:  # largest first: the one that costs a reader most
        print(f"{size:>9,}  {path}")
    kind = "knowledge" if args.knowledge else "state"
    print(f"{len(over)} of {len(paths)} {kind} files are over {args.limit:,} characters")
    return 1 if over else 0


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if done.returncode != 0:
        raise ValueError(done.stderr.strip() or "git " + " ".join(args) + " failed")
    return done.stdout


def cmd_since(args: argparse.Namespace) -> int:
    """What happened since the last checkpoint is in Git, so no checkpoint has to tell it again: the
    commits made since the file last changed (or since --from, a date or a commit), newest first."""
    home = args.file.resolve().parent
    last = git(home, "log", "-1", "--format=%H %cI", "--", args.file.resolve().name).split()
    if not args.since and not last:
        raise ValueError(f"{args.file} has no commit yet; give --from")
    repo = Path(git(args.repo or home, "rev-parse", "--show-toplevel").strip())
    start = args.since or last[1]
    if args.since:
        is_commit = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", start + "^{commit}"],
                                   capture_output=True).returncode == 0
        span = [start + "..HEAD"] if is_commit else ["--since=" + start]
    else:  # after the file's own last commit, exactly, when it is in the repository being read
        span = ["--since=" + start] if args.repo else [last[0] + "..HEAD"]
    rows = [row.split("\x1f") for row in git(repo, "log", *span, "--no-merges",
                                             "--format=%h%x1f%cs%x1f%s%x1f%(trailers:key=Release-note,valueonly,separator=%x2C)"
                                             ).splitlines() if row]
    print(f"{len(rows)} commits in {repo.name} since {start}" + ("" if len(rows) <= args.limit else f"; the newest {args.limit}:"))
    for short, day, subject, note in rows[:args.limit]:
        print(f"{short}  {day}  {subject}" + (f"  [note: {note.strip()}]" if note.strip() else ""))
    return 0


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
    which.add_argument("--section", action="append", help="a whole section's heading; repeat for several")
    p.add_argument("--now", help="timestamp to record; the clock when absent")
    p.set_defaults(run=cmd_history)
    p = sub.add_parser("subjects")
    p.add_argument("file", type=Path, help="a KNOWLEDGE.md, or a STATE.md whose sections are durable facts")
    p.add_argument("--plan", type=Path, required=True, help="JSON: which sections go to which subject file")
    p.add_argument("--now")
    p.add_argument("--dry-run", action="store_true", help="print the sizes that would result and change nothing")
    p.set_defaults(run=cmd_subjects)
    p = sub.add_parser("detail")
    p.add_argument("state", type=Path)
    p.add_argument("--entry", type=int, required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--now")
    p.set_defaults(run=cmd_detail)
    p = sub.add_parser("check")
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    p.add_argument("--limit", type=int, default=LIMIT)
    p.add_argument("--knowledge", action="store_true", help="check KNOWLEDGE.md files instead of STATE.md files")
    p.add_argument("paths", nargs="*")
    p.set_defaults(run=cmd_check)
    p = sub.add_parser("since")
    p.add_argument("file", type=Path, help="a tracked file, usually a STATE.md")
    p.add_argument("--from", dest="since", help="a date, a timestamp or a commit; the file's last commit when absent")
    p.add_argument("--repo", type=Path, help="another repository to read, for a node whose work is committed elsewhere")
    p.add_argument("--limit", type=int, default=100)
    p.set_defaults(run=cmd_since)
    args = parser.parse_args(argv)
    try:
        return args.run(args)
    except (ValueError, OSError, KeyError) as exc:
        print(f"state.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
