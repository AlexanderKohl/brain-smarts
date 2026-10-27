"""Choices as events: what each person decided about a note, folded the same way on every brain.

A note file is written by its author and edited by nobody else. What the owner chooses on the
board – a note's visibility, a wording change, what to do with a commit no note claims – is one
file under `<release-notes>/choices/<author>-<UTC stamp>.json`, append-only, never edited or
moved. `fold` reads them all in `(saved_at, author, id)` order and derives the effective note:
for each field the **earliest** choice decides; a later choice by the same author replaces
their own (an owner revising a choice is routine); a later different choice by another author
does not change the value but is listed as a conflict and drawn on the board, so both see it.

Public, for the owner-board skill's release-notes section and for `release_notes.py release`:

    load_config(brain_root, repository=None)      -> release_notes.Config
    collect_unreleased(cfg, project)              -> (effective notes, broken notes, conflicts)
    collect_loose(cfg, project, notes)            -> commits in no note that nobody set aside
    collect_released(cfg, project)                -> {"testing": [...], "production": [...]}
    apply_choices(cfg, saved, by, saved_at, dry)  -> one line per choice event written

Ids come from the owner-board skill's `events` module (one implementation of the id rule).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ENVIRONMENTS = ("testing", "production")
NOTE_FIELDS = ("visibility", "title", "body", "look_out_for")
COMMIT_ACTIONS = ("skip", "add", "new")
SCHEMA = "release-notes/choices/v1"


def _rn():
    import release_notes  # noqa: E402  (lazy: release_notes imports this module)
    return release_notes


def _events(root: Path):
    scripts = root / "shared" / "skills" / "owner-board" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import events  # noqa: E402
    return events


def load_config(root: Path, path: Path | None = None, repository: Path | None = None):
    """The release-notes configuration; `repository` adds that repository's own projects.
    The same function the command line uses (`release_notes.load_config`, SMART-RULE-0018)."""
    return _rn().load_config(Path(root), path, repository)


def repo_definition(repository: Path) -> Path:
    """Where a project repository keeps its own release-notes projects (`brain/status/release-notes.json`)."""
    return _rn().repo_definition(repository)


# ---------------------------------------------------------------- the events

def read_choices(cfg, project: dict) -> list:
    out = []
    sub = cfg.inside(project, "choices")
    if not sub.is_dir():
        return out
    for found in sorted(sub.glob("*.json")):
        path = cfg.inside(project, "choices", found.name)
        try:
            choice = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as err:
            raise ValueError("choice " + str(path) + " cannot be read: " + str(err)) from err
        choice.setdefault("id", path.stem)
        out.append(choice)
    return sorted(out, key=lambda c: (str(c.get("saved_at") or ""), str(c.get("by") or ""), str(c.get("id") or "")))


def fold(choices: list) -> dict:
    """`{"notes": {slug: {field: {value, by, at}}}, "conflicts": {slug: [...]}, "commits": {hash: {...}}}`."""
    notes: dict = {}
    conflicts: dict = {}
    commits: dict = {}

    def settle(slot: dict, key: str, value, by: str, at: str, slug: str | None):
        have = slot.get(key)
        if have is None or have["by"] == by:
            slot[key] = {"value": value, "by": by, "at": at}
        elif have["value"] != value:
            conflicts.setdefault(slug or key, []).append(
                {"field": key, "first": {"by": have["by"], "value": have["value"]}, "later": {"by": by, "value": value}})

    for c in choices:
        by, at = str(c.get("by") or ""), str(c.get("saved_at") or "")
        if c.get("kind") == "note" and c.get("slug"):
            slot = notes.setdefault(str(c["slug"]), {})
            for field, value in (c.get("fields") or {}).items():
                if field in NOTE_FIELDS:
                    settle(slot, field, value, by, at, str(c["slug"]))
        elif c.get("kind") == "commit" and c.get("hash"):
            action = {"action": c.get("action"), "slug": c.get("slug") or ""}
            settle(commits, str(c["hash"]), action, by, at, None)
    return {"notes": notes, "conflicts": conflicts, "commits": commits}


def effective(note: dict, folded: dict) -> dict:
    """The note as the choices make it: a copy with the chosen fields laid over the file's."""
    out = dict(note, front=dict(note["front"]))
    for field, chosen in (folded["notes"].get(note["slug"]) or {}).items():
        if field == "body":
            out["body"] = str(chosen["value"])
        else:
            out["front"][field] = chosen["value"]
    out["conflicts"] = list(folded["conflicts"].get(note["slug"]) or [])
    return out


# ---------------------------------------------------------------- collecting

