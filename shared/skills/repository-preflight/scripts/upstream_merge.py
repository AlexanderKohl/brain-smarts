#!/usr/bin/env python3
"""Follow upstream (SMART-RULE-0032, CONTRACT §13.2): merge `upstream/main` into the mechanics and
the skill library when the owner's setting `follow_upstream` is true.

Used by sync.py and the session-start hook (hooks.py); it has no command of its own. For each of
the mechanics and the library that has an `upstream` remote: fetch it; when `upstream/main` has
commits the shared checkout lacks, a session copy of its own begins at the shared checkout's commit
and `upstream/main` is merged in with the routine that merges `origin` (SMART-RULE-0034,
`session.merge_main`): never a rebase, reset or forced push; a conflicting generated file is
rebuilt, a conflicting hand-written file stops and leaves the merge in progress in the copy. The
merge is recorded, append-only, in the copy's `/memory/governance/upstream-merges.md` (upstream
commit, files changed, contract_version before and after, protected-governance files) and that is
committed; then `session.py finish` checks the copy with the preflight, pushes to `origin` (never
forced) and fast-forwards the shared checkout. Any stop keeps the copy and pushes nothing.

With `follow_upstream` false or absent nothing here runs. With it absent and an `upstream` present,
`b4_nudge` gives the SETUP B4 question to ask the owner once.
"""

from __future__ import annotations

import datetime
import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stdout
from pathlib import Path

HERE = Path(__file__).resolve().parent
REMOTE, BRANCH = "upstream", "main"
SETTINGS = Path("memory/skills/skill-exchange/config/settings.json")
RECORD = Path("governance/upstream-merges.md")          # in the memory repository
RECORD_PATH = "/memory/" + RECORD.as_posix()
COMMAND = "python shared/skills/repository-preflight/scripts/sync.py"
# The session-start hook merges only when at least this much of its time budget is left; a merge
# runs the preflight, which a fetch timeout cannot bound.
MERGE_SECONDS = 10.0
VERSION_RE = re.compile(r"^contract_version:\s*['\"]?([^'\"\s]+)", re.M)
B4_QUESTION = (
    "This brain has an upstream but no follow_upstream setting (SETUP.md step B4, SMART-RULE-0032). "
    "Ask the owner once: \"Follow the original automatically? 1. Yes: each session start merges the "
    "changes its maintainer has accepted, rules included, and tells you what came in (suggested). "
    "2. No: you are told what changed and decide each time.\" Record the answer as \"follow_upstream\": "
    "true or false in /memory/skills/skill-exchange/config/settings.json."
)
RECORD_HEAD = """---
id: memory-governance-upstream-merges
title: Upstream merges
type: register
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: {now}
updated: {now}
owner: brain-owner
---

# Upstream merges

Append-only (SMART-RULE-0032, CONTRACT §13.2). One entry per merge of `upstream/main` made by
`sync.py` while `follow_upstream` is on; each protected-governance file it lists came in under the
owner's standing acceptance. A merge can be reverted on its own from its upstream commit.
"""


