"""Build or check /CORE.md: what every writing session reads first (CONTRACT §1).

/CORE.md is generated, never edited. It holds, verbatim, the contract sections and the rules whose
`Applies when` in /RULES.md is `always`, and the two index tables that say when to read the rest.

  python shared/skills/repository-preflight/scripts/core.py build   write /CORE.md
  python shared/skills/repository-preflight/scripts/core.py check   exit 1 when /CORE.md is stale
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

CORE = "CORE.md"
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


def render(root: Path) -> str:
    contract = (root / "CONTRACT.md").read_text(encoding="utf-8")
    rules = (root / "RULES.md").read_text(encoding="utf-8")
    rule_lines, section_lines, rule_rows, section_rows = tables(rules)
    updated = max(UPDATED.search(text).group(1) for text in (contract, rules))
    always = lambda when: when.startswith("always")
    parts = ["---", "id: brain-core", "title: Brain Core", "type: generated_core", "schema_version: 0.2",
             "contract: /CONTRACT.md", "status: active", "created: 2026-09-29T08:00:00+10:00",
             f"updated: {updated}", "owner: brain-owner", "generated_by: /shared/skills/repository-preflight/scripts/core.py",
             "canonical_sources:", "  - /CONTRACT.md", "  - /RULES.md", "---", "",
             "# Brain Core", "",
             "Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It is what",
             "a writing session reads first (CONTRACT §1): the contract sections and rules that always apply,",
             "verbatim, and the tables that say when to read the rest in its canonical home.", "",
             "## When to read the rest", "", *section_lines, "", *rule_lines, "",
             "## Contract sections that always apply", ""]
    for key, when in section_rows:
        if always(when):
            parts += [contract_section(contract, key), ""]
    parts += ["## Rules that always apply", ""]
    for key, when in rule_rows:
        body = rule_section(rules, key) if always(when) else None
        if body:
            parts += [body, ""]
    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=("build", "check"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args(argv)
    rules = (args.root / "RULES.md").read_text(encoding="utf-8")
    found = problems(rules)
    target = args.root / CORE
    if args.action == "build":
        target.write_text(render(args.root), encoding="utf-8", newline="\n")
        print(f"wrote {target}")
    elif not target.is_file() or target.read_text(encoding="utf-8").replace("\r\n", "\n") != render(args.root):
        found.append(f"/{CORE}: out of date; run core.py build")
    for problem in found:
        print(problem)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
