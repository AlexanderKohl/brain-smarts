#!/usr/bin/env python3
"""Release notes: one note per change a user would notice, chosen on the project's board.

    python release_notes.py build                                   # team pages, per environment
    python release_notes.py new <project> <slug> --title "..." [--kind changed] [--commit abc123]
    python release_notes.py release <version> --env testing|production [--project <id>] [--date YYYY-MM-DD] [--dry-run]
    python release_notes.py check [--fix]              # every note readable; lists each that is not; exit 1 if any
    python release_notes.py fix                        # repair notes that do not parse (wording unchanged)
    python release_notes.py link <project> [--dry-run] # each note's commits and versions, from trailers
    python release_notes.py apply [--dry-run]          # legacy release-choices-*.json files, as choice events

A note that does not parse never stops a command: `check` and `fix` name it with file, line and
problem; `link` and `build` skip it and say so at the top of their output.

A project is a source of notes: a git repository (`kind: git`, notes in
`release-notes/unreleased/` on its development branch) or a folder (`kind: folder`, notes
written by hand – for example a CRM's changes, kept beside the app's in the same repository).
The owner chooses visibility and edits wording on the project's board (`/shared/skills/owner-board/`);
each choice is an append-only event (`release_choices.py`). `release <version> --env` moves the
notes going out into `released/<version>/`, marks the environment they reached, and writes one
`released` event per open board card at or below that version: those cards retire on both brains
at the next build. The team pages show per environment what has reached it.

Configuration: `/memory/skills/release-notes/config/release-notes.json`, and for a shared board
the project repository's own `brain/status/release-notes.json` (paths relative to that
repository); an owner's memory entry overrides the repository's entry with the same `id`.
Nothing here names an owner, a repository or a person; they come from those files and from
`/memory/OWNER.md`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import release_choices  # noqa: E402
import release_fix  # noqa: E402
import release_link  # noqa: E402
import release_pages  # noqa: E402

VERSION = "0.4.2"
VISIBILITY = ["undecided", "announce", "hold", "internal"]
KINDS = ["added", "changed", "fixed", "removed"]
KIND_ALIASES = {"new": "added"}   # the word people reach for first
FIELDS = ["title", "kind", "area", "audience", "visibility", "look_out_for", "authors",
          "commits", "versions", "workflows", "opened"]
ENVIRONMENTS = release_choices.ENVIRONMENTS
PREFIX = "release-choices-"
TRAILER = re.compile(r"^Release-note:\s*(\S+)\s*$", re.M)


class Refused(Exception):
    pass


# ---------------------------------------------------------------- locations

def brain_root(start: str | None = None) -> Path:
    p = Path(start or __file__).resolve()
    for d in [p] + list(p.parents):
        if (d / "CONTRACT.md").is_file():
            return d
    raise Refused("no CONTRACT.md above " + str(p))


def resolve(root: Path, path: str) -> Path:
    """A repository-root path (`/memory/...`) or an absolute one."""
    if path.startswith("/memory/") or path.startswith("/library/") or path.startswith("/shared/"):
        return root / path.lstrip("/")
    return Path(path)


REPO_DEFINITION = Path("brain") / "status" / "release-notes.json"
REPO_KEYS = ("id", "label", "kind", "development", "production", "since", "folder", "artifact_url",
             "released_on", "source", "local_refs")
ABSOLUTE = re.compile(r"^([A-Za-z]:|[\\/]|~)")


def repo_definition(repository: Path) -> Path:
    """Where a project repository keeps its own release-notes projects."""
    return Path(repository) / REPO_DEFINITION


def inside_repository(folder: str) -> bool:
    """A path relative to the repository root that stays inside it, judged on the text alone."""
    return bool(folder) and not ABSOLUTE.match(folder) and ":" not in folder and \
        ".." not in re.split(r"[\\/]", folder)


def within(base: Path, path: Path) -> bool:
    """True when `path` resolves inside `base` once every link on the way (symlink or junction)
    is followed, also for a path not created yet: its existing part is what is resolved."""
    try:
        Path(path).resolve().relative_to(Path(base).resolve())
    except (OSError, RuntimeError, ValueError):   # outside, or a link loop
        return False
    return True


def confined(repository: Path, folder: str) -> Path | None:
    """`<repository>/<folder>` when it stays inside the repository after every link on the way
    (symlink or junction) is followed; None when the text or the resolved path leaves it.
    Checked before anything under the folder is read or written."""
    if not inside_repository(folder) or not within(repository, Path(repository, folder)):
        return None
    return Path(repository) / folder


def repo_projects(path: Path, problems: list) -> list[dict]:
    """The projects a repository defines in `brain/status/release-notes.json`, each bound to that
    repository. Nothing is raised: an unreadable file or a refused entry is one line in `problems`."""
    path = Path(path)
    if not path.is_file():
        return []
    where = "/".join(path.parts[-4:])
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        problems.append(where + " cannot be read: " + str(err))
        return []
    items = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(items, list):
        problems.append(where + " has no `projects` list")
        return []
    repository = path.absolute().parents[2]
    out = []
    for item in items:
        if not isinstance(item, dict) or not item.get("id") or not item.get("label"):
            problems.append(where + ": a project needs an id and a label")
            continue
        pid, kind = str(item["id"]), str(item.get("kind") or "git")
        folder = str(item.get("folder") or "release-notes")
        if kind not in ("git", "folder"):
            problems.append("%s: project %s has kind %s; git or folder" % (where, pid, kind))
        elif confined(repository, folder) is None:
            problems.append("%s: project %s names folder %s; a path relative to the repository root, "
                            "without .. and not leaving it through a link, is needed" % (where, pid, folder))
        elif kind == "git" and not (item.get("development") and item.get("production")):
            problems.append("%s: project %s needs its development and production branches" % (where, pid))
        else:
            project = {k: item[k] for k in REPO_KEYS if k in item}
            project.update(id=pid, kind=kind, folder=folder, repo=repository.name, repository=repository)
            out.append(project)
    return out


def repository_here(start: Path) -> Path | None:
    """The nearest folder at or above `start` that holds `brain/status/release-notes.json`."""
    start = Path(start).absolute()
    for d in [start] + list(start.parents):
        if repo_definition(d).is_file():
            return d
    return None


class Config:
    """The projects, pages and folders of the owner's configuration.

    `repo_definition` is a repository's `brain/status/release-notes.json`: its projects are added
    after the owner's, so a memory entry with the same `id` wins. Without the owner's file (a brain
    that only builds a shared board) the memory configuration is empty; an explicit `path` that
    does not exist is still an error. Problems with the repository file are kept in `problems`."""

    def __init__(self, root: Path, path: Path | None = None, repo_definition: Path | None = None):
        self.root = root
        self.home = root / "memory" / "skills" / "release-notes"
        self.path = path or self.home / "config" / "release-notes.json"
        if path is None and not self.path.is_file():
            data = {}
        else:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        self.data = data
        self.problems: list = []
        owner = read_front(root / "memory" / "OWNER.md")[0] if (root / "memory" / "OWNER.md").exists() else {}
        self.owner = str(owner.get("owner_short_name") or "")
        self.repos_root = Path(data.get("project_repos_root") or owner.get("project_repos_root") or root.parent)
        self.projects = {p["id"]: p for p in data.get("projects", [])}
        if repo_definition is not None:
            for project in repo_projects(Path(repo_definition), self.problems):
                self.projects.setdefault(project["id"], project)
        self.pages = data.get("pages", [])
        self.pages_dir = resolve(root, data.get("pages_dir", "/memory/skills/release-notes/pages"))
        self.inbox = self.home / "in"
        self.applied = self.home / "applied"

    def folder(self, project: dict) -> Path:
        """The folder holding `unreleased/`, `released/` and `choices/` for a project."""
        if project.get("repository"):   # defined by the repository itself: relative to its root
            inside = confined(Path(project["repository"]), str(project["folder"]))
            if inside is None:   # checked again at use: a link may have changed since loading
                raise Refused("project %s: folder %s leaves its repository" % (project["id"], project["folder"]))
            return inside
        if project["kind"] == "git":
            return self.repo(project) / "release-notes"
        folder = str(project["folder"])
        if ":" in folder and not re.match(r"^[A-Za-z]:[\\/]", folder):
            # `<repository>:<path>`: a hand-written source kept inside a project repository.
            repo_name, inside = folder.split(":", 1)
            return self.repos_root / repo_name / inside.strip("/")
        return resolve(self.root, folder)

    def inside(self, project: dict, *parts: str) -> Path:
        """`<folder>/<parts...>`: the path every read and write under a project's folder uses.
        For a project its repository defines, the final path must resolve inside the repository
        (links followed), so a link at any level under the folder – `unreleased`, `choices`,
        `released/<version>`, a note – and every directory created on the way are refused."""
        path = self.folder(project).joinpath(*[str(p) for p in parts])
        if project.get("repository") and not within(project["repository"], path):
            raise Refused("project %s: %s leaves its repository" % (
                project["id"], "/".join([str(project["folder"])] + [str(p) for p in parts])))
        return path

    def repo(self, project: dict) -> Path:
        if project.get("repository"):
            return Path(project["repository"])
        return self.repos_root / project["repo"]


def load_config(root: Path, path: Path | None = None, repository: Path | None = None) -> Config:
    """The one way to load the configuration (SMART-RULE-0018), for the board and the command
    line alike: the owner's, plus the projects `repository` defines in its
    `brain/status/release-notes.json` when one is given. The owner's entry with the same id wins."""
    return Config(Path(root), path, repo_definition(repository) if repository is not None else None)


