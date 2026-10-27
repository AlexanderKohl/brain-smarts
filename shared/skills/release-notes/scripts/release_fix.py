"""A note that does not parse: where it fails, and the one repair that cures the common case.

Notes written by hand carry two shapes YAML refuses: a plain scalar with a colon and a space
in it (`look_out_for: Check: the total`) and a value that opens with a quoted phrase and goes
on (`title: "Your decision" is a page`). Both are cured by turning the value into a `>-`
block, which keeps the wording and the line endings exactly as they were.

`parse_error(text)` says where a front matter fails; `repair(text)` returns the repaired text
or the original when nothing it knows applies; `fix_file(path)` repairs a note in place and
reports whether it now parses. Nothing here reads configuration or names a project.
"""
from __future__ import annotations

from pathlib import Path

import yaml

FRONT_FIRST_LINE = 2   # the line of the file on which the front matter starts, after `---`


def split(text: str) -> tuple[str, str, str] | None:
    """(front, rest, newline) for a file that opens with a front matter; None when it does not."""
    nl = "\r\n" if "\r\n" in text else "\n"
    plain = text.replace("\r\n", "\n")
    if not plain.startswith("---\n"):
        return None
    end = plain.find("\n---", 3)
    if end < 0:
        return None
    return plain[4:end], plain[end:], nl


def parse_error(front: str) -> str | None:
    """`line N: problem` (N counted in the file) when the front matter does not parse."""
    try:
        yaml.safe_load(front)
    except yaml.YAMLError as err:
        mark = getattr(err, "problem_mark", None) or getattr(err, "context_mark", None)
        line = (mark.line + FRONT_FIRST_LINE) if mark is not None else "?"
        problem = getattr(err, "problem", None) or str(err).splitlines()[0]
        return "line %s: %s" % (line, problem)
    return None


def _scalar_line(line: str) -> tuple[str, str] | None:
    """(key, value) when a line is `key: plain value` that could need a block."""
    if not line or line[0] in " \t#-":
        return None
    key, sep, value = line.partition(":")
    if not sep or not key.strip() or " " in key.strip():
        return None
    value = value.strip()
    if not value or value[0] in "[{>|" or value.startswith("&") or value.startswith("*"):
        return None
    return key.strip(), value


def _parses(lines: list[str]) -> bool:
    """Only a value YAML refuses outright is touched; a date or a number is left as it is."""
    try:
        yaml.safe_load("\n".join(lines))
    except yaml.YAMLError:
        return False
    return True


def repair(front: str) -> str:
    """Each `key: value` that YAML refuses as a plain or quoted scalar becomes a `>-` block.

    A value may continue on indented lines; those are kept as the block's lines. The words
    are never changed: a quote that opened the value stays in it.
    """
    lines = front.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        found = _scalar_line(lines[i])
        if not found:
            out.append(lines[i])
            i += 1
            continue
        key, value = found
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and lines[j].startswith((" ", "\t")) and lines[j].strip():
            block.append(lines[j])
            j += 1
        if _parses(block):
            out.extend(block)
        else:
            out.append(key + ": >-")
            out.append("  " + value)
            out.extend("  " + b.strip() for b in block[1:])
        i = j
    return "\n".join(out)


def fix_file(path: Path) -> tuple[bool, str | None]:
    """Repair a note in place. (changed, remaining error): error is None once it parses."""
    text = path.read_bytes().decode("utf-8")   # bytes, so a CRLF file stays CRLF
    parts = split(text)
    if parts is None:
        return False, "no front matter"
    front, rest, nl = parts
    before = parse_error(front)
    if before is None:
        return False, None
    fixed = repair(front)
    after = parse_error(fixed)
    if fixed == front or after is not None:
        return False, after if after is not None else before
    new_text = ("---\n" + fixed + rest).replace("\n", nl)
    path.write_text(new_text, encoding="utf-8", newline="")
    return True, None


def broken_in(folder: Path, inside=None) -> list[dict]:
    """Every note in a folder that does not parse: slug, path and `line N: problem`. `inside(name)`
    returns the checked path of a note or raises; a note it refuses is listed, never read."""
    out = []
    for f in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if f.name.lower() == "readme.md":
            continue
        if inside is not None:
            try:
                f = inside(f.name)
            except Exception as err:   # a link that leaves the repository
                out.append({"slug": f.stem, "path": f, "error": str(err), "refused": True})
                continue
        parts = split(f.read_bytes().decode("utf-8"))
        error = parse_error(parts[0]) if parts else "no front matter"
        if error:
            out.append({"slug": f.stem, "path": f, "error": error})
    return out


def skipped_lines(projects, path_of) -> list[str]:
    """One line per unreleased note that does not parse, for the top of an output or a page.
    `path_of(project, *parts)` is the checked path under the project's `unreleased/`."""
    return ["skipped %s/%s: %s (%s) – run release_notes.py fix" % (p["id"], b["slug"], b["error"], b["path"])
            for p in projects for b in broken_in(path_of(p), lambda name, p=p: path_of(p, name))]


def fix_notes(projects, path_of) -> tuple[list[str], list[str]]:
    """Repair every unreleased note that does not parse: (fixed, still broken), one line each."""
    fixed, left = [], []
    for p in projects:
        for b in broken_in(path_of(p), lambda name, p=p: path_of(p, name)):
            changed, error = (False, b["error"]) if b.get("refused") else fix_file(b["path"])
            if error is None:
                fixed.append("fixed %s/%s (%s)" % (p["id"], b["slug"], b["path"]))
            else:
                left.append("could not repair %s/%s: %s (%s)" % (p["id"], b["slug"], error, b["path"]))
    return fixed, left
