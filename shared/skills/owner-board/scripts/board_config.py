"""Find the brain, the memory checkout and the owner-board configuration.

Every owner-board script resolves its boards through this module, so there is one answer to
"which boards exist and where do they live". Nothing here names a machine path: the brain root
is found by moving upwards to `CONTRACT.md` (CONTRACT section 3.5), the memory checkout is
`<brain_root>/memory/`, and everything owner-specific comes from

    /memory/skills/owner-board/config/boards.json

whose schema is documented in `/shared/skills/owner-board/SKILL.md` (section "Configuration").
A value such as `{project_repos_root}/example-product` is filled from `/memory/OWNER.md`.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
import os
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any

SKILL = "owner-board"
CONFIG_PARTS = ("skills", SKILL, "config", "boards.json")

# Defaults for one board entry. Anything not listed in the owner's entry takes these values.
# Alphabetical, so a reader can find a key without knowing the history of the file.
BOARD_DEFAULTS: dict[str, Any] = {
    "blurb": "",
    "built_version": None,
    "committed_version": None,
    "copy_only_prefixes": ["about:", "chrome-extension://", "chrome://", "moz-extension://"],
    "favicon": None,
    "fetch": True,
    "grace_minutes": 15,
    "main": "main",
    "merge_version_pattern": r"[0-9]+\.[0-9]+\.[0-9]+",
    "placeholder_pattern": r"\b(temp|wip|fixup|squash)\b",
    "remote": "origin",
    "repo": None,
    "where_view_href": None,
}

DIRECTORY_DEFAULTS: dict[str, Any] = {"favicon": None, "folder": "boards", "title": "Boards"}

# The tab icon of every generated page when the owner names none: a board of three columns on a
# mid-green tile, which reads on a light and on a dark tab strip. Inline, so a page opened from
# file:// needs no second file.
DEFAULT_FAVICON = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="7" fill="#1f7a5a"/>'
    '<rect x="6" y="7" width="5.5" height="18" rx="1.5" fill="#fff"/>'
    '<rect x="13.25" y="7" width="5.5" height="12" rx="1.5" fill="#fff" opacity=".85"/>'
    '<rect x="20.5" y="7" width="5.5" height="8" rx="1.5" fill="#fff" opacity=".7"/>'
    "</svg>"
)

# How task records reach the boards (`task_board.py`). Alphabetical. `auto_boards` off means a
# task whose projects have no registered board is shown on the personal board; on, such a
# project gets a generated task-only board of its own under `<directory>/<auto_folder>/`.
TASKS_DEFAULTS: dict[str, Any] = {
    "auto_boards": False,
    "auto_folder": "projects",
    "auto_roots": ["/memory/projects/"],
    "completed_days": 14,
    "enabled": True,
    "store": "tasks",
}

PERSONAL_DEFAULTS: dict[str, Any] = {
    "blurb": "Every task no project board holds",
    "id": "personal",
    "label": "Personal tasks",
    "page": "personal.html",
}


MSYS_HINT = ("Git Bash rewrites an argument that starts with / into a Windows path; "
             "run the command with MSYS_NO_PATHCONV=1 in front")


def looks_path_converted(value: str | None) -> bool:
    """True for a repository-root path that Git Bash (MSYS) has turned into a Windows path."""
    return bool(value) and bool(re.match(r"^[A-Za-z]:[\/]", str(value))) and (
        bool(os.environ.get("MSYSTEM")) or bool(re.search(r"[\/]Git[\/]", str(value), re.I)))


def _hint(value) -> str:
    return " (" + MSYS_HINT + ")" if looks_path_converted(value) else ""


class ConfigError(Exception):
    """The configuration is missing, unreadable or names something that does not exist."""


def find_brain_root(start: str | os.PathLike | None = None) -> Path:
    """The nearest folder at or above `start` that holds `CONTRACT.md`.

    Without `start`, the current directory is tried first and then this script's own folder,
    so a command run from anywhere inside the brain, or from outside it with the script's full
    path, finds the same root.
    """
    candidates: list[Path] = []
    if start is not None:
        candidates.append(Path(start))
    else:
        candidates += [Path.cwd(), Path(__file__).resolve().parent]
    for candidate in candidates:
        here = candidate.resolve()
        for folder in (here, *here.parents):
            if (folder / "CONTRACT.md").is_file():
                return folder
    raise ConfigError("CONTRACT.md not found above " + ", ".join(str(c) for c in candidates) + _hint(start))


def front_matter(path: Path) -> dict[str, str]:
    """Flat `key: value` pairs from a Markdown file's YAML front matter. Lists are ignored."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    out: dict[str, str] = {}
    for line in text[3:end if end > 0 else len(text)].splitlines():
        found = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if found and found.group(2).strip():
            out[found.group(1)] = found.group(2).strip().strip('"')
    return out


def _fill(template: str, values: dict[str, str]) -> str:
    def swap(match: re.Match) -> str:
        key = match.group(1)
        if key not in values or not values[key]:
            raise ConfigError("{" + key + "} is used in the owner-board configuration but has no value")
        return values[key]
    return re.sub(r"\{([A-Za-z_]+)\}", swap, template)