def collect_unreleased(cfg, project: dict) -> tuple:
    """(effective unreleased notes in slug order, notes that do not parse, conflicts by slug)."""
    rn = _rn()
    broken: list = []
    folded = fold(read_choices(cfg, project))
    notes = [effective(n, folded) for n in rn.load_notes(cfg.inside(project, "unreleased"), broken)]
    return notes, broken, folded["conflicts"]


def collect_loose(cfg, project: dict, notes: list) -> list:
    """Commits on the way to production that no note names and no choice has dealt with."""
    rn = _rn()
    folded = fold(read_choices(cfg, project))
    dealt = {h for h, c in folded["commits"].items() if (c["value"] or {}).get("action") in COMMIT_ACTIONS}
    return rn.unnoted(cfg, project, notes, dealt)


def collect_released(cfg, project: dict) -> dict:
    """Every release of the project, per environment, newest first."""
    rn = _rn()
    out = {env: [] for env in ENVIRONMENTS}
    for rec in rn.releases(cfg, project):
        for env in ENVIRONMENTS:
            if env in (rec.get("environments") or {}):
                out[env].append(rec)
    for env in ENVIRONMENTS:
        out[env].sort(key=lambda r: (r["environments"][env], r.get("version", "")), reverse=True)
    return out


# ---------------------------------------------------------------- applying

def apply_choices(cfg, saved: dict, by: str, saved_at: str, dry_run: bool = False) -> list:
    """Write one choice event per note entry and per commit entry. Returns one line each.

    `saved` is `{"notes": [{project, slug, visibility?, title?, body?, look_out_for?}],
    "commits": [{project, hash, action, slug?, subject?}]}`, as the board saves it. A choice
    on a note that is not waiting (released or renamed since the page was built) is skipped.
    A `new` commit choice also creates the note, by this author, so the file arrives with the
    choice.
    """
    rn = _rn()
    ev = _events(cfg.root)
    report: list = []
    taken: dict = {}
    for e in saved.get("notes") or []:
        project = cfg.projects.get(e.get("project"))
        if not project:
            report.append("SKIPPED note " + str(e.get("slug")) + ": unknown project " + str(e.get("project")))
            continue
        if not cfg.inside(project, "unreleased", str(e.get("slug")) + ".md").is_file():
            report.append("SKIPPED " + str(e.get("slug")) + ": no such note waiting (released or renamed since the page was built)")
            continue
        fields = {k: e[k] for k in NOTE_FIELDS if k in e}
        if "visibility" in fields and fields["visibility"] not in rn.VISIBILITY:
            fields.pop("visibility")
        if not fields:
            continue
        event = _make(ev, cfg, project, by, saved_at, taken, kind="note", project=project["id"], slug=str(e["slug"]), fields=fields)
        _write(cfg, project, event, dry_run)
        report.append("choice %s: %s/%s %s" % (event["id"], project["id"], e["slug"], ", ".join(sorted(fields))))
    for c in saved.get("commits") or []:
        project = cfg.projects.get(c.get("project"))
        if not project or c.get("action") not in COMMIT_ACTIONS or not c.get("hash"):
            report.append("SKIPPED commit " + str(c.get("hash")) + ": " + ("unknown project" if not project else "unknown action " + str(c.get("action"))))
            continue
        slug = str(c.get("slug") or "")
        if c["action"] == "new":
            slug = re.sub(r"[^a-z0-9]+", "-", str(c.get("subject") or "").lower()).strip("-")[:50] or str(c["hash"])
            if not dry_run and not cfg.inside(project, "unreleased", slug + ".md").exists():
                rn.new_note(cfg, project, slug, c.get("subject") or slug, commits=[c["hash"]])
            report.append("%s: new note %s from %s - write it from the user's side" % (project["id"], slug, c["hash"]))
        event = _make(ev, cfg, project, by, saved_at, taken, kind="commit", project=project["id"], hash=str(c["hash"]),
                      action=c["action"], slug=slug, subject=c.get("subject") or "")
        _write(cfg, project, event, dry_run)
        report.append("choice %s: %s %s %s" % (event["id"], project["id"], c["hash"], c["action"] + ((" -> " + slug) if slug else "")))
    return report


def _make(ev, cfg, source: dict, by: str, saved_at: str, taken: dict, **fields) -> dict:
    sub = cfg.inside(source, "choices")
    have = taken.setdefault(str(sub), {p.stem for p in sub.glob("*.json")} if sub.is_dir() else set())
    moment = ev.utc(saved_at or None)
    event = {"id": ev.new_id(by, moment, have), "schema": SCHEMA, "by": ev.author_of(by), "saved_at": ev.iso(moment)}
    event.update(fields)
    have.add(event["id"])
    return event


def _write(cfg, project: dict, event: dict, dry_run: bool) -> None:
    path = cfg.inside(project, "choices", event["id"] + ".json")
    if path.exists():
        raise FileExistsError("choice " + event["id"] + " already exists and is never rewritten")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(event, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
