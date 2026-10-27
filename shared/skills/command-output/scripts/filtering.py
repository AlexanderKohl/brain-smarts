"""The filter: shortens the long output of a recognised command before an agent reads it.

It keeps the head and the tail, every error line with a little context, and the exit code; it
saves the full output to a file and names that file on the last line, so an agent that needs more
reads the file instead of running the command again. Output that is short, or comes from a command
it does not recognise, is left exactly as it was. The rules are data, in filters.json beside this
file. hook.py (a host's after-command hook) and run.py (the wrapper) are its only callers.

Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RULES_FILE = HERE / "filters.json"
OUTPUT_DIR = Path("temp") / "command-output"
KEEP_DAYS = 7
# Set to "off" to turn the filter off for one session or one computer without touching any host file.
SWITCH = "COMMAND_OUTPUT"
# Names another folder for the saved outputs, the statistics and the error log.
FOLDER = "COMMAND_OUTPUT_DIR"
# Replace the output only when it saves at least this share of its characters.
MIN_SAVING = 0.2

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)")
SEGMENTS = re.compile(r"&&|\|\||;|\|")
# What may stand before the program in one segment: variable assignments, sudo, time, PowerShell's &.
LEAD = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+|sudo\s+|time\s+|&\s+)*")
PROGRAM_PATH = re.compile(r"""^["']?[^\s"']*[\\/](?=[^\\/\s"']+)""")
EXE = re.compile(r"^(\S+?)\.(exe|cmd|bat)\b", re.IGNORECASE)


def enabled() -> bool:
    return os.environ.get(SWITCH, "").strip().lower() not in ("off", "0", "false", "no")


def brain_root(start: Path = HERE) -> Path | None:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file() and (folder / "shared").is_dir():
            return folder
    return None


def _patterns(values: list[str]) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(value, re.IGNORECASE) for value in values)


@dataclass(frozen=True)
class Family:
    name: str
    commands: tuple[re.Pattern, ...]
    drop: tuple[re.Pattern, ...]
    keep: tuple[re.Pattern, ...]
    drop_only_when_over: bool
    errors: bool
    keep_head: int
    keep_tail: int
    max_lines: int


@dataclass(frozen=True)
class Rules:
    families: tuple[Family, ...]
    generic: Family
    pass_lines: int
    pass_chars: int
    priority: re.Pattern
    notable: re.Pattern
    before: int
    after: int
    max_priority_lines: int
    leave_alone: re.Pattern


def _family(data: dict) -> Family:
    return Family(
        name=data["name"],
        commands=_patterns(data.get("commands", [])),
        drop=_patterns(data.get("drop", [])),
        keep=_patterns(data.get("keep", [])),
        drop_only_when_over=bool(data.get("drop_only_when_over", False)),
        errors=bool(data.get("errors", True)),
        keep_head=int(data["keep_head"]),
        keep_tail=int(data["keep_tail"]),
        max_lines=int(data["max_lines"]),
    )


def load_rules(path: Path = RULES_FILE) -> Rules:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Rules(
        families=tuple(_family(item) for item in data["families"]),
        generic=_family(data["generic"]),
        pass_lines=int(data["pass_through_below"]["lines"]),
        pass_chars=int(data["pass_through_below"]["chars"]),
        priority=re.compile(data["priority"], re.IGNORECASE),
        notable=re.compile(data["notable"], re.IGNORECASE),
        before=int(data["priority_context"]["before"]),
        after=int(data["priority_context"]["after"]),
        max_priority_lines=int(data["max_priority_lines"]),
        leave_alone=re.compile(data["leave_alone"], re.IGNORECASE),
    )


def program_text(segment: str) -> str:
    """One command segment with what stands before the program removed, and the program's folder
    and .exe/.cmd ending dropped, so `.venv\\Scripts\\python.exe -m pytest` reads `python -m pytest`."""
    text = LEAD.sub("", segment).strip()
    text = PROGRAM_PATH.sub("", text)
    return EXE.sub(r"\1", text).strip("\"' ")


def family_for(command: str, rules: Rules, explicit: bool = False) -> Family | None:
    """The family of the first segment that starts with a recognised program. None when the command
    already narrows its own output (a pipe into head, grep and the like) or is the wrapper itself;
    the generic family when the wrapper was asked for explicitly and nothing else matches."""
    if rules.leave_alone.search(command):
        return None
    for segment in SEGMENTS.split(command):
        text = program_text(segment)
        for family in rules.families:
            if any(pattern.match(text) for pattern in family.commands):
                return family
    return rules.generic if explicit else None


def is_short(text: str, rules: Rules) -> bool:
    return text.count("\n") < rules.pass_lines and len(text) < rules.pass_chars


def clean_lines(text: str) -> list[str]:
    """Lines without colour codes, and with a progress bar's carriage-return redraws reduced to the
    last state shown. Windows line endings are made plain first, or every line would read empty."""
    text = ANSI.sub("", text).replace("\r\n", "\n")
    return [line.rstrip("\r").rsplit("\r", 1)[-1].rstrip() for line in text.split("\n")]


def collapse(lines: list[str]) -> list[str]:
    """A run of three or more identical lines becomes the line once and one marker line; a run of
    blank lines becomes one blank line."""
    out: list[str] = []
    i = 0
    while i < len(lines):
        j = i
        while j + 1 < len(lines) and lines[j + 1] == lines[i]:
            j += 1
        run = j - i + 1
        if lines[i] == "":
            out.append("")
        elif run >= 3:
            out += [lines[i], f"[... the line above repeats {run - 1} more times]"]
        else:
            out += lines[i:j + 1]
        i = j + 1
    return out


def _wanted(line: str, family: Family, rules: Rules) -> bool:
    """An error line, unless error words are content in this family, or a line the family keeps."""
    if family.errors and rules.priority.search(line):
        return True
    return any(pattern.search(line) for pattern in family.keep)


def cap(lines: list[str], family: Family, rules: Rules, failed: bool) -> list[str]:
    """The head and the tail, and from the middle every wanted line (an error, or a line the family
    keeps) with its context, then notable lines (warnings) while the budget lasts. Omitted stretches
    are marked with how many lines they held."""
    total = len(lines)
    head = min(family.keep_head, total)
    tail = family.keep_tail + (family.keep_tail // 2 if failed else 0)
    tail_start = max(head, total - tail)
    keep = set(range(head)) | set(range(tail_start, total))
    budget = rules.max_priority_lines
    skipped = 0
    for i in range(head, tail_start):
        if not _wanted(lines[i], family, rules):
            continue
        window = [j for j in range(i - rules.before, i + rules.after + 1)
                  if head <= j < tail_start and j not in keep]
        if len(window) > budget:
            skipped += 1
            continue
        keep.update(window)
        budget -= len(window)
    for i in range(head, tail_start):
        if budget <= 0 or not family.errors:
            break
        if i not in keep and rules.notable.search(lines[i]):
            keep.add(i)
            budget -= 1
    out: list[str] = []
    last = -1
    for i in sorted(keep):
        if i != last + 1:
            out.append(f"[... {i - last - 1} lines omitted ...]")
        out.append(lines[i])
        last = i
    if skipped:
        kind = "error lines" if family.errors else "kept lines"
        out.append(f"[... {skipped} more {kind} not shown; they are in the full output]")
    return out


def shorten(text: str, family: Family, rules: Rules, failed: bool) -> tuple[list[str], int]:
    """The shortened lines and the number of lines there were."""
    lines = clean_lines(text)
    total = len(lines)
    if family.drop and (total > family.max_lines or not family.drop_only_when_over):
        lines = [line for line in lines
                 if _wanted(line, family, rules) or not any(pattern.search(line) for pattern in family.drop)]
    lines = collapse(lines)
    if len(lines) > family.max_lines:
        lines = cap(lines, family, rules, failed)
    return lines, total


def _prune(folder: Path) -> None:
    cutoff = time.time() - KEEP_DAYS * 86400
    for path in folder.glob("*.log"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            pass


def output_folder(root: Path | None = None) -> Path:
    """COMMAND_OUTPUT_DIR when it is set; otherwise <brain root>/temp/command-output, or the system's
    temporary folder when the skill runs outside a brain."""
    if root is None and os.environ.get(FOLDER):
        return Path(os.environ[FOLDER])
    root = brain_root() if root is None else root
    return (root / OUTPUT_DIR) if root else Path(tempfile.gettempdir()) / "command-output"


def save_full(text: str, command: str, exit_code: int | None, cwd: str | None,
              root: Path | None = None) -> Path:
    folder = output_folder(root)
    folder.mkdir(parents=True, exist_ok=True)
    _prune(folder)
    path = folder / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}.log"
    saved = datetime.now().astimezone().isoformat(timespec="seconds")
    header = (f"command: {command}\ncwd: {cwd or 'unknown'}\n"
              f"exit code: {'not reported' if exit_code is None else exit_code}\nsaved: {saved}\n\n")
    path.write_text(header + text, encoding="utf-8")
    return path


def record(entry: dict, root: Path | None = None) -> None:
    """One line per replaced output in stats.jsonl beside the saved files, for the trial's
    measurements. It holds sizes and the family only, never the command or the output."""
    try:
        folder = output_folder(root)
        folder.mkdir(parents=True, exist_ok=True)
        entry = {"at": datetime.now().astimezone().isoformat(timespec="seconds"), **entry}
        with (folder / "stats.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        pass


def footer(shown: int, total: int, family: str, exit_code: int | None, path: Path) -> str:
    """The last line of a shortened output. The exit code is named when the caller knows it and left
    out when it does not, so the line never contradicts the code a host reports beside it."""
    code = "" if exit_code is None else f", exit code {exit_code}"
    return f"[command-output: showing {shown} of {total} lines ({family} filter{code}). Full output: {path}]"


def shrink(command: str, text: str, exit_code: int | None, *, explicit: bool = False,
           cwd: str | None = None, root: Path | None = None, rules: Rules | None = None,
           host: str = "unknown") -> str | None:
    """The replacement for `text`, or None to leave it exactly as it is."""
    if not text or not enabled():
        return None
    rules = load_rules() if rules is None else rules
    if is_short(text, rules):
        return None
    family = family_for(command, rules, explicit)
    if family is None:
        return None
    lines, total = shorten(text, family, rules, failed=exit_code not in (0, None))
    body = "\n".join(lines)
    shown = sum(1 for line in lines if line.strip() and not line.startswith("[... "))
    if shown == 0 or len(body) > (1 - MIN_SAVING) * len(text):
        return None
    try:
        path = save_full(text, command, exit_code, cwd, root)
    except OSError:
        return None  # nothing is dropped that cannot be read back
    record({"host": host, "family": family.name, "lines_before": total, "lines_after": shown,
            "chars_before": len(text), "chars_after": len(body), "exit_code": exit_code}, root)
    return body + "\n" + footer(shown, total, family.name, exit_code, path)
