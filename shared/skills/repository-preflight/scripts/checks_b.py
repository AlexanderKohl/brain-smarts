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


def subject_files(index: Path) -> list[Path]:
    """The subject files of a node whose knowledge is kept by subject: the Markdown in `knowledge/` beside
    its KNOWLEDGE.md (CONTRACT section 4)."""
    folder = index.parent / "knowledge"
    return sorted(folder.glob("*.md")) if folder.is_dir() else []


def added_knowledge_lines(memory: Path, subjects: bool = False) -> list[tuple[str, str]]:
    """Lines being added to KNOWLEDGE.md files: uncommitted changes, as a pre-commit run sees them. With
    `subjects`, also lines added to a subject file beside one."""
    import subprocess
    specs = ["*KNOWLEDGE.md"] + (["*knowledge/*.md"] if subjects else [])
    diff = subprocess.run(["git", "diff", "HEAD", "--unified=0", "--", *specs], cwd=memory,
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    current, found = "", []
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            found.append((current, line[1:]))
    if subjects:  # only a knowledge/ folder that sits beside a KNOWLEDGE.md holds subject files
        found = [(path, line) for path, line in found
                 if path.endswith("KNOWLEDGE.md") or (memory / path).parent.parent.joinpath("KNOWLEDGE.md").is_file()]
    return found


def validate_knowledge_provenance(root: Path, errors: list[str], subjects: bool = False) -> None:
    """CONTRACT 11.6 rule 3: knowledge from outside content names its source and evidence status."""
    memory = root / "memory"
    if not (memory / ".git").exists():
        return
    for path, line in added_knowledge_lines(memory, subjects):
        if SOURCE_CITE.search(line) and not STATUS.search(line):
            errors.append(f"/memory/{path}: new knowledge cites a source without an evidence status "
                          f"(unverified, or verified by ...) (CONTRACT 11.6)")


REVIEW_BY = re.compile(r"review by (\d{4}-\d{2}-\d{2})")


def validate_knowledge_review_dates(root: Path, errors: list[str], today: date | None = None,
                                    subjects: bool = False) -> None:
    """CONTRACT section 4, KNOWLEDGE.md: a claim past its review date surfaces as an error."""
    today = today or date.today()
    for base in (root, root / "memory"):
        indexes = sorted(base.rglob("KNOWLEDGE.md"))
        for path in [each for index in indexes for each in [index] + (subject_files(index) if subjects else [])]:
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


LEARNING_VIEWS_SCRIPT = ("shared", "skills", "learning-maintenance", "scripts", "learning_views.py")
LEARNING_VIEWS_COMMAND = "python shared/skills/learning-maintenance/scripts/learning_views.py build"


def load_learning_views(root: Path):
    """Import the learning-maintenance generator from the brain root; never copy its logic (SMART-RULE-0018)."""
    import importlib.util
    path = root.joinpath(*LEARNING_VIEWS_SCRIPT)
    spec = importlib.util.spec_from_file_location("learning_views_for_preflight", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_learning_views(root: Path, errors: list[str], loader=None) -> None:
    """SMART-RULE-0028: the learning index and board equal a fresh build, apart from the derivation stamp."""
    if not (root / "memory").is_dir():
        return
    # A memory with no learning view has nothing to check, and need not carry the generator.
    if not any((root / "memory" / "projects").glob("*/data/learning/*.md")):
        return
    try:
        views_module = (loader or load_learning_views)(root)
        folder = root / views_module.LEARNING_DIR
        if not folder.is_dir():
            return
        views, problems = views_module.build_views(root)
        for name, body in views.items():
            path = folder / name
            shown = "/" + path.relative_to(root).as_posix()
            try:
                committed = views_module.read_file(path)
            except (OSError, UnicodeDecodeError) as exc:
                errors.append(f"{shown}: the learning view cannot be read ({exc}); rebuild it with {LEARNING_VIEWS_COMMAND} (SMART-RULE-0028)")
                continue
            fresh = views_module.render(name, body, views_module.existing_created(path, "-"), "-")
            diff = views_module.first_difference(committed, fresh)
            if diff:
                errors.append(f"{shown}: the learning view differs from a fresh build at line {diff[0]}; "
                              f"rebuild it with {LEARNING_VIEWS_COMMAND} (SMART-RULE-0028)")
        for problem in problems:
            errors.append(f"/memory learning records: {problem}; the views cannot be built cleanly (SMART-RULE-0028)")
    except Exception as exc:  # a generator that cannot be imported or raises is one error, never a traceback
        errors.append(f"the learning views could not be checked: {type(exc).__name__}: {exc}; "
                      f"run {LEARNING_VIEWS_COMMAND} to see why (SMART-RULE-0028)")
