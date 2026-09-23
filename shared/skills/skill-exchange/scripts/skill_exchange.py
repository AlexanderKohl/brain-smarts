"""Skill exchange: the mechanical, read-mostly parts of moving skills between brains.

Proposed under `PROPOSAL-skill-exchange` (`/governance/proposals/skill-exchange.md`); see
`/shared/skills/skill-exchange/SKILL.md`. Nothing here pushes, opens a pull request, merges or
installs: those are owner decisions the agent carries out by hand after a yes.

Commands (run from the brain root; every command takes `--root`):

    due                      exit 0 when an upstream check is due, 1 when not (cheap, no network)
    upstream [--no-fetch]    what changed upstream since the last report, grouped for the owner
    scrub <path>...          personal-data check before anything leaves memory or goes upstream
    candidate add|list|mark  promotion candidates noticed while working
    record-install           write provenance for a skill installed from another brain
    verify-installs          say which installed skills no longer match their recorded source

State and owner settings live in memory, never in the mechanics repository:

    /memory/skills/skill-exchange/config/settings.json   cadence and suggestion settings
    /memory/skills/skill-exchange/state.json             last check and what was already reported
    /memory/skills/skill-exchange/candidates.json        promotion candidates
    /memory/skills/skill-exchange/scrub-allow.txt        strings the scrub check may accept
    /memory/skills/installed.json                        provenance of installed skills
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SETTINGS_DEFAULTS = {
    "check_every_days": 7,
    "max_items_per_digest": 5,
    "remote": "upstream",
    "branch": "main",
    "suggestions": "checkpoint",
}

# ------------------------------------------------------------------ locations


def find_brain_root(start: str | None = None) -> Path:
    for candidate in ([Path(start)] if start else [Path.cwd(), Path(__file__).resolve().parent]):
        here = candidate.resolve()
        for folder in (here, *here.parents):
            if (folder / "CONTRACT.md").is_file():
                return folder
    raise SystemExit("CONTRACT.md not found; pass --root")


class Brain:
    def __init__(self, root: str | None = None, now: str | None = None):
        self.root = find_brain_root(root)
        self.memory = self.root / "memory"
        self.home = self.memory / "skills" / "skill-exchange"
        self.now = datetime.datetime.fromisoformat(now) if now else \
            datetime.datetime.now().astimezone().replace(microsecond=0)

    def settings(self) -> dict:
        return dict(SETTINGS_DEFAULTS, **read_json(self.home / "config" / "settings.json", {}))

    def profile(self) -> dict:
        return front_matter(self.memory / "OWNER.md")

    def active_skills(self) -> list:
        return self.profile().get("active_skills", []) or []


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


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
            value = found.group(2).strip().strip('"')
            out[key] = [] if value in ("", "[]") else value
    return out


def git(root: Path, *args: str, check: bool = True) -> str:
    out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    if check and out.returncode:
        raise SystemExit("git " + " ".join(args) + " failed: " + out.stderr.strip())
    return out.stdout.strip() if out.returncode == 0 else ""


# ------------------------------------------------------------------ upstream


def due(brain: Brain) -> tuple[bool, str]:
    settings = brain.settings()
    state = read_json(brain.home / "state.json", {})
    last = state.get("last_checked")
    if not last:
        return True, "never checked"
    age = brain.now - datetime.datetime.fromisoformat(last)
    days = settings["check_every_days"]
    if age.total_seconds() >= days * 86400:
        return True, "last checked " + last
    return False, "last checked " + last + "; next after " + str(days) + " day(s)"


def always_on(brain: Brain) -> set:
    """Skills the rules or contract name by path: active for every owner."""
    names: set = set()
    for name in ("RULES.md", "CONTRACT.md"):
        try:
            text = (brain.root / name).read_text(encoding="utf-8")
        except OSError:
            continue
        names.update(re.findall(r"/shared/skills/([a-z0-9-]+)/", text))
    return names


def upstream_changes(brain: Brain, fetch: bool = True) -> dict:
    """What upstream has that this brain does not, grouped for the owner."""
    settings = brain.settings()
    remote, branch = settings["remote"], settings["branch"]
    if remote not in git(brain.root, "remote").split():
        raise SystemExit("no remote named " + remote + " - see /SETUP.md step B3")
    if fetch:
        git(brain.root, "fetch", "-q", remote)
    ref = remote + "/" + branch
    head = git(brain.root, "rev-parse", ref)
    base = git(brain.root, "merge-base", "HEAD", ref)
    commits = git(brain.root, "log", "--format=%h %s", base + ".." + ref).splitlines()
    changed = git(brain.root, "diff", "--name-status", base, ref).splitlines()
    active = set(brain.active_skills())
    required = always_on(brain)
    local = {p.name for p in (brain.root / "shared" / "skills").iterdir() if p.is_dir()} \
        if (brain.root / "shared" / "skills").is_dir() else set()
    skills: dict = {}
    governance: list = []
    other = 0
    for line in changed:
        parts = line.split("\t")
        path = parts[-1]
        found = re.match(r"shared/skills/([^/]+)/", path)
        if found:
            name = found.group(1)
            skills.setdefault(name, 0)
            skills[name] += 1
        elif path in ("CONTRACT.md", "RULES.md", "BOOTSTRAP.md", "AGENTS.md") or path.startswith("governance/"):
            governance.append(path)
        else:
            other += 1
    grouped = {"active": [], "always_on": [], "new": [], "other": []}
    for name in sorted(skills):
        if name in active:
            grouped["active"].append(name)
        elif name in required:
            grouped["always_on"].append(name)
        elif name not in local:
            grouped["new"].append(name)
        else:
            grouped["other"].append(name)
    return {"ref": ref, "upstream_commit": head, "commits": commits, "skills": grouped,
            "governance": sorted(set(governance)), "other_files": other}


def digest(brain: Brain, changes: dict) -> list:
    """The lines to show the owner: only what was not reported before, capped, numbered."""
    state = read_json(brain.home / "state.json", {})
    if state.get("last_reported_commit") == changes["upstream_commit"]:
        return []
    if not changes["commits"]:
        return []
    cap = int(brain.settings()["max_items_per_digest"])
    items: list = []
    for name in changes["skills"]["active"]:
        items.append("changed skill you use: " + name)
    for name in changes["skills"]["always_on"]:
        items.append("changed skill every brain uses: " + name)
    for path in changes["governance"]:
        items.append("governance changed: " + path + " (needs your acceptance before it applies)")
    for name in changes["skills"]["new"]:
        items.append("new skill offered: " + name)
    lines = ["Upstream has " + str(len(changes["commits"])) + " new commit(s) on " + changes["ref"] + "."]
    for n, item in enumerate(items[:cap], start=1):
        lines.append(str(n) + ". " + item)
    rest = max(0, len(items) - cap) + len(changes["skills"]["other"])
    if rest > 0:
        lines.append("   and " + str(rest) + " other change(s) to skills you have not switched on")
    return lines


def mark_reported(brain: Brain, changes: dict) -> None:
    state = read_json(brain.home / "state.json", {})
    state["last_checked"] = brain.now.isoformat()
    if changes.get("commits"):
        state["last_reported_commit"] = changes["upstream_commit"]
    write_json(brain.home / "state.json", state)


# ------------------------------------------------------------------ scrub


def personal_data_module(brain: Brain):
    """The validator's personal-data check: one implementation (SMART-RULE-0008, SMART-RULE-0018)."""
    scripts = Path(__file__).resolve().parents[2] / "repository-preflight" / "scripts"  # a core sibling
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import personal_data
    return personal_data


