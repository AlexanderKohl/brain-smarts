"""Saving a page's decisions into the inbox folder (design 04 of the personal CRM, increment 2).

The board server (`serve_boards.py`, its posts in `serve_post.py`) files what a page saves here,
in `/memory/inbox/` of the checkout it runs from: the owner's hand-over folder that conductors
already read. The body is the exact JSON the page would have downloaded, written unchanged, so
every apply script keeps working on it. Four kinds:

| kind | file name | schema | apply script |
|---|---|---|---|
| `verdicts` | `<verdict_prefix><board>-<stamp>.json` of a registered board | that board's `verdict_schema` | `apply_events.py` |
| `task-actions` | `task-actions-<stamp>.json` | `owner-board/task-actions/v1` | `apply_events.py` |
| `inbox-decisions` | `inbox-decisions-<stamp>.json` | `mail-review/decisions/v2` (v1 still accepted) | `inbox_apply.py` |
| `social-decisions` | `social-decisions-<stamp>.json` | `crm/social-decisions/v1` | `social_links_apply.py` |

`<stamp>` is the body's own `savedAt` as the page names its download (`2026-01-10T10:00:00.000Z`
gives `2026-01-10-10-00-00`). The name is this module's, never one the page sends; the file is
written under a temporary dot name and then linked to its name, which never replaces a file: a
second save in the same second gets `-2`, `-3`. The `schema` is checked and, for verdicts, that
the board is registered; inbox decisions are also checked, read-only, against the current
snapshot of their account (`inbox_triage.validate_decisions`), so a stale page is told at once.
Nothing is applied or dry-run here.

The two library kinds are offered only when their skill is checked out under `/library/` (the
mail-review and crm skills); their prefixes and schemas are read from the skill's own module. The
mail-review skill also brings `inbox_serve.py`, the full text of one message on demand
(`mail_text`, for `POST /_mail/text`); without the skill `/_board-server.json` says `"mail": false`.
`inbox_folders` gives `apply_events.py` the inbox folders it reads by default: this memory's, and
when this memory is a session copy (a linked worktree), the shared checkout's, where the server
saves.
"""
from __future__ import annotations

import datetime
import importlib
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import page_js

INBOX = "inbox"
SHOWN = "/memory/inbox/"
TEMP_PREFIX = ".saving-"
STAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})")
ALIAS_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_NUMBER = 999
GIT_TIMEOUT = 5
_LOCK = threading.Lock()


class Refused(Exception):
    """The body may not be saved; the message is this module's own, safe to show on the page."""


def _count(n: int, word: str) -> str:
    return str(n) + " " + word + ("" if n == 1 else "s")


def _shown(value) -> str:
    """A value the page sent, cut short for a refusal."""
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def stamp_of(body: dict) -> str:
    saved_at = body.get("savedAt")
    match = STAMP_RE.match(saved_at) if isinstance(saved_at, str) else None
    if not match:
        raise Refused("the decisions carry no save time (savedAt)")
    return "%s-%s-%s-%s" % match.groups()


def _library(library: Path, skill: str, module: str, apply_script: str):
    """A library skill's module, when the skill and its apply script are checked out; else None."""
    folder = library / "skills" / skill / "scripts"
    if not (folder / (module + ".py")).is_file() or not (folder / apply_script).is_file():
        return None
    if str(folder) not in sys.path:
        sys.path.append(str(folder))
    try:
        return importlib.import_module(module)
    except Exception:  # noqa: BLE001 – a broken optional skill only removes its kind
        return None


def _place(tmp: str, target: Path) -> None:
    """Give the written file its name, never replacing one: FileExistsError when it is taken."""
    try:
        os.link(tmp, target)
    except FileExistsError:
        raise
    except OSError:      # a file system without links: the lock and this check stand in
        if target.exists():
            raise FileExistsError(str(target))
        os.rename(tmp, target)


