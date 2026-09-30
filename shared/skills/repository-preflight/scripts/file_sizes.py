"""SMART-RULE-0041 in the validator: code files stay small.

A code file has at most 800 lines. A repository adopts the limit by recording every code file already
over it, with its size (`code-map record --adopt` writes `<record dir>/sizes.json`); a recorded file
may not grow, and a new file over the limit is split, never recorded. A repository with no record has
not adopted the limit and is not checked.

Files are counted the way the code map counts them (/shared/skills/code-map/scripts/lib/config.js and
files.js): git's own list of the repository's files, tracked and untracked but not ignored; less the
code map's ignored and size-exempt patterns and the repository's own additions in
`code-map.config.json`; code files by extension; lines as the code map counts them. A test compares
these lists with the code map's, so the two cannot drift apart.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

CONFIG_FILE = "code-map.config.json"
RECORD_DIR = "code-map"
FILE_LINES = 800
IGNORE = ["**/node_modules/**", "**/dist/**", "**/build/**", "**/.next/**", "**/out/**", "**/coverage/**",
          "**/vendor/**", "**/*.min.js", "**/*.map", "**/.git/**", "**/__pycache__/**"]
SIZE_EXEMPT = ["**/migrations/**", "**/seeders/**", "**/fixtures/**", "**/__fixtures__/**", "**/*.generated.*",
               "**/generated/**", "**/*.d.ts", "**/package-lock.json", "**/*.lock"]
CODE_EXTENSIONS = ["js", "mjs", "cjs", "jsx", "ts", "mts", "cts", "tsx", "vue", "svelte", "py", "ps1", "psm1", "sh",
                   "bash", "php", "go", "rb", "cs", "java", "kt", "swift", "rs", "ejs", "sql"]
MAX_BYTES = 8 * 1024 * 1024


def glob_to_regex(glob: str) -> re.Pattern:
    """The code map's minimal glob: `**` any path, `*` within one segment, `?` one character."""
    out = ""
    i = 0
    while i < len(glob):
        c = glob[i]
        if c == "*" and glob[i + 1:i + 2] == "*":
            if glob[i + 2:i + 3] == "/":
                out += "(?:.*/)?"
                i += 3
            else:
                out += ".*"
                i += 2
            continue
        out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
        i += 1
    return re.compile(f"^{out}$")


def matches_any(path: str, globs: list[str]) -> bool:
    return any(glob_to_regex(g).match(path) for g in globs)


def count_lines(text: str) -> int:
    if not text:
        return 0
    n = text.count("\n") + 1
    return n - 1 if text.endswith("\n") else n


def load_config(repo: Path) -> dict:
    """The repository's code-map.config.json, as far as the size limit uses it."""
    path = repo / CONFIG_FILE
    own = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    return {
        "recordDir": own.get("recordDir", RECORD_DIR),
        "fileLines": own.get("limits", {}).get("fileLines", FILE_LINES),
        # As in the code map: extra patterns add to the defaults; a full list replaces them.
        "ignore": IGNORE + own["ignoreMore"] if "ignoreMore" in own else own.get("ignore", IGNORE),
        "sizeExempt": SIZE_EXEMPT + own["sizeExemptMore"] if "sizeExemptMore" in own else own.get("sizeExempt", SIZE_EXEMPT),
        "codeExtensions": own.get("codeExtensions", CODE_EXTENSIONS),
    }


def repository_files(repo: Path) -> list[str]:
    """Git's list of the repository's files; a folder that is not the top of its own work tree is walked."""
    try:
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, check=True).stdout.strip()
        if Path(top).resolve() == repo.resolve():
            out = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                                 capture_output=True, check=True).stdout.decode("utf-8")
            files = [f for f in out.split("\0") if f]
            if files:
                return files
    except (OSError, subprocess.CalledProcessError):
        pass
    # Walked: leave out .git, node_modules and other repositories inside this one.
    out = []
    for folder, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules") and not (Path(folder, d) / ".git").exists()]
        out += [Path(folder, f).relative_to(repo).as_posix() for f in files]
    return out


def oversized(repo: Path, config: dict) -> dict[str, int]:
    """Every code file over the limit, with its lines."""
    out = {}
    for file in repository_files(repo):
        file = file.replace("\\", "/")
        ext = file.rsplit(".", 1)[-1].lower() if "." in file.rsplit("/", 1)[-1] else ""
        if ext not in config["codeExtensions"] or matches_any(file, config["ignore"]) or matches_any(file, config["sizeExempt"]):
            continue
        path = repo / file
        try:
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        lines = count_lines(data.decode("utf-8", errors="replace"))
        if lines > config["fileLines"]:
            out[file] = lines
    return out


def check_repository(repo: Path, shown_prefix: str) -> list[str]:
    """Errors for one repository: a new file over the limit, or a recorded file that grew."""
    config = load_config(repo)
    record = repo / config["recordDir"] / "sizes.json"
    if not record.is_file():
        return []
    sizes = json.loads(record.read_text(encoding="utf-8"))
    errors = []
    limit = config["fileLines"]
    for file, lines in sorted(oversized(repo, config).items()):
        recorded = sizes.get(file)
        if recorded is None:
            errors.append(f"{shown_prefix}{file}: {lines} lines, over the {limit}-line limit; split it before "
                          "committing, since a new file over the limit is not recorded (SMART-RULE-0041)")
        elif lines > recorded:
            errors.append(f"{shown_prefix}{file}: grew from its recorded {recorded} lines to {lines}; move code "
                          "out of it rather than into it (SMART-RULE-0041)")
    return errors


def validate_file_sizes(root: Path, errors: list[str]) -> None:
    """SMART-RULE-0041 for the mechanics and, when present, the skill library and the memory."""
    for repo, prefix in ((root, "/"), (root / "library", "/library/"), (root / "memory", "/memory/")):
        if repo.is_dir():
            errors.extend(check_repository(repo, prefix))