def scrub(brain: Brain, paths: list) -> list:
    """Every personal-data hit in the given files or folders, as (file, line, kind, text).
    Generic exemptions come from the validator; `scrub-allow.txt` in memory may add exact strings
    for this command only, each justified in the commit."""
    pd = personal_data_module(brain)
    allow_file = brain.home / "scrub-allow.txt"
    allow = {t.strip() for t in allow_file.read_text(encoding="utf-8").splitlines() if t.strip()}         if allow_file.is_file() else set()
    _, values, _ = pd.load_exemptions()
    files: list = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.is_file() and ".git" not in f.parts)
        elif p.is_file():
            files.append(p)
    return pd.scan(files, pd.owner_terms(brain.root), allowed=values | allow)


# ------------------------------------------------------------------ candidates


def candidates_path(brain: Brain) -> Path:
    return brain.home / "candidates.json"


def candidate_add(brain: Brain, path: str, reason: str) -> dict:
    data = read_json(candidates_path(brain), {"candidates": []})
    for c in data["candidates"]:
        if c["path"] == path:
            c["evidence"].append({"at": brain.now.isoformat(), "reason": reason})
            write_json(candidates_path(brain), data)
            return c
    entry = {"path": path, "status": "noticed", "noticed_at": brain.now.isoformat(),
             "evidence": [{"at": brain.now.isoformat(), "reason": reason}]}
    data["candidates"].append(entry)
    write_json(candidates_path(brain), data)
    return entry


def candidates_to_suggest(brain: Brain) -> list:
    """Noticed and not yet suggested, or declined and seen again with new evidence since."""
    out = []
    for c in read_json(candidates_path(brain), {"candidates": []})["candidates"]:
        if c["status"] == "noticed":
            out.append(c)
        elif c["status"] == "declined":
            since = [e for e in c["evidence"] if e["at"] > c.get("decided_at", "")]
            if since:
                out.append(c)
    return sorted(out, key=lambda c: c["path"])


