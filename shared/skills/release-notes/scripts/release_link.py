"""`link`: a note's commits and versions, read from the commits that name it with a
`Release-note: <slug>` trailer. The owner's rule (MEMORY-RULE-0003, as amended on 1 October 2026)
has them generated, never kept by hand: run it before a release, or whenever the lists should be
current; it changes only notes whose lists differ.

Part of the release-notes skill; release_notes.py calls it.
"""

from __future__ import annotations

import json
import re
import subprocess


def version_key(version: str) -> tuple:
    """Semantic versions in their order (1.10.0 after 1.9.0); anything else after them."""
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(version or ""))
    return (0, *map(int, m.groups())) if m else (1, str(version))


def named_by(repo, git, ref: str, trailer: re.Pattern, since: str | None = None) -> dict[str, list[tuple[str, str | None]]]:
    """slug -> [(short hash, package.json version at that commit)], oldest commit first."""
    args = ["log", "--reverse", "--format=%h%x1f%B%x1e", ref]
    if since:
        args.insert(2, "--since=" + since)
    naming: list[tuple[str, list[str]]] = []
    for rec in git(repo, *args).split("\x1e"):
        if "\x1f" not in rec:
            continue
        h, body = rec.strip("\n").split("\x1f", 1)
        slugs = trailer.findall(body)
        if slugs:
            naming.append((h, slugs))
    versions = versions_at(repo, git, [h for h, _ in naming])
    out: dict[str, list[tuple[str, str | None]]] = {}
    for h, slugs in naming:
        for slug in slugs:
            out.setdefault(slug, []).append((h, versions[h]))
    return out


def version_in(text: str) -> str | None:
    """The `version` of a package.json's text; None when it is not JSON or holds none."""
    try:
        return json.loads(text).get("version")
    except Exception:  # noqa: BLE001 - not JSON, or not an object: no version
        return None


def versions_at(repo, git, hashes: list[str]) -> dict[str, str | None]:
    """commit -> the version in its package.json, None when it has none. One `git cat-file
    --batch` answers for every commit: a `git show` per commit took 90 seconds on a project with
    1,400 commits that name a note. When the batch cannot be read, each commit is asked on its own."""
    try:
        done = subprocess.run(["git", "-C", str(repo), "cat-file", "--batch"], capture_output=True,
                              input="".join(f"{h}:package.json\n" for h in hashes).encode("utf-8"))
        if done.returncode != 0:
            raise OSError(done.stderr.decode("utf-8", "replace"))
        found: dict[str, str | None] = {}
        data, at = done.stdout, 0
        for h in hashes:
            end = data.index(b"\n", at)
            header, at = data[at:end].split(b" "), end + 1
            if len(header) != 3 or not header[2].isdigit():     # "<name> missing", or ambiguous
                found[h] = None
                continue
            content, at = data[at:at + int(header[2])], at + int(header[2]) + 1
            try:
                found[h] = version_in(content.decode("utf-8")) if header[1] == b"blob" else None
            except UnicodeDecodeError:
                found[h] = None
        return found
    except (OSError, ValueError):
        found = {}
        for h in hashes:
            try:
                found[h] = version_in(git(repo, "show", f"{h}:package.json"))
            except Exception:  # noqa: BLE001 - no package.json at that commit: no version
                found[h] = None
        return found


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