def write_new(folder: Path, base: str, raw: bytes) -> str:
    """Write `raw` as `<base>.json`, or `<base>-2.json` and on when that is taken. Returns the name."""
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=TEMP_PREFIX, suffix=".tmp", dir=str(folder))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        with _LOCK:
            for n in range(1, MAX_NUMBER + 1):
                name = base + ("-%d" % n if n > 1 else "") + ".json"
                try:
                    _place(tmp, folder / name)
                    return name
                except FileExistsError:
                    continue
        raise Refused("too many saves in one second")
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Inbox:
    """The inbox folder of one brain, and the kinds of decisions it takes."""

    def __init__(self, brain: Path, folder: Path, boards: list, library: Path | None = None):
        """`library` is the skill library checkout, `<brain>/library` unless a test names another."""
        self.brain, self.folder = Path(brain), Path(folder)
        self.boards = {b["id"]: b for b in boards}
        self.shown = SHOWN
        library = Path(library) if library is not None else self.brain / "library"
        self.mail = _library(library, "mail-review", "inbox_triage", "inbox_apply.py")
        self.social = _library(library, "crm", "social_links_page", "social_links_apply.py")
        serve = _library(library, "mail-review", "inbox_serve", "inbox_apply.py")
        self.fetcher = serve.Fetcher(self.brain) if serve else None     # the full text of a message, on demand

    @classmethod
    def from_config(cls, config) -> "Inbox":
        return cls(config.brain, config.memory / INBOX, config.boards)

    def kinds(self) -> list:
        return (["verdicts", "task-actions"] + (["inbox-decisions"] if self.mail else [])
                + (["social-decisions"] if self.social else []))

    def prefixes(self) -> list:
        """(file prefix, kind) of every kind offered, longest prefix first."""
        out = [(b["verdict_prefix"], "verdicts") for b in self.boards.values()] + [(page_js.TASK_PREFIX, "task-actions")]
        if self.mail:
            out.append((self.mail.FILE_PREFIX, "inbox-decisions"))
        if self.social:
            out.append((self.social.FILE_PREFIX, "social-decisions"))
        return sorted(out, key=lambda p: len(p[0]), reverse=True)

    def kind_of(self, name: str) -> str | None:
        if name.startswith(".") or not name.endswith(".json"):
            return None
        return next((kind for prefix, kind in self.prefixes() if name.startswith(prefix)), None)

    # ------------------------------------------------------------ the checks, one per kind

    def _verdicts(self, body: dict, stamp: str) -> tuple:
        which = body.get("board")
        board = self.boards.get(which) if isinstance(which, str) else None
        if board is None:
            raise Refused("board " + _shown(which) + " is not registered")
        if body.get("schema") != board["verdict_schema"]:
            raise Refused("not a verdicts file for the " + board["id"] + " board")
        detail = board["label"] + ", " + _count(len(body.get("verdicts") or []), "verdict")
        if body.get("tasks"):
            detail += ", " + _count(len(body["tasks"]), "task action")
        return board["verdict_prefix"] + board["id"] + "-" + stamp, detail

    def _tasks(self, body: dict, stamp: str) -> tuple:
        if body.get("schema") != page_js.TASK_SCHEMA:
            raise Refused("not a task-actions file")
        return page_js.TASK_PREFIX + stamp, _count(len(body.get("tasks") or []), "task action")

    def _inbox(self, body: dict, stamp: str) -> tuple:
        mail = self.mail
        if body.get("schema") not in (mail.SCHEMA_DECISIONS, mail.SCHEMA_DECISIONS_V2):
            raise Refused("not an inbox decisions file")
        snap = body.get("snapshot") if isinstance(body.get("snapshot"), dict) else {}
        alias = snap.get("account") or body.get("account")
        if not isinstance(alias, str) or not ALIAS_RE.match(alias):
            raise Refused("the decisions name no account")
        snapshot = mail.load_json(self.brain / "temp" / "mail-review" / alias / "snapshot.json")
        if not snapshot:
            raise Refused("there is no snapshot of " + alias + " to check the decisions against")
        errors = mail.validate_decisions(body, snapshot)
        if errors:
            raise Refused("the decisions do not fit the current snapshot of " + alias + " ("
                          + _count(len(errors), "problem") + ") – rebuild the page and decide again")
        return (mail.FILE_PREFIX + stamp,
                "inbox of " + alias + ", " + _count(len(body.get("decisions") or []), "decision"))

    def _social(self, body: dict, stamp: str) -> tuple:
        if body.get("schema") != self.social.DECISIONS_SCHEMA:
            raise Refused("not a social link decisions file")
        return self.social.FILE_PREFIX + stamp, _count(len(body.get("decisions") or []), "social link decision")

    def save(self, kind: str, raw: bytes, body: dict) -> dict:
        """File one body of a kind offered. Raises Refused; returns the answer for the page."""
        check = {"verdicts": self._verdicts, "task-actions": self._tasks,
                 "inbox-decisions": self._inbox, "social-decisions": self._social}
        if kind not in self.kinds():
            raise Refused("nothing is saved at that address")
        base, detail = check[kind](body, stamp_of(body))
        name = write_new(self.folder, base, raw)
        return {"saved": name, "folder": self.shown, "say": "Apply " + name + " (" + detail + ")"}

    def mail_text(self, body: dict) -> tuple:
        """`(status, answer)` for `POST /_mail/text`: one snapshot message's whole text, fetched live
        by the mail-review skill's `inbox_serve.py` (read-only, `messages.get` only)."""
        if self.fetcher is None:
            return 404, {"refused": "nothing is saved at that address"}
        return self.fetcher.text(body)

    def waiting(self) -> list:
        """The saved files still in the folder, oldest first: name, kind, saved time, size."""
        try:
            entries = [e for e in os.scandir(self.folder) if e.is_file()]
        except OSError:
            return []
        out = []
        for entry in entries:
            kind = self.kind_of(entry.name)
            if kind is None:
                continue
            stat = entry.stat()
            saved = datetime.datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds")
            out.append({"name": entry.name, "kind": kind, "saved": saved, "size": stat.st_size})
        return sorted(out, key=lambda e: (e["saved"], e["name"]))


def inbox_folders(memory: Path) -> list:
    """The inbox folders `apply_events.py` reads by default, those that exist: this memory's, and
    the shared checkout's when this memory is a linked worktree of it (a session copy)."""
    memory = Path(memory)
    found = [memory / INBOX]
    try:
        out = subprocess.run(["git", "-C", str(memory), "rev-parse", "--path-format=absolute", "--show-toplevel",
                              "--git-common-dir"], capture_output=True, text=True, timeout=GIT_TIMEOUT)
        lines = out.stdout.split("\n") if out.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired):
        lines = []
    if len(lines) >= 2 and lines[0].strip() and Path(lines[0].strip()).resolve() == memory.resolve():
        common = Path(lines[1].strip())
        if common.name == ".git" and common.parent.resolve() != memory.resolve():
            found.append(common.parent / INBOX)
    return [str(p) for p in found if p.is_dir()]