def candidate_mark(brain: Brain, path: str, status: str, note: str = "") -> dict:
    data = read_json(candidates_path(brain), {"candidates": []})
    for c in data["candidates"]:
        if c["path"] == path:
            c["status"] = status
            c["decided_at" if status in ("declined", "promoted") else "suggested_at"] = brain.now.isoformat()
            if note:
                c["note"] = note
            write_json(candidates_path(brain), data)
            return c
    raise SystemExit("no candidate " + path)


# ------------------------------------------------------------------ provenance


def tree_of(repo: Path, commit: str, path: str) -> str:
    return git(repo, "rev-parse", commit + ":" + path)


def record_install(brain: Brain, skill: str, source: str, commit: str, path: str | None = None) -> dict:
    path = path or "shared/skills/" + skill
    local_tree = tree_of(brain.root, "HEAD", path) if git(brain.root, "rev-parse", "--verify", "--quiet",
                                                          "HEAD:" + path, check=False) else ""
    record_file = brain.memory / "skills" / "installed.json"
    data = read_json(record_file, {"installed": []})
    entry = {"skill": skill, "path": path, "source_repo": source, "source_commit": commit,
             "tree": local_tree, "installed_at": brain.now.isoformat()}
    data["installed"] = sorted([e for e in data["installed"] if e["skill"] != skill] + [entry],
                               key=lambda e: e["skill"])
    write_json(record_file, data)
    return entry


def verify_installs(brain: Brain) -> list:
    out = []
    for e in read_json(brain.memory / "skills" / "installed.json", {"installed": []})["installed"]:
        now = git(brain.root, "rev-parse", "HEAD:" + e["path"], check=False)
        if not now:
            out.append((e["skill"], "missing"))
        elif e.get("tree") and now != e["tree"]:
            out.append((e["skill"], "changed since install"))
        else:
            out.append((e["skill"], "matches source " + e["source_commit"][:12]))
    return out


# ------------------------------------------------------------------ command line


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root")
    p.add_argument("--now", help=argparse.SUPPRESS)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("due")
    up = sub.add_parser("upstream")
    up.add_argument("--no-fetch", action="store_true")
    up.add_argument("--json", action="store_true")
    up.add_argument("--dry-run", action="store_true", help="do not record the report as delivered")
    sc = sub.add_parser("scrub")
    sc.add_argument("paths", nargs="+")
    ca = sub.add_parser("candidate")
    ca_sub = ca.add_subparsers(dest="action", required=True)
    a = ca_sub.add_parser("add")
    a.add_argument("path")
    a.add_argument("--reason", required=True)
    ca_sub.add_parser("list")
    m = ca_sub.add_parser("mark")
    m.add_argument("path")
    m.add_argument("status", choices=["declined", "promoted", "suggested"])
    m.add_argument("--note", default="")
    ri = sub.add_parser("record-install")
    ri.add_argument("--skill", required=True)
    ri.add_argument("--source", required=True, help="the repository the skill came from")
    ri.add_argument("--commit", required=True, help="the full commit it was taken from")
    ri.add_argument("--path")
    sub.add_parser("verify-installs")
    args = p.parse_args(argv)
    brain = Brain(args.root, args.now)

    if args.cmd == "due":
        yes, why = due(brain)
        print(("due: " if yes else "not due: ") + why)
        return 0 if yes else 1
    if args.cmd == "upstream":
        changes = upstream_changes(brain, fetch=not args.no_fetch)
        if args.json:
            print(json.dumps(changes, indent=2))
        else:
            lines = digest(brain, changes)
            print("\n".join(lines) if lines else "Nothing new upstream since the last report.")
        if not args.dry_run:
            mark_reported(brain, changes)
        return 0
    if args.cmd == "scrub":
        hits = scrub(brain, args.paths)
        for f, n, kind, value in hits:
            print(f + ":" + str(n) + ": " + kind + ": " + value)
        print(str(len(hits)) + " hit(s)")
        return 1 if hits else 0
    if args.cmd == "candidate":
        if args.action == "add":
            print(json.dumps(candidate_add(brain, args.path, args.reason), indent=2))
        elif args.action == "list":
            for c in candidates_to_suggest(brain):
                print(c["path"] + "  (" + c["status"] + ", " + str(len(c["evidence"])) + " observation(s))")
        else:
            print(json.dumps(candidate_mark(brain, args.path, args.status, args.note), indent=2))
        return 0
    if args.cmd == "record-install":
        print(json.dumps(record_install(brain, args.skill, args.source, args.commit, args.path), indent=2))
        return 0
    if args.cmd == "verify-installs":
        for skill, verdict in verify_installs(brain):
            print(skill + ": " + verdict)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
