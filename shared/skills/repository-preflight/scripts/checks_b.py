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
