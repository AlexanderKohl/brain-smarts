"""Build or check the core: what every writing session reads first (CONTRACT §1).

The core is two generated files, never edited. /CONTRACT-CORE.md holds, verbatim, the contract sections whose
`Applies when` in /RULES.md is `always`; /RULES-CORE.md holds the two index tables that say when to
read the rest, and, verbatim, the rules whose `Applies when` is `always`. Each part stays under
LIMIT characters: a host shortens longer tool output (Claude Code shows about 2 KB of a longer
shell output), so an agent would read only the start of a longer file.

When /RULES.md has a rule-pack table (`| Pack | Applies when | Rules |`), each row names a third kind
of generated file: a rule pack, /rules/<name>.md, which holds, verbatim, the rules of one situation,
so an agent entering that situation reads one short file instead of finding each rule in /RULES.md.
/RULES-CORE.md then lists the packs, and a rule's own row only when its text is in neither the core
nor a pack. Without that table nothing changes.

  python shared/skills/repository-preflight/scripts/core.py build   write both parts
  python shared/skills/repository-preflight/scripts/core.py check   exit 1 when a part is stale or too long
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PARTS = ("CONTRACT-CORE.md", "RULES-CORE.md")
# The names the two parts had before contract 3.8.0. Each is kept for one contract version as a short pointer to
# its new name, for pointer files written before the rename, and goes with the next contract version.
MOVED = {"CORE.md": PARTS[0], "CORE-RULES.md": PARTS[1]}
# Claude Code showed 29,000 characters of a shell output whole and cut 31,000 (TASK-2026-0003, 30 September 2026).
LIMIT = 28_000
RULE_ROW = re.compile(r"^\| `(SMART-RULE-\d{4})` \|(.*)\|$")
SECTION_ROW = re.compile(r"^\| §(\d+(?:\.\d+)?) \|(.*)\|$")
PACK_ROW = re.compile(r"^\| `/(rules/[a-z0-9-]+\.md)` \|(.*)\|$")
HEADING = re.compile(r"^(#{2,3}) (\d+(?:\.\d+)?)[. ]")
UPDATED = re.compile(r"^updated: (\S+)$", re.MULTILINE)


def cells(rest: str) -> list[str]:
    return [cell.strip() for cell in rest.split(" | ")]


def tables(rules: str) -> tuple[list[str], list[str], list[tuple[str, str]], list[tuple[str, str]]]:
    """The rule and contract-section tables as written, and (key, applies when) for each row."""
    rule_lines, section_lines, rule_rows, section_rows = [], [], [], []
    lines = rules.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("| ID | Rule |"):
            rule_lines = [line, lines[i + 1]]
        elif line.startswith("| Section | Title |"):
            section_lines = [line, lines[i + 1]]
        elif match := RULE_ROW.match(line):
            rule_lines.append(line)
            rule_rows.append((match.group(1), cells(match.group(2))[-1]))
        elif match := SECTION_ROW.match(line):
            section_lines.append(line)
            section_rows.append((match.group(1), cells(match.group(2))[-1]))
    return rule_lines, section_lines, rule_rows, section_rows


def packs(rules: str) -> tuple[list[str], list[tuple[str, str, list[str]]]]:
    """The rule-pack table as written, and (file, applies when, rule ids) for each row."""
    lines, rows = [], []
    source = rules.splitlines()
    for i, line in enumerate(source):
        if line.startswith("| Pack | Applies when |"):
            lines = [line, source[i + 1]]
        elif match := PACK_ROW.match(line):
            lines.append(line)
            when, listed = cells(match.group(2))[:2]
            rows.append((match.group(1), when, re.findall(r"SMART-RULE-\d{4}", listed)))
    return lines, rows


def pack_sections(rules: str) -> dict[str, list[str]]:
    """The contract sections each row of the pack table names (`§9`), by pack file."""
    found: dict[str, list[str]] = {}
    for line in rules.splitlines():
        if match := PACK_ROW.match(line):
            listed = cells(match.group(2))[1:2]
            found[match.group(1)] = re.findall(r"§(\d+(?:\.\d+)?)", listed[0]) if listed else []
    return found


def contract_section(contract: str, number: str) -> str:
    """A section from its heading to the next heading at the same or a higher level."""
    lines = contract.splitlines()
    start = level = None
    for i, line in enumerate(lines):
        match = HEADING.match(line)
        if not match:
            continue
        if start is None and match.group(2) == number:
            start, level = i, len(match.group(1))
        elif start is not None and len(match.group(1)) <= level:
            return "\n".join(lines[start:i]).strip()
    if start is None:
        raise ValueError(f"CONTRACT §{number} not found")
    return "\n".join(lines[start:]).strip()


def rule_section(rules: str, rule_id: str) -> str | None:
    lines = rules.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(f"## {rule_id} "):
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
            return "\n".join(lines[i:end]).strip()
    return None


def problems(rules: str) -> list[str]:
    """Rows without `Applies when`, and rule headings the index does not list."""
    _, _, rule_rows, section_rows = tables(rules)
    found = [f"/RULES.md: {key} has no Applies when" for key, when in rule_rows if not when]
    found += [f"/RULES.md: CONTRACT §{key} has no Applies when" for key, when in section_rows if not when]
    listed = {key for key, _ in rule_rows}
    for heading in re.findall(r"^## (SMART-RULE-\d{4})\b", rules, re.MULTILINE):
        if heading not in listed:
            found.append(f"/RULES.md: {heading} has a heading but no index row")
    when_of = dict(rule_rows)
    section_when, sections_of = dict(section_rows), pack_sections(rules)
    for name, when, ids in packs(rules)[1]:
        if not when:
            found.append(f"/RULES.md: pack /{name} has no Applies when")
        if len(ids) < 2 and not sections_of.get(name):
            found.append(f"/RULES.md: pack /{name} names fewer than two rules; a single rule keeps its own row")
        for number in sections_of.get(name, []):
            if number not in section_when:
                found.append(f"/RULES.md: pack /{name} names CONTRACT §{number}, which the section table does not list")
            elif section_when[number].startswith("always"):
                found.append(f"/RULES.md: pack /{name} names CONTRACT §{number}, which always applies and is in the core")
        for rule_id in ids:
            if rule_id not in when_of:
                found.append(f"/RULES.md: pack /{name} names {rule_id}, which the index does not list")
            elif rule_section(rules, rule_id) is None:
                found.append(f"/RULES.md: pack /{name} names {rule_id}, whose text is not in this file")
            elif when_of[rule_id].startswith("always"):
                found.append(f"/RULES.md: pack /{name} names {rule_id}, which always applies and is in the core")
    return found


def front(id_: str, title: str, updated: str) -> list[str]:
    return ["---", f"id: {id_}", f"title: {title}", "type: generated_core", "schema_version: 0.2",
            "contract: /CONTRACT.md", "status: active", "created: 2026-09-29T08:00:00+10:00",
            f"updated: {updated}", "owner: brain-owner",
            "generated_by: /shared/skills/repository-preflight/scripts/core.py",
            "canonical_sources:", "  - /CONTRACT.md", "  - /RULES.md", "---", ""]


def render(root: Path) -> dict[str, str]:
    """Both parts of the core, and every rule pack, by file name."""
    contract = (root / "CONTRACT.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    rules = (root / "RULES.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    rule_lines, section_lines, rule_rows, section_rows = tables(rules)
    updated = max(UPDATED.search(text).group(1) for text in (contract, rules))
    always = lambda when: when.startswith("always")
    pack_lines, pack_rows = packs(rules)
    header, row_of = rule_lines[:2], {RULE_ROW.match(line).group(1): line for line in rule_lines[2:]}
    if pack_rows:
        # A rule's own row is listed only when its text is in neither the core nor a pack.
        elsewhere = {key for key, when in rule_rows if always(when) and rule_section(rules, key)}
        elsewhere |= {rule_id for _, _, ids in pack_rows for rule_id in ids}
        rule_lines = header + [line for key, line in row_of.items() if key not in elsewhere]
    sections_of = pack_sections(rules)
    held_in: dict[str, list[str]] = {}
    for name, numbers in sections_of.items():
        for number in numbers:
            held_in.setdefault(number, []).append(name)
    if held_in:
        # A section a pack holds is read there: its row names the pack, and the pack's row says when.
        for i, line in enumerate(section_lines):
            match = SECTION_ROW.match(line)
            if match and match.group(1) in held_in:
                title = cells(match.group(2))[0]
                where = ", ".join(f"`/{name}`" for name in sorted(held_in[match.group(1)]))
                section_lines[i] = f"| §{match.group(1)} | {title} | in {where} |"
    first = front("contract-core", "Contract core", updated) + [
        "# Contract core", "",
        "Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is the",
        "first of the two files a writing session reads first (CONTRACT §1): the contract sections that",
        "always apply, verbatim. Then read `/RULES-CORE.md`.", "",
        "## Contract sections that always apply", ""]
    for key, when in section_rows:
        if always(when):
            first += [contract_section(contract, key), ""]
    first += ["Next: read `/RULES-CORE.md`, with the file-reading tool."]
    second = front("rules-core", "Rules core", updated) + [
        "# Rules core", "",
        "Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is the",
        "second of the two files a writing session reads first (CONTRACT §1), after `/CONTRACT-CORE.md`: the tables",
        "that say when to read every other contract section and rule in its canonical home, and the rules",
        "that always apply, verbatim.", "",
        "## When to read the rest", "", *section_lines, ""]
    if pack_rows:
        holds = "the contract sections and the rules" if held_in else "the rules"
        second += [f"A rule pack holds, verbatim, {holds} of one situation. Read the whole pack before acting in",
                   "that situation.", "", *pack_lines, "",
                   "Rules that are in no pack and not below, each read in its canonical home (`/RULES.md` has the",
                   "full index):", ""]
    second += [*rule_lines, "", "## Rules that always apply", ""]
    for key, when in rule_rows:
        body = rule_section(rules, key) if always(when) else None
        if body:
            second += [body, ""]
    parts = {PARTS[0]: "\n".join(first).rstrip() + "\n", PARTS[1]: "\n".join(second).rstrip() + "\n"}
    for old, (new, old_id) in zip(MOVED, zip(MOVED.values(), ("brain-core", "brain-core-rules"))):
        parts[old] = "\n".join(front(old_id, f"Moved to /{new}", updated) + [
            f"# Moved to `/{new}`", "",
            f"Read `/{new}` instead, with the file-reading tool. This file was renamed in contract 3.8.0, so that its",
            "name says which file it is generated from. This pointer is for pointer files written before the rename,",
            "and goes with the next contract version."]) + "\n"
    for name, when, ids in pack_rows:
        stem = Path(name).stem
        numbers = sections_of.get(name, [])
        if numbers:
            opening = ["Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,",
                       "the contract sections and the rules of one situation, so that they are read together. A section's",
                       "canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.", ""]
        else:
            opening = ["Generated from `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim, the rules of one",
                       "situation, so that they are read together. Each rule's canonical home stays `/RULES.md`.", ""]
        text = front(f"brain-rules-{stem}", f"Rule pack: {stem}", updated) + [
            f"# Rule pack: {stem}", "", *opening, f"Read the whole file before: {when}.", ""]
        for number in numbers:
            text += [contract_section(contract, number), ""]
        if ids:
            text += [*header, *[row_of[rule_id] for rule_id in ids if rule_id in row_of], ""]
        for rule_id in ids:
            body = rule_section(rules, rule_id)
            if body:
                text += [body, ""]
        parts[name] = "\n".join(text).rstrip() + "\n"
    return parts


def leftovers(root: Path, parts: dict[str, str]) -> list[str]:
    """Pack files no row of the pack table generates any more."""
    folder = root / "rules"
    if not folder.is_dir():
        return []
    return [f"/rules/{path.name}: no row of the pack table in /RULES.md generates it; delete it"
            for path in sorted(folder.glob("*.md")) if f"rules/{path.name}" not in parts]


def size_problems(parts: dict[str, str]) -> list[str]:
    return [f"/{name}: {len(text):,} characters, over the {LIMIT:,} a host shows whole; move a section or rule "
            "out of `always`, split the core further, or split the pack" for name, text in parts.items() if len(text) > LIMIT]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args(argv)
    rules = (args.root / "RULES.md").read_text(encoding="utf-8")
    found = problems(rules)
    parts = render(args.root)
    found += size_problems(parts) + leftovers(args.root, parts)
    for name, text in parts.items():
        target = args.root / name
        if args.action == "build":
            target.parent.mkdir(exist_ok=True)
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {target} ({len(text):,} characters)")
        elif not target.is_file() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            found.append(f"/{name}: out of date; run core.py build")
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
