"""Personal-data check for shareable repositories (SMART-RULE-0008, CONTRACT §3.4).

The one implementation: the repository preflight validator runs it on every shareable
repository before each commit, and `skill_exchange.py scrub` calls it for any path. It finds the
owner's own terms (read from memory at run time, never written anywhere else) and patterns that
look like personal data. A clean repository reports nothing, so every hit is worth reading.

Generic exemptions live in `../config/exemptions.txt`, one per line with its reason:

    path: <glob relative to the repository root>   # reason
    value: <exact text>                             # reason

Owner-specific values never go there; they are fixed at their source instead.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from pathlib import Path

# Patterns, alphabetical by name. Values are regular expressions, matched case-insensitively.
PATTERNS = {
    # A Windows user or dev folder, or a Unix home ("/Users/" is case-sensitive, so an API
    # route such as "/users/search" is not a home folder).
    "absolute-path": r"(?<![\w/])(?:[A-Za-z]:\\\\?(?:Users|dev)\\\\?[^\s`'\"]+|(?-i:/(?:home|Users)/)[^\s/`'\"]+)",
    # The domain must end in letters, so "python@3.12" is not an address.
    "email": r"[\w.+-]+@(?!example\.(?:com|org|net)\b)[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b",
    "phone": r"(?<![\w.:-])\+?\d(?:[ ]?\d){8,13}(?![\w:-]|\.\d)",
    "uuid": r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
}
# Owner-profile fields whose values identify the owner.
PROFILE_FIELDS = ("brain_root", "github_account", "owner_name", "owner_short_name", "project_repos_root")
# Profile fields that hold a personal name, matched case-sensitively, and the prefix that marks them.
NAME_FIELDS = ("owner_name", "owner_short_name")
NAME = "Name:"
TEXT_SUFFIXES = {".cfg", ".css", ".html", ".ini", ".js", ".json", ".md", ".mjs", ".ps1", ".py",
                 ".sh", ".toml", ".ts", ".txt", ".yaml", ".yml"}
MIN_TERM = 4
# Telephone numbers reserved for fiction contain this run of digits (555-01xx).
FICTION_PHONE = "55501"
# An unbroken run of this many digits without a leading "+" is a count or a millisecond
# timestamp, not a telephone number (a national number has at most eleven).
NOT_A_PHONE_DIGITS = 12
EXEMPTIONS = Path(__file__).resolve().parents[1] / "config" / "exemptions.txt"
SKELETON = ("shared", "templates", "memory-skeleton")


def front_matter(path: Path) -> dict:
    """Scalars and simple `- item` lists from YAML front matter."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    out: dict = {}
    key = None
    for line in text[3:end].splitlines():
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and key:
            if not isinstance(out.get(key), list):
                out[key] = []
            out[key].append(item.group(1).strip().strip('"'))
            continue
        found = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if found:
            key = found.group(1)
            out[key] = found.group(2).strip().strip('"')
    return out


def owner_terms(root: Path) -> list[str]:
    """Terms that identify this owner: profile values, memory's own node names and an optional
    denylist. Node names the memory skeleton ships are generic, not the owner's. A personal name
    and its parts come back as `Name:<text>` and match only as written, so a name that is also a
    common word ("Owner", "Rose") does not match the lower-case word."""
    memory = root / "memory"
    if not (memory / "OWNER.md").is_file():
        return []
    terms: set[str] = set()
    profile = front_matter(memory / "OWNER.md")
    for field in PROFILE_FIELDS:
        value = profile.get(field)
        if not isinstance(value, str) or not value:
            continue
        if field in NAME_FIELDS:
            terms.update(NAME + part for part in {value, *value.split()} if len(part) >= MIN_TERM)
        else:
            terms.add(value)
    skeleton = root.joinpath(*SKELETON)
    for folder in ("projects", "systems"):
        generic = {p.name for p in (skeleton / folder).iterdir() if p.is_dir()} \
            if (skeleton / folder).is_dir() else set()
        base = memory / folder
        if base.is_dir():
            terms.update(p.name for p in base.iterdir() if p.is_dir() and p.name not in generic)
    extra = memory / "skills" / "repository-preflight" / "config" / "denylist.txt"
    if extra.is_file():
        terms.update(t.strip() for t in extra.read_text(encoding="utf-8").splitlines()
                     if t.strip() and not t.startswith("#"))
    return sorted((t for t in terms if len(t) >= MIN_TERM), key=lambda t: (-len(t), t))


def load_exemptions(path: Path = EXEMPTIONS) -> tuple[list[str], set[str], list[str]]:
    """(path globs, exact values, problems). A line without a reason is a problem."""
    globs: list[str] = []
    values: set[str] = set()
    problems: list[str] = []
    if not path.is_file():
        return globs, values, problems
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        body, _, reason = line.partition(" # ")
        kind, _, value = body.partition(":")
        value = value.strip()
        if not reason.strip() or kind.strip() not in ("path", "value") or not value:
            problems.append(f"{path.name}:{number}: expected 'path: <glob>  # reason' or 'value: <text>  # reason'")
            continue
        (globs.append(value) if kind.strip() == "path" else values.add(value))
    return globs, values, problems


def repository_files(repo: Path) -> list[Path]:
    """Files Git tracks or would track in `repo` (ignored files are not shared)."""
    try:
        listed = subprocess.run(
            ["git", "-c", f"safe.directory={repo.as_posix()}", "-C", str(repo),
             "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return sorted(p for p in repo.rglob("*") if p.is_file() and ".git" not in p.parts)
    return sorted(repo / name for name in listed.split("\0") if name and (repo / name).is_file())


def not_a_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    unbroken = not value.startswith("+") and " " not in value
    return FICTION_PHONE in digits or (unbroken and len(digits) >= NOT_A_PHONE_DIGITS)


def scan(files: list[Path], terms: list[str], *, base: Path | None = None,
         globs: list[str] = (), allowed: set[str] = frozenset()) -> list[tuple[str, int, str, str]]:
    """Every hit as (file, line, kind, text). `globs` are relative to `base`."""
    def alternatives(group: list[str]) -> str:
        return "|".join(r"(?<![\w@.])" + re.escape(t) + r"(?![\w])" for t in group)

    names = [t[len(NAME):] for t in terms if t.startswith(NAME)]
    others = [t for t in terms if not t.startswith(NAME)]
    parts = ([f"(?-i:{alternatives(names)})"] if names else []) + ([alternatives(others)] if others else [])
    word = re.compile("|".join(parts), re.I) if parts else None
    patterns = {k: re.compile(v, re.I) for k, v in PATTERNS.items()}
    hits: list[tuple[str, int, str, str]] = []
    for f in files:
        if f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if base is not None:
            relative = f.relative_to(base).as_posix()
            if any(fnmatch.fnmatch(relative, g) for g in globs):
                continue
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            found = [("owner-term", m.group(0)) for m in word.finditer(line)] if word else []
            found += [(k, m.group(0)) for k, r in patterns.items() for m in r.finditer(line)]
            for kind, value in found:
                if value in allowed:
                    continue
                if kind == "phone" and not_a_phone(value):
                    continue
                hits.append((str(f), number, kind, value))
    return hits


def check_repository(root: Path, repo: Path) -> tuple[list[tuple[str, int, str, str]], list[str]]:
    """Hits and exemption-file problems for one shareable repository beneath the brain root."""
    globs, values, problems = load_exemptions()
    nested = [repo / name for name in ("memory", "library")] if repo == root else []
    files = [f for f in repository_files(repo) if not any(n in f.parents for n in nested)]
    return scan(files, owner_terms(root), base=repo, globs=globs, allowed=values), problems
