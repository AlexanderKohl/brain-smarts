"""Checks added by the research-driven changes (eval-b): pointer files, knowledge provenance and review dates."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

POINTER_FILES = ["CLAUDE.md", "AGENTS.md"]
RULE_ID = re.compile(r"\b(SMART|MEMORY)-RULE-\d{4}\b")
POINTER_MAX_LINES = 60


def validate_pointer_files(root: Path, errors: list[str]) -> None:
    """SMART-RULE-0007, one text per rule: a pointer file points and restates nothing."""
    paths = [root / name for name in POINTER_FILES]
    paths += sorted((root / "shared" / "templates" / "host-pointers").glob("*.md"))
    for path in paths:
        if not path.is_file() or path.name == "README.md":
            continue
        text = path.read_text(encoding="utf-8")
        shown = str(path.relative_to(root)).replace("\\", "/")
        if RULE_ID.search(text):
            errors.append(f"/{shown}: a pointer file names a rule; point to the rule file instead (SMART-RULE-0007)")
        if len(text.splitlines()) > POINTER_MAX_LINES:
            errors.append(f"/{shown}: longer than a pointer ({POINTER_MAX_LINES} lines) (SMART-RULE-0007)")


SOURCE_CITE = re.compile(r"(?:/memory/)?(?:raw|sources)/[A-Za-z0-9]")
STATUS = re.compile(r"\bunverified\b|\bverified by\b", re.I)


def added_knowledge_lines(memory: Path) -> list[tuple[str, str]]:
    """Lines being added to KNOWLEDGE.md files: uncommitted changes, as a pre-commit run sees them."""
    import subprocess
    diff = subprocess.run(["git", "diff", "HEAD", "--unified=0", "--", "*KNOWLEDGE.md"], cwd=memory,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    current, found = "", []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            found.append((current, line[1:]))
    return found


def validate_knowledge_provenance(root: Path, errors: list[str]) -> None:
    """CONTRACT 11.6 rule 3: knowledge from outside content names its source and evidence status."""
    memory = root / "memory"
    if not (memory / ".git").exists():
        return
    for path, line in added_knowledge_lines(memory):
        if SOURCE_CITE.search(line) and not STATUS.search(line):
            errors.append(f"/memory/{path}: new knowledge cites a source without an evidence status "
                          f"(unverified, or verified by ...) (CONTRACT 11.6)")


REVIEW_BY = re.compile(r"review by (\d{4}-\d{2}-\d{2})")


def validate_knowledge_review_dates(root: Path, errors: list[str], today: date | None = None) -> None:
    """CONTRACT section 4, KNOWLEDGE.md: a claim past its review date surfaces as an error."""
    today = today or date.today()
    for base in (root, root / "memory"):
        for path in base.rglob("KNOWLEDGE.md"):
            if "raw" in path.parts or ".git" in path.parts:
                continue
            if base == root and "memory" in path.relative_to(root).parts[:1]:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if line.lstrip().startswith("~~"):
                    continue
                for when in REVIEW_BY.findall(line):
                    if date.fromisoformat(when) < today:
                        shown = str(path.relative_to(root)).replace("\\", "/")
                        errors.append(f"/{shown}:{number}: knowledge past its review date {when}; confirm, "
                                      f"re-date or supersede it (RULE-2026-0045)")