def git(repo: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def settings(root: Path) -> dict:
    try:
        found = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def following(root: Path) -> bool:
    """True only when the owner's setting is the JSON value true; false, absent or unreadable is off."""
    return settings(root).get("follow_upstream") is True


def repositories(root: Path) -> list[tuple[str, Path]]:
    """The mechanics and the library, each when it is a repository with an `upstream` remote."""
    return [(name, repo) for name, repo in (("mechanics", root), ("library", root / "library"))
            if (repo / ".git").exists() and git(repo, "remote", "get-url", REMOTE).returncode == 0]


def b4_nudge(root: Path) -> str | None:
    """The SETUP B4 question, when an upstream exists, memory is present and the key is absent."""
    if not (root / "memory").is_dir() or "follow_upstream" in settings(root) or not repositories(root):
        return None
    return B4_QUESTION


def contract_version(repo: Path) -> str:
    for name in ("CONTRACT.md", "repository-manifest.json"):
        path = repo / name
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace")
            found = VERSION_RE.search(text) or re.search(r'"contract_version":\s*"([^"]+)"', text)
            if found:
                return found.group(1)
    return "none"


def said(out: io.StringIO) -> str:
    return " | ".join(line for line in out.getvalue().splitlines() if line and not line.startswith(
        ("session copy:", "work only there", "before the first write", "release notes", "  no release")))


def record(memory: Path, now: str, entry: str) -> str | None:
    """Append the entry to the record in a memory worktree and commit it; None, or why it failed."""
    path = memory / RECORD
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else RECORD_HEAD.format(now=now)
    text = re.sub(r"^updated: .*$", f"updated: {now}", text, count=1, flags=re.M)
    path.write_text(text.rstrip("\n") + "\n\n" + entry, encoding="utf-8")
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import session
    author = session.co_author(memory)
    message = "Record an upstream merge\n\nTool: sync.py\n" + (f"Co-Authored-By: {author}\n" if author else "")
    git(memory, "add", RECORD.as_posix())
    done = git(memory, "commit", "--quiet", "-m", message)
    return None if done.returncode == 0 else (done.stderr.strip().splitlines() or ["?"])[-1]


def merge(root: Path, name: str, repo: Path, fetch_timeout: float | None = None, fits=None) -> dict | None:
    """Merge `upstream/main` into one repository; a result in sync_one's shape plus `digest`, or
    None when upstream has nothing the shared checkout lacks. `fits` (the hook) says whether a merge
    still fits the time budget; when it does not, the merge is reported as pending with its command."""
    def result(state: str, detail: str, ok: bool, digest: list[str] | None = None) -> dict:
        return {"name": name, "path": str(repo), "state": state, "detail": detail, "ok": ok, "digest": digest or []}

    ref = f"{REMOTE}/{BRANCH}"
    try:
        fetched = git(repo, "fetch", "--quiet", REMOTE, BRANCH, timeout=fetch_timeout)
    except subprocess.TimeoutExpired:
        return result("upstream not merged", f"fetching {REMOTE} took longer than {fetch_timeout:.0f} s; "
                      f"run: {COMMAND}", False)
    if fetched.returncode:
        return result("upstream unreachable", f"could not fetch {REMOTE}: "
                      + (fetched.stderr.strip().splitlines() or ["?"])[-1], False)
    if git(repo, "merge-base", "--is-ancestor", ref, "HEAD").returncode == 0:
        return None
    if fits is not None and not fits():
        return result("upstream merge pending", f"not enough of the session-start time budget left; "
                      f"run: {COMMAND}", False)
    changed = [l for l in git(repo, "status", "--porcelain").stdout.splitlines() if l and not l.startswith("??")]
    if changed:
        return result("upstream not merged", f"{len(changed)} changed file(s) in the shared checkout; commit "
                      f"them, then run: {COMMAND}", False)
    if not (root / "memory" / ".git").exists():
        return result("upstream not merged", "no memory repository to record the merge in", False)
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import session  # here, not at the top: session.py imports sync, which imports this module
    from preflight_governance import is_protected
    upstream_commit = git(repo, "rev-parse", ref).stdout.strip()
    before = git(repo, "rev-parse", "HEAD").stdout.strip()
    copy_name = f"upstream-{name}-{datetime.datetime.now():%Y%m%d-%H%M%S}"
    folder = session.sessions_folder(root, None)
    copy = folder / copy_name
    out = io.StringIO()
    with redirect_stdout(out):
        started = session.cmd_start(root, copy_name, folder, {name: before})
    if started:
        return result("upstream merge stopped", "could not make a session copy: " + said(out), False)
    path = session.session_path(copy, name)
    version_before = contract_version(path)
    with redirect_stdout(out):
        merged, what = session.merge_main(copy, name, path, ref)
    if not merged:
        return result("upstream merge stopped", f"the shared checkout is unchanged; the merge stopped in {copy}: "
                      f"{what}", False)
    prefix = "" if name == "mechanics" else name + "/"
    files = [prefix + f for f in git(path, "diff", "--name-only", before, "HEAD").stdout.splitlines() if f]
    protected = [f for f in files if is_protected(f)]
    version_after = contract_version(path)
    now = datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    entry = (f"## {now} – {name}\n\n- upstream commit: {upstream_commit}\n"
             f"- contract_version: {version_before} to {version_after}\n"
             f"- files changed ({len(files)}): {', '.join(files) or 'none'}\n"
             f"- protected governance ({len(protected)}): {', '.join(protected) or 'none'}\n")
    failed = record(session.session_path(copy, "memory"), now, entry)
    if failed:
        return result("upstream merge stopped", f"merged in {copy} but the record could not be committed: {failed}", False)
    out = io.StringIO()
    with redirect_stdout(out):
        finished = session.cmd_finish(root, copy_name, folder, keep=False, preflight=True)
    if finished:
        return result("upstream merge stopped", f"merged in {copy}, nothing pushed by this step: " + said(out), False)
    summary = (f"merged {ref} {upstream_commit[:12]} (a merge in a session copy, checked, pushed, fast-forwarded): "
               f"{len(files)} file(s) changed, {len(protected)} protected governance"
               + (f" ({', '.join(protected)})" if protected else "")
               + f", contract_version {version_before} to {version_after}; recorded in {RECORD_PATH}")
    return result("upstream merged", summary, True, describe(root, repo, before, upstream_commit))


def describe(root: Path, repo: Path, before: str, after: str) -> list[str]:
    """skill-exchange's digest of what the merge brought; empty when it cannot be made."""
    scripts = str(HERE.parent.parent / "skill-exchange" / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    try:
        import skill_exchange
        brain = skill_exchange.Brain(str(root))
        changes = skill_exchange.merged_changes(brain, repo, git(repo, "merge-base", before, after).stdout.strip(), after)
        return skill_exchange.digest(brain, changes, merged=True) if changes else []
    except (Exception, SystemExit):  # noqa: BLE001 – the digest is a description; the merge stands
        return []


def merge_all(root: Path, deadline: float | None = None, clock=None) -> list[dict]:
    """Every upstream merge due, when following. With a deadline (the hook's, read with `clock`), the
    fetch is bounded by the time left and a merge that would not fit is reported as pending."""
    if not following(root):
        return []
    results = []
    for name, repo in repositories(root):
        if deadline is None:
            done = merge(root, name, repo)
        elif deadline - clock() <= 1:
            done = {"name": name, "path": str(repo), "state": "upstream merge pending",
                    "detail": f"the session-start time budget is used up; run: {COMMAND}", "ok": False, "digest": []}
        else:
            done = merge(root, name, repo, fetch_timeout=deadline - clock(),
                         fits=lambda: deadline - clock() >= MERGE_SECONDS)
        if done:
            results.append(done)
    return results
