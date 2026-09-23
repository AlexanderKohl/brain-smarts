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

import json
import os
import re
import sys
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
    "fetch": True,
    "grace_minutes": 15,
    "main": "main",
    "merge_version_pattern": r"[0-9]+\.[0-9]+\.[0-9]+",
    "placeholder_pattern": r"\b(temp|wip|fixup|squash)\b",
    "remote": "origin",
    "repo": None,
    "where_view_href": None,
}

DIRECTORY_DEFAULTS: dict[str, Any] = {"folder": "boards", "title": "Boards"}


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
    raise ConfigError("CONTRACT.md not found above " + ", ".join(str(c) for c in candidates))


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
                              + " - see /shared/skills/owner-board/SKILL.md, Configuration")
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