class Config:
    """The owner-board configuration for one brain, with every path made absolute."""

    def __init__(self, root: str | os.PathLike | None = None, config_path: str | os.PathLike | None = None):
        self.brain = find_brain_root(root)
        self.memory = self.brain / "memory"
        self.path = Path(config_path) if config_path else self.memory.joinpath(*CONFIG_PARTS)
        if not self.path.is_file():
            raise ConfigError("no owner-board configuration at " + str(self.path)
                              + " - see /shared/skills/owner-board/SKILL.md, Configuration" + _hint(config_path))
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except ValueError as err:
            raise ConfigError(str(self.path) + " is not valid JSON: " + str(err)) from err
        self.raw = raw
        self.profile = front_matter(self.memory / "OWNER.md")
        self.owner = str(raw.get("owner_name") or self.profile.get("owner_short_name") or "")
        self.directory = dict(DIRECTORY_DEFAULTS, **(raw.get("directory") or {}))
        self.directory_folder = self.memory / self.directory["folder"]
        self.boards = [self._board(entry) for entry in raw.get("boards") or []]
        seen: set[str] = set()
        for board in self.boards:
            if board["id"] in seen:
                raise ConfigError("board id " + board["id"] + " is registered twice")
            seen.add(board["id"])
        # Other generated pages the directory links to, such as a contact register's page:
        # each {"label", "page", "blurb"}, `page` relative to the directory folder.
        self.pages = [dict(entry) for entry in raw.get("pages") or [] if entry.get("label") and entry.get("page")]
        tasks = dict(raw.get("tasks") or {})
        self.personal = dict(PERSONAL_DEFAULTS, **(tasks.pop("personal", None) or {}))
        self.tasks = dict(TASKS_DEFAULTS, **tasks)
        self.task_store = self.memory / str(self.tasks["store"]).replace("/", os.sep)
        if self.personal["id"] in seen:
            raise ConfigError("the personal board id " + self.personal["id"]
                              + " is also a registered board id")

    def _board(self, entry: dict) -> dict:
        for key in ("id", "label", "status"):
            if not entry.get(key):
                raise ConfigError("a board entry in " + str(self.path) + " has no " + key)
        board = dict(BOARD_DEFAULTS, **entry)
        board.setdefault("title", board["label"] + ": where we are")
        board.setdefault("verdict_prefix", board["id"] + "-verdicts-")
        board.setdefault("verdict_schema", "owner-board/verdicts/v1")
        board.setdefault("storage_prefix", board["id"] + "-status")
        board.setdefault("node", "/memory/" + board["status"].rsplit("/status", 1)[0])
        board["folder"] = self.memory / board["status"].replace("/", os.sep)
        board["memory"] = self.memory
        board["owner"] = self.owner
        values = {"brain_root": str(self.brain), "memory_root": str(self.memory),
                  "project_repos_root": self.profile.get("project_repos_root", "")}
        if board.get("repo"):
            repo = Path(_fill(str(board["repo"]), values))
            if not repo.is_absolute():
                base = values["project_repos_root"] or str(self.brain.parent)
                repo = Path(base) / repo
            board["repo"] = repo
        return board

    def board(self, which: str | None = None, cwd: str | os.PathLike | None = None) -> dict:
        """One board by id, or the board whose folder holds `cwd`, or the only board."""
        if which:
            for board in self.boards:
                if board["id"] == which:
                    return board
            raise ConfigError("no board " + which + " in " + str(self.path))
        here = Path(cwd or Path.cwd()).resolve()
        for board in self.boards:
            folder = board["folder"].resolve()
            if here == folder or folder in here.parents:
                return board
        if len(self.boards) == 1:
            return self.boards[0]
        raise ConfigError("name a board with --board; registered: "
                          + ", ".join(b["id"] for b in self.boards))


def favicon_href(config: "Config", board: dict | None = None) -> str:
    """The tab icon as a data URI: the board's `favicon`, else the directory's, else the default.

    A value is an SVG string, a `data:` URI, or a file path relative to the directory folder
    (`/memory/boards/` by default). A named file that does not exist is a configuration error,
    not a silent fallback.
    """
    value = (board or {}).get("favicon") or config.directory.get("favicon") or DEFAULT_FAVICON
    value = str(value).strip()
    if value.startswith("data:"):
        return value
    if not value.startswith("<"):
        path = config.directory_folder / value.replace("/", os.sep)
        if not path.is_file():
            raise ConfigError("favicon " + value + " not found at " + str(path))
        if path.suffix.lower() != ".svg":
            mime = mimetypes.guess_type(str(path))[0] or "image/png"
            return "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode("ascii")
        value = path.read_text(encoding="utf-8").strip()
    return "data:image/svg+xml," + urllib.parse.quote(value, safe="=:/")


def favicon_link(config: "Config", board: dict | None = None) -> str:
    """The `<link rel="icon">` tag every generated page carries in its head."""
    return '<link rel="icon" href="' + html.escape(favicon_href(config, board)) + '">'


def add_common_arguments(parser) -> None:
    """The arguments every owner-board command takes, in one place."""
    parser.add_argument("--root", help="brain root (default: found by moving upwards to CONTRACT.md)")
    parser.add_argument("--config", help="configuration file (default: /memory/skills/owner-board/config/boards.json)")
    parser.add_argument("--no-fetch", action="store_true",
                        help="do not fetch the product repository before reconciling")


def load(args) -> Config:
    config = Config(getattr(args, "root", None), getattr(args, "config", None))
    if getattr(args, "no_fetch", False):
        for board in config.boards:
            board["fetch"] = False
    return config


def cli(main, argv=None) -> int:
    """Run a command's `main`, turning a configuration problem into one plain line."""
    try:
        return main(argv)
    except ConfigError as err:
        print("owner-board: " + str(err), file=sys.stderr)
        return 2