# ---------------------------------------------------------------- notes

def read_front(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    end = text.index("\n---", 3)
    return yaml.safe_load(text[4:end]) or {}, text[end + 4:].lstrip("\n")


def write_note(path: Path, front: dict, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(front, sort_keys=False, allow_unicode=True, width=100) + "---\n\n" + body.strip() + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")


def load_notes(folder: Path, broken: list | None = None) -> list[dict]:
    """Every readable note, in slug order. A note whose front matter does not parse is never
    raised: it is appended to `broken` (slug, path, `line N: problem`) when a list is given."""
    notes = []
    for f in sorted(folder.glob("*.md")):
        if f.name.lower() == "readme.md":
            continue
        if not within(folder, f):   # a note that is a link leading out of its folder is never read
            if broken is not None:
                broken.append({"slug": f.stem, "path": f, "error": "a link that leaves the folder; refused"})
            continue
        try:
            front, body = read_front(f)
        except yaml.YAMLError:
            parts = release_fix.split(f.read_text(encoding="utf-8"))
            error = release_fix.parse_error(parts[0]) if parts else "no front matter"
            if broken is not None:
                broken.append({"slug": f.stem, "path": f, "error": error or "does not parse"})
            continue
        front["kind"] = KIND_ALIASES.get(front.get("kind"), front.get("kind"))
        notes.append({"slug": f.stem, "path": f, "front": front, "body": body})
    return notes


def skipped_lines(cfg: Config) -> list[str]:
    """One line per unreleased note that does not parse, for the top of an output."""
    return release_fix.skipped_lines(cfg.projects.values(), lambda p, *parts: cfg.inside(p, "unreleased", *parts))


def fix_notes(cfg: Config) -> tuple[list[str], list[str]]:
    """Repair every unreleased note that does not parse: (fixed, still broken), one line each."""
    return release_fix.fix_notes(cfg.projects.values(), lambda p, *parts: cfg.inside(p, "unreleased", *parts))


def visibility(note: dict) -> str:
    v = note["front"].get("visibility") or "undecided"
    return v if v in VISIBILITY else "undecided"


def problems(note: dict) -> list[str]:
    out = []
    f = note["front"]
    if not f.get("title"):
        out.append("no title")
    if f.get("visibility") not in VISIBILITY:
        out.append("visibility must be one of " + ", ".join(VISIBILITY))
    if f.get("kind") and f["kind"] not in KINDS:
        out.append("kind must be one of " + ", ".join(KINDS))
    return out


def stamp(root: Path) -> str:
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def new_note(cfg: Config, project: dict, slug: str, title: str, kind: str = "changed",
             commits: list | None = None, body: str = "") -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise Refused("a slug is lower-case words joined by hyphens: " + slug)
    path = cfg.inside(project, "unreleased", slug + ".md")
    if path.exists():
        raise Refused("a note already exists: " + str(path))
    front = {}
    if project["kind"] == "folder" and str(cfg.folder(project)).startswith(str(cfg.root / "memory")):
        now = stamp(cfg.root)   # a memory file carries the brain's metadata
        front.update({"id": "release-note-" + slug, "type": "release_note", "schema_version": 0.2,
                      "contract": "/CONTRACT.md", "created": now, "updated": now})
    front.update({"title": title, "kind": kind, "area": project.get("label", ""), "audience": [],
                  "visibility": "undecided", "look_out_for": "", "authors": [],
                  "commits": list(commits or []), "workflows": [],
                  "opened": dt.date.today().isoformat()})
    write_note(path, front, body or "(what a user will notice, in their words)")
    return path


# ---------------------------------------------------------------- git

def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise Refused("git " + " ".join(args) + ": " + r.stderr.strip())
    return r.stdout


def ref(project: dict, which: str) -> str:
    branch = project[which]
    return branch if project.get("local_refs") else "origin/" + branch


DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")


def ignored(f: Path) -> tuple[set, set]:
    """Commits set aside in a `not-user-visible.txt` written before choices became events. The
    file is read for what it already says and never written to."""
    hashes, subjects = set(), set()
    if not f.exists():
        return hashes, subjects
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        first, _, rest = line.strip().partition(" ")
        if DATE.match(first):
            subjects.add(rest.strip())
        else:
            hashes.add(first)
            if rest.strip():
                subjects.add(rest.strip())
    return hashes, subjects


def unnoted(cfg: Config, project: dict, notes: list[dict], dealt: set | None = None) -> list[dict]:
    """Commits on the way to production that no note names and nobody set aside."""
    if project["kind"] != "git":
        return []
    repo = cfg.repo(project)
    args = ["log", "--no-merges", "--format=%h%x1f%an%x1f%ad%x1f%s%x1f%b%x1e", "--date=short",
            ref(project, "production") + ".." + ref(project, "development")]
    if project.get("since"):
        args.insert(2, "--since=" + project["since"])
    claimed = [str(c) for n in notes for c in (n["front"].get("commits") or [])]
    slugs = {n["slug"] for n in notes}
    skip, skip_subjects = ignored(cfg.inside(project, "not-user-visible.txt"))
    skip |= set(dealt or ())
    out = []
    for rec in git(repo, *args).split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) < 5:
            continue
        h, author, date, subject, body = parts
        if any(h.startswith(c) or c.startswith(h) for c in claimed + list(skip)) or subject.strip() in skip_subjects:
            continue
        if any(t in slugs for t in TRAILER.findall(body)):
            continue
        files = [f for f in git(repo, "show", "--name-only", "--format=", h).splitlines() if f.strip()]
        if files and all(f.startswith("release-notes/") for f in files):
            continue
        out.append({"hash": h, "author": author, "date": date, "subject": subject})
    return out


def git_ready(cfg: Config, project: dict) -> None:
    """Edits to a repository's notes happen on its development branch only."""
    if project["kind"] != "git":
        return
    branch = git(cfg.repo(project), "rev-parse", "--abbrev-ref", "HEAD").strip()
    if branch != project["development"]:
        raise Refused("%s is on %s, not %s: check out %s first" % (
            project["repo"], branch, project["development"], project["development"]))


# ---------------------------------------------------------------- releases

def releases(cfg: Config, project: dict) -> list[dict]:
    """Every `released/<version>/release.json` with its announced notes. A release recorded
    before environments were kept counts as released to production on its date."""
    out = []
    for found in sorted(cfg.inside(project, "released").glob("*/release.json")):
        rj = cfg.inside(project, "released", found.parent.name, found.name)
        rec = json.loads(rj.read_text(encoding="utf-8"))
        rec.setdefault("environments", {"production": rec.get("date", "")})
        rec["notes"] = [n for n in load_notes(rj.parent) if visibility(n) == "announce"]
        out.append(rec)
    return out


def release(cfg: Config, project: dict, version: str, env: str, date: str | None = None,
            dry_run: bool = False) -> list[str]:
    """Move the notes going out into `released/<version>/`, mark the environment reached, and
    retire the board cards at or below the version with `released` events."""
    if env not in ENVIRONMENTS:
        raise Refused("--env must be one of " + ", ".join(ENVIRONMENTS))
    target = cfg.inside(project, "released", version)
    record = cfg.inside(project, "released", version, "release.json")
    date = date or dt.date.today().isoformat()
    report: list[str] = []
    if record.exists():
        rec = json.loads(record.read_text(encoding="utf-8"))
        rec.setdefault("environments", {"production": rec.get("date", "")})
        if env in rec["environments"]:
            raise Refused("release %s of %s already reached %s on %s" % (version, project["id"], env, rec["environments"][env]))
        rec["environments"][env] = date
        if not dry_run:
            record.write_text(json.dumps(rec, indent=2) + "\n", encoding="utf-8")
        report.append("release %s %s reached %s on %s" % (project["id"], version, env, date))
    else:
        notes, broken, _ = release_choices.collect_unreleased(cfg, project)
        going = [n for n in notes if visibility(n) in ("announce", "internal")]
        if project["kind"] == "git":
            git_ready(cfg, project)
            repo = cfg.repo(project)
            if not project.get("local_refs"):
                git(repo, "fetch", "-q", "origin")
            branch = ref(project, "production" if env == "production" else "development")
            for n in going:
                for c in n["front"].get("commits") or []:
                    r = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", str(c), branch])
                    if r.returncode != 0:
                        raise Refused("%s: commit %s of %s is not on %s yet - release after the merge" % (
                            project["id"], c, n["slug"], branch))
        if not dry_run:
            target.mkdir(parents=True)
            record.write_text(json.dumps({"project": project["id"], "version": version, "date": date,
                                          "environments": {env: date}}, indent=2) + "\n", encoding="utf-8")
        for n in going:
            report.append("%s %s (%s)" % ("would move" if dry_run else "moved", n["slug"], visibility(n)))
            if dry_run:
                continue
            dest = cfg.inside(project, "released", version, n["path"].name)
            try:
                if project["kind"] != "git":
                    raise Refused("not a git project")
                git(cfg.repo(project), "mv", str(n["path"]), str(dest))   # staged for the conductor
            except Refused:
                shutil.move(str(n["path"]), str(dest))   # a note not tracked yet, or a folder source
            write_note(dest, n["front"], n["body"])   # the chosen wording and visibility, baked in
        kept = [n["slug"] for n in notes if n not in going]
        if kept:
            report.append("carried forward: " + ", ".join(kept))
        for b in broken:
            report.append("skipped %s: does not parse (%s) - run release_notes.py fix" % (b["slug"], b["error"]))
        report.append("release %s %s to %s dated %s" % (project["id"], version, env, date))
    report += retire_cards(cfg, project, version, env, dry_run)
    return report


def retire_cards(cfg: Config, project: dict, version: str, env: str, dry_run: bool = False) -> list[str]:
    """One `released` event per open card, on every board that draws this project, whose version
    is at or below `version` and that has not reached `env` yet. A production release retires
    the card on both brains; a testing release puts it in the Released fold."""
    scripts = cfg.root / "shared" / "skills" / "owner-board" / "scripts"
    if not (scripts / "events.py").is_file():
        return ["no owner-board skill at " + str(scripts) + ": no cards retired"]
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import board_config  # noqa: E402
    import events  # noqa: E402
    try:
        config = board_config.Config(cfg.root)
    except board_config.ConfigError as err:
        return ["no boards: " + str(err)]
    report = []
    for board in config.boards:
        if project["id"] not in board.get("release_notes", []):
            continue
        state = events.state(board)
        taken = events.ids_in(board)
        for item in state["items"]:
            if not item.get("version") or events.version_key(item["version"]) > events.version_key(version):
                continue
            if env in (item.get("released_to") or {}):
                continue
            event = events.make(board, "released", board["author"], None, taken, card=item["id"], version=version,
                                card_version=item["version"], env=env, title=(item.get("title") or "")[:80],
                                seen_through=item.get("last_event") or "")
            events.write(board, event, dry_run)
            taken.add(event["id"])
            report.append("%s %s: %s %s (%s) released to %s as %s" % (
                "would retire" if dry_run else "retired", board["id"], item["id"], item["version"], project["id"], env, event["id"]))
    return report


def build(cfg: Config) -> list[Path]:
    """The team pages, per environment; `<id>.html` is the production view."""
    written = []
    cfg.pages_dir.mkdir(parents=True, exist_ok=True)
    for page_cfg in cfg.pages:
        rels = []
        for pid in page_cfg["projects"]:
            project = cfg.projects[pid]
            for rec in releases(cfg, project):
                rec["label"] = project["label"]
                rels.append(rec)
        for env in ENVIRONMENTS:
            text = release_pages.build_team(page_cfg, env, [r for r in rels if env in r["environments"]])
            for name in ([page_cfg["id"] + "." + env + ".html"] + ([page_cfg["id"] + ".html"] if env == "production" else [])):
                p = cfg.pages_dir / name
                p.write_text(text, encoding="utf-8", newline="\n")
                written.append(p)
    return written


# ---------------------------------------------------------------- main

def choice_files(cfg: Config, extra: list | None = None) -> list[str]:
    folders = [cfg.inbox, Path.home() / "Downloads"] + [Path(x) for x in (extra or [])]
    found = set()
    for d in folders:
        found.update(glob.glob(str(d / (PREFIX + "*.json"))))
    return sorted(found, key=os.path.getmtime)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", help="brain root (default: found by moving upwards to CONTRACT.md)")
    ap.add_argument("--config", help="configuration file")
    ap.add_argument("--repo", help="a project repository whose brain/status/release-notes.json adds projects "
                                   "(default: the one holding the current folder, if any)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    ck = sub.add_parser("check")
    ck.add_argument("--fix", action="store_true", help="repair the notes that do not parse first")
    sub.add_parser("fix")
    n = sub.add_parser("new")
    n.add_argument("project")
    n.add_argument("slug")
    n.add_argument("--title", required=True)
    n.add_argument("--kind", default="changed", choices=KINDS)
    n.add_argument("--commit", action="append", default=[])
    a = sub.add_parser("apply")
    a.add_argument("--dry-run", action="store_true")
    a.add_argument("--from", dest="extra", action="append", default=[])
    lk = sub.add_parser("link")
    lk.add_argument("project")
    lk.add_argument("--dry-run", action="store_true")
    r = sub.add_parser("release")
    r.add_argument("version")
    r.add_argument("--env", required=True, choices=list(ENVIRONMENTS))
    r.add_argument("--project", help="default: the only git project, or name one")
    r.add_argument("--date")
    r.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    try:
        root = brain_root(args.root)
        repository = Path(args.repo) if args.repo else repository_here(Path.cwd())
        if repository is not None and not repo_definition(repository).is_file():
            raise Refused("no brain/status/release-notes.json in " + str(repository))
        cfg = load_config(root, Path(args.config) if args.config else None, repository)
        for line in cfg.problems:
            print("release-notes: " + line, file=sys.stderr)
        if args.cmd == "new":
            print(new_note(cfg, cfg.projects[args.project], args.slug, args.title, args.kind, args.commit))
        elif args.cmd in ("check", "fix"):
            bad = 0
            if args.cmd == "fix" or args.fix:
                fixed, left = fix_notes(cfg)
                for line in fixed + left:
                    print(line)
                print("%d note(s) fixed, %d could not be repaired" % (len(fixed), len(left)))
                if args.cmd == "fix":
                    return 1 if left else 0
            for project in cfg.projects.values():
                broken: list = []
                for note in load_notes(cfg.inside(project, "unreleased"), broken):
                    for msg in problems(note):
                        bad += 1
                        print("%s/%s: %s" % (project["id"], note["slug"], msg))
                for b in broken:
                    bad += 1
                    print("%s/%s: does not parse - %s: %s" % (project["id"], b["slug"], b["path"], b["error"]))
            print("ok" if not bad else "%d problem(s)" % bad)
            return 1 if bad else 0
        elif args.cmd == "apply":
            files = choice_files(cfg, args.extra)
            if not files:
                print("nothing saved - choices are made on the project's board and saved with its verdicts")
            for f in files:
                print(os.path.basename(f))
                saved = json.loads(Path(f).read_text(encoding="utf-8"))
                for line in release_choices.apply_choices(cfg, saved, cfg.owner or "owner", saved.get("savedAt") or "", args.dry_run):
                    print("  " + line)
                if not args.dry_run:
                    cfg.applied.mkdir(parents=True, exist_ok=True)
                    shutil.move(f, str(cfg.applied / os.path.basename(f)))
        elif args.cmd == "link":
            project = cfg.projects[args.project]
            if project["kind"] != "git":
                raise Refused(f"{args.project} is not a git project: its notes name no commits")
            # Every commit that names a note, whenever made: `since` bounds only the list of commits
            # without a note.
            named = release_link.named_by(cfg.repo(project), git, ref(project, "development"), TRAILER)
            broken = []
            notes = load_notes(cfg.inside(project, "unreleased"), broken)
            for b in broken:
                print("skipped %s/%s: %s (%s) - run release_notes.py fix" % (project["id"], b["slug"], b["error"], b["path"]))
            lines = release_link.link(notes, named, write_note, args.dry_run)
            for line in lines:
                print(line)
            print("%d note(s) %s" % (len(lines), "would change" if args.dry_run else "changed"))
        elif args.cmd == "release":
            which = args.project or next((p["id"] for p in cfg.projects.values() if p["kind"] == "git"), None)
            if not which or which not in cfg.projects:
                raise Refused("name the project with --project; configured: " + ", ".join(cfg.projects))
            for line in release(cfg, cfg.projects[which], args.version, args.env, args.date, args.dry_run):
                print(line)
        if args.cmd in ("build", "apply", "release", "new", "link") and not getattr(args, "dry_run", False):
            if args.cmd == "build":
                for line in skipped_lines(cfg):
                    print(line)
            for w in build(cfg):
                print("wrote " + str(w))
    except (Refused, KeyError) as err:
        print("release-notes: " + str(err), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
