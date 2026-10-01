"""Build or check the core: what every writing session reads first (CONTRACT §1).

The core is two generated files, never edited. /CORE.md holds, verbatim, the contract sections whose
`Applies when` in /RULES.md is `always`; /CORE-RULES.md holds the two index tables that say when to
read the rest, and, verbatim, the rules whose `Applies when` is `always`. Each part stays under
LIMIT characters: a host shortens longer tool output (Claude Code shows about 2 KB of a longer
shell output), so an agent would read only the start of a longer file.

  python shared/skills/repository-preflight/scripts/core.py build   write both parts
  python shared/skills/repository-preflight/scripts/core.py check   exit 1 when a part is stale or too long
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PARTS = ("CORE.md", "CORE-RULES.md")
# Claude Code showed 29,000 characters of a shell output whole and cut 31,000 (TASK-2026-0003, 30 September 2026).
LIMIT = 28_000
RULE_ROW = re.compile(r"^\| `(SMART-RULE-\d{4})` \|(.*)\|$")
SECTION_ROW = re.compile(r"^\| §(\d+(?:\.\d+)?) \|(.*)\|$")
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
    return found


def front(id_: str, title: str, updated: str) -> list[str]:
    return ["---", f"id: {id_}", f"title: {title}", "type: generated_core", "schema_version: 0.2",
            "contract: /CONTRACT.md", "status: active", "created: 2026-09-29T08:00:00+10:00",
            f"updated: {updated}", "owner: brain-owner",
            "generated_by: /shared/skills/repository-preflight/scripts/core.py",
            "canonical_sources:", "  - /CONTRACT.md", "  - /RULES.md", "---", ""]


def render(root: Path) -> dict[str, str]:
    """Both parts of the core, by file name."""
    contract = (root / "CONTRACT.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    rules = (root / "RULES.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    rule_lines, section_lines, rule_rows, section_rows = tables(rules)
    updated = max(UPDATED.search(text).group(1) for text in (contract, rules))
    always = lambda when: when.startswith("always")
    first = front("brain-core", "Brain Core", updated) + [
        "# Brain Core", "",
        "Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is the",
        "first of the two files a writing session reads first (CONTRACT §1): the contract sections that",
        "always apply, verbatim. Then read `/CORE-RULES.md`.", "",
        "## Contract sections that always apply", ""]
    for key, when in section_rows:
        if always(when):
            first += [contract_section(contract, key), ""]
    first += ["Next: read `/CORE-RULES.md`, with the file-reading tool."]
    second = front("brain-core-rules", "Brain Core: Rules", updated) + [
        "# Brain Core: Rules", "",
        "Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is the",
        "second of the two files a writing session reads first (CONTRACT §1), after `/CORE.md`: the tables",
        "that say when to read every other contract section and rule in its canonical home, and the rules",
        "that always apply, verbatim.", "",
        "## When to read the rest", "", *section_lines, "", *rule_lines, "",
        "## Rules that always apply", ""]
    for key, when in rule_rows:
        body = rule_section(rules, key) if always(when) else None
        if body:
            second += [body, ""]
    return {PARTS[0]: "\n".join(first).rstrip() + "\n", PARTS[1]: "\n".join(second).rstrip() + "\n"}


def size_problems(parts: dict[str, str]) -> list[str]:
    return [f"/{name}: {len(text):,} characters, over the {LIMIT:,} a host shows whole; move a section or rule "
            "out of `always`, or split the core further" for name, text in parts.items() if len(text) > LIMIT]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args(argv)
    rules = (args.root / "RULES.md").read_text(encoding="utf-8")
    found = problems(rules)
    parts = render(args.root)
    found += size_problems(parts)
    for name, text in parts.items():
        target = args.root / name
        if args.action == "build":
            target.write_text(text, encoding="utf-8", newline="\n")
            print(f"wrote {target} ({len(text):,} characters)")
        elif not target.is_file() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != text:
            found.append(f"/{name}: out of date; run core.py build")
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
