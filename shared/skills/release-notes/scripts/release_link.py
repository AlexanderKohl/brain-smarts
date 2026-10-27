"""`link`: a note's commits and versions, read from the commits that name it with a
`Release-note: <slug>` trailer. The owner's rule (MEMORY-RULE-0003, as amended on 1 October 2026)
has them generated, never kept by hand: run it before a release, or whenever the lists should be
current; it changes only notes whose lists differ.

Part of the release-notes skill; release_notes.py calls it.
"""

from __future__ import annotations

import json
import re


def version_key(version: str) -> tuple:
    """Semantic versions in their order (1.10.0 after 1.9.0); anything else after them."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return (0, *map(int, m.groups())) if m else (1, str(version))


def named_by(repo, git, ref: str, trailer: re.Pattern, since: str | None = None) -> dict[str, list[tuple[str, str | None]]]:
    """slug -> [(short hash, package.json version at that commit)], oldest commit first."""
    args = ["log", "--reverse", "--format=%h%x1f%B%x1e", ref]
    if since:
        args.insert(2, "--since=" + since)
    out: dict[str, list[tuple[str, str | None]]] = {}
    for rec in git(repo, *args).split("\x1e"):
        if "\x1f" not in rec:
            continue
        h, body = rec.strip("\n").split("\x1f", 1)
        slugs = trailer.findall(body)
        if not slugs:
            continue
        try:
            version = json.loads(git(repo, "show", f"{h}:package.json")).get("version")
        except Exception:  # noqa: BLE001 - no package.json at that commit, or not JSON: no version
            version = None
        for slug in slugs:
            out.setdefault(slug, []).append((h, version))
    return out


def link(notes: list[dict], named: dict[str, list[tuple[str, str | None]]], write_note, dry_run: bool = False) -> list[str]:
    """Sets each note's `commits` and `versions` from `named`; returns a line per note changed."""
    report = []
    for note in notes:
        pairs = named.get(note["slug"], [])
        commits = list(dict.fromkeys(h for h, _ in pairs))
        versions = sorted({v for _, v in pairs if v}, key=version_key)
        front = note["front"]
        if (front.get("commits") or []) == commits and (front.get("versions") or []) == versions:
            continue
        front["commits"] = commits
        front["versions"] = versions
        report.append(f"{note['slug']}: {len(commits)} commit(s), versions {', '.join(versions) or 'none'}")
        if not dry_run:
            write_note(note["path"], front, note["body"])
    return report
