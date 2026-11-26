#!/usr/bin/env python3
"""Weekly cleanup: what has piled up in the brain and its project repositories, and what clears it.

A report, never a gate: nothing here fails a commit or a push. It is run once a week, by the agent
that meets the repeating reminder which names it, and that agent clears what the report lists.
Each section says what was found and the command or the step that clears it; a section with
nothing to clear says so. The sections come in the order the work is done: the files every thread
reads first, then what threads left behind, then figures to watch.

    cleanup.py [--root <brain root>] [--no-fetch]      the report
    cleanup.py --fix branches                           also delete merged local session branches

Sections:
  long files          STATE.md and KNOWLEDGE.md over 28,000 characters, or within a tenth of it, in
                      the mechanics, the memory and each project repository's working branch
  stale handovers     a project whose handover entry is weeks older than its latest commits
  session copies      session copies idle for days: merged ones to remove, others left behind
  merged branches     session branches already merged into main, local and on the remote
  project worktrees   extra working copies and remote branches of a project that are merged
  project folders     a project folder behind its remote, with or without uncommitted files
  inbox               files waiting to be filed in the memory's inbox
  warnings            the preflight's warnings, counted by kind
  leftovers           compaction markers of threads long gone, and background jobs that failed
  commit reasons      the share of the week's commits whose body gives a reason
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session  # noqa: E402
import state  # noqa: E402

NEAR = state.LIMIT * 9 // 10      # a file this long is listed before it is over
STALE_DAYS = 14                    # a handover entry this much older than the latest commit is stale
IDLE_DAYS = 2                      # a session copy untouched this long is no longer a thread's working copy
MARKER_HOURS = 48                  # a compaction marker this old belongs to a thread that will not clear it
REASON_CHARACTERS = 40             # a body shorter than this says no more than its subject
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
WORD_DATE = re.compile(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})\b")
TRAILER = re.compile(r"^[A-Za-z][A-Za-z-]+: \S")
GENERATED = re.compile(r"^(Finish: |Merge )")
TOOL = "python shared/skills/repository-preflight/scripts/"


def git(repo: Path, *args: str, timeout: float | None = None) -> str:
    """A Git command's output, or nothing when it fails."""
    try:
        done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout if done.returncode == 0 else ""


def count(text: str) -> int:
    return len([line for line in text.splitlines() if line.strip()])


def projects(root: Path) -> list:
    """Each project repository checked out on this computer, once, with its working branch."""
    scripts = root / "shared" / "skills" / "tasks" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import task_stores
    seen, found = set(), []
    for pointer in task_stores.pointers(root):
        if pointer.checkout is None or not pointer.branch or pointer.checkout in seen:
            continue
        seen.add(pointer.checkout)
        found.append(pointer)
    return sorted(found, key=lambda p: p.repository)


def size_class(characters: int, limit: int = state.LIMIT) -> str | None:
    if characters > limit:
        return "over"
    return "near" if characters > limit * 9 // 10 else None


def long_files(root: Path, repos: list) -> list[str]:
    rows = []
    for path in state.state_files(root) + state.knowledge_files(root):
        size = len(state.read(path)[0])
        if size_class(size):
            rows.append((size, size_class(size), state.shown(root, path)))
    for repo in repos:
        for name in ("STATE.md", "KNOWLEDGE.md"):
            size = len(git(repo.checkout, "show", f"origin/{repo.branch}:brain/{name}"))
            if size_class(size):
                rows.append((size, size_class(size), f"{repo.repository}:brain/{name} on origin/{repo.branch}"))
    lines = [f"{size:>9,}  {kind:<4}  {where}" for size, kind, where in sorted(rows, reverse=True)]
    if lines:
        lines.append(f"clear with: {TOOL}state.py list <STATE.md>, then history --keep or --section; "
                     f"{TOOL}state.py subjects <KNOWLEDGE.md> --plan <plan.json>")
    return lines


def handover_date(text: str, today: datetime.date) -> datetime.date | None:
    """The newest date, not in the future, named at the top of a state file's handover section."""
    start = re.search(rf"^{re.escape(state.SECTION)}[ \t]*$", text, flags=re.M)
    if not start:
        return None
    top = text[start.end():start.end() + 1500]
    nxt = re.search(r"^## ", top, flags=re.M)
    top = top[:nxt.start()] if nxt else top
    found = []
    for year, month, day in ISO_DATE.findall(top):
        found.append((int(year), int(month), int(day)))
    for day, month, year in WORD_DATE.findall(top):
        found.append((int(year), MONTHS.index(month) + 1, int(day)))
    dates = []
    for year, month, day in found:
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            continue
        if date <= today:
            dates.append(date)
    return max(dates) if dates else None


def stale_handovers(repos: list, today: datetime.date) -> list[str]:
    lines = []
    for repo in repos:
        ref = f"origin/{repo.branch}"
        written = handover_date(git(repo.checkout, "show", f"{ref}:brain/STATE.md"), today)
        latest = git(repo.checkout, "log", "-1", "--format=%cs", ref).strip()
        week = git(repo.checkout, "rev-list", "--count", "--since=7.days", ref).strip()
        if written is None or not latest or not int(week or 0):
            continue
        behind = (datetime.date.fromisoformat(latest) - written).days
        if behind > STALE_DAYS:
            lines.append(f"{repo.repository}: the handover entry is of {written.isoformat()}, {behind} days before the "
                         f"latest commit on {ref} ({week} commits this week)")
    if lines:
        lines.append("clear with: the thread that works there writes its checkpoint (SMART-RULE-0019); "
                     f"{TOOL}state.py since <STATE.md> prints what Git recorded since")
    return lines


def session_copies(root: Path, now: float) -> list[str]:
    folder = session.sessions_folder(root, None)
    lines = []
    for copy in sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []:
        repos = [repo for repo in (copy, copy / "library", copy / "memory") if (repo / ".git").exists()]
        if not repos:
            continue
        ahead = sum(count("\n".join(row for row in git(repo, "cherry", session.base_ref(repo), "HEAD").splitlines()
                                    if row.startswith("+ "))) for repo in repos)
        dirty = sum(count(git(repo, "status", "--porcelain")) for repo in repos)
        last = max(int(git(repo, "log", "-1", "--format=%ct").strip() or 0) for repo in repos)
        idle = int((now - last) // 86400) if last else 0
        if idle < IDLE_DAYS:
            continue
        if not ahead and not dirty:
            lines.append(f"{copy.name}: all of it is on main, idle {idle} days; remove with: {TOOL}session.py finish {copy.name}")
        else:
            lines.append(f"{copy.name}: {ahead} commit(s) not on main and {dirty} uncommitted file(s), idle {idle} days; "
                         "look at what it holds before finishing or removing it")
    return lines


def merged_session_branches(repo: Path) -> tuple[list[str], int]:
    """Local session branches merged into main and checked out nowhere, and how many are merged on the remote."""
    base = session.base_ref(repo)
    merged = git(repo, "branch", "--merged", base, "--list", "session/*", "--format=%(refname:short)").split()
    used = {line.removeprefix("branch refs/heads/") for line in git(repo, "worktree", "list", "--porcelain").splitlines()
            if line.startswith("branch ")}
    remote = count(git(repo, "branch", "-r", "--merged", base, "--list", "origin/session/*"))
    return sorted(b for b in merged if b not in used), remote


def merged_branches(root: Path, fix: bool) -> list[str]:
    lines = []
    for name, repo in session.repositories(root):
        local, remote = merged_session_branches(repo)
        if not local and not remote:
            continue
        if fix and local:
            gone = [b for b in local if git(repo, "branch", "-d", b)]
            lines.append(f"{name}: deleted {len(gone)} of {len(local)} merged local session branches; {remote} merged on the remote remain")
        else:
            lines.append(f"{name}: {len(local)} local and {remote} remote session branches are merged into main")
    if lines and not fix:
        lines.append(f"clear with: {TOOL}cleanup.py --fix branches for the local ones (Git refuses an unmerged branch); "
                     "a remote one with: git push origin --delete <branch>")
    return lines


def project_worktrees(repos: list) -> list[str]:
    lines = []
    for repo in repos:
        ref = f"origin/{repo.branch}"
        blocks = git(repo.checkout, "worktree", "list", "--porcelain").strip().split("\n\n")[1:]
        done = []
        for block in blocks:
            path = Path(block.splitlines()[0].removeprefix("worktree "))
            if not path.is_dir():
                continue
            merged = subprocess.run(["git", "-C", str(path), "merge-base", "--is-ancestor", "HEAD", ref],
                                    capture_output=True).returncode == 0
            if merged and not count(git(path, "status", "--porcelain")):
                done.append(path.name)
        remote = [b.strip() for b in git(repo.checkout, "branch", "-r", "--merged", ref).splitlines()
                  if "->" not in b and b.strip() not in (ref, "origin/main", "origin/master")]
        if done or remote:
            names = ", ".join(done[:8]) + (" and more" if len(done) > 8 else "")
            lines.append(f"{repo.repository}: {len(blocks)} extra working copies, {len(done)} of them merged into {ref} and "
                         f"clean" + (f" ({names})" if done else "") + f"; {len(remote)} remote branches merged into {ref}")
    if lines:
        lines.append("clear with: git -C <repository> worktree remove <folder>, then git branch -d <branch>; a remote "
                     "branch by its author, with: git push origin --delete <branch>")
    return lines


def project_folders(repos: list) -> list[str]:
    lines = []
    for repo in repos:
        behind = int(git(repo.checkout, "rev-list", "--count", "HEAD..@{u}").strip() or 0)
        dirty = count(git(repo.checkout, "status", "--porcelain"))
        if behind and (dirty or behind > 20):
            branch = git(repo.checkout, "branch", "--show-current").strip() or "a detached commit"
            lines.append(f"{repo.repository}: {repo.checkout} is on {branch}, {behind} commits behind its remote, with "
                         f"{dirty} uncommitted file(s)")
    if lines:
        lines.append("clear with: commit or hand back what is uncommitted, then git pull --ff-only; a tool that reads "
                     "the folder (the task list, the preflight) reads old records until then")
    return lines


def inbox(root: Path) -> list[str]:
    folder = root / "memory" / "inbox"
    files = sorted(p.name for p in folder.iterdir() if p.is_file() and p.name not in ("README.md", ".gitkeep")) \
        if folder.is_dir() else []
    return [f"{len(files)} file(s) wait in /memory/inbox: " + ", ".join(files[:6]) + (" and more" if len(files) > 6 else ""),
            "clear with: file each one under CONTRACT section 11"] if files else []


def warning_kind(line: str) -> str:
    """What a preflight warning is about, without the file it names, so that warnings can be counted."""
    parts = line.removeprefix("WARNING: ").split(": ")
    while len(parts) > 1 and " " not in parts[0]:
        parts.pop(0)
    kind = re.sub(r"\S*/\S*", "<path>", parts[0])
    return re.sub(r"the claim of \S+ lapsed", "a claim lapsed", kind)


def warnings(root: Path) -> list[str]:
    done = subprocess.run([sys.executable, str(HERE / "preflight.py"), "--root", str(root)], capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    kinds: dict[str, list[str]] = {}
    for line in done.stdout.splitlines() + done.stderr.splitlines():
        if line.startswith("WARNING: "):
            kinds.setdefault(warning_kind(line), []).append(line.removeprefix("WARNING: "))
    lines = [f"{len(rows):>4}  {kind}  (for example: {rows[0][:150]})" for kind, rows in
             sorted(kinds.items(), key=lambda item: (-len(item[1]), item[0]))]
    errors = [line for line in (done.stdout + done.stderr).splitlines() if line.startswith("ERROR: ")]
    return [f"the preflight FAILS: {line[:200]}" for line in errors] + lines


def leftovers(root: Path, now: float) -> list[str]:
    lines = []
    markers = sorted((root / "temp" / "conductor" / "compacted").glob("*.json"), key=lambda p: p.stat().st_mtime)
    old = [p for p in markers if now - p.stat().st_mtime > MARKER_HOURS * 3600]
    if old:
        oldest = datetime.datetime.fromtimestamp(old[0].stat().st_mtime).strftime("%Y-%m-%d")
        lines.append(f"{len(old)} compaction marker(s) older than {MARKER_HOURS} hours in /temp/conductor/compacted, the "
                     f"oldest of {oldest}; each belongs to a thread that never cleared it. Clear with: "
                     f"python shared/skills/delegate-work/scripts/delegation.py checkpoint-done --session <id>, once "
                     "the thread is known to be closed")
    for record in sorted((root / "temp" / "background").glob("*.json")):
        try:
            job = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if job.get("state") == "failed":
            lines.append(f"background {job.get('kind', 'job')} of {job.get('name', record.stem)} failed on "
                         f"{str(job.get('finished', '?'))[:10]}; its log is {job.get('log', record.with_suffix('.log'))}")
    return lines


def gives_reason(message: str) -> bool | None:
    """Whether a commit message's body says more than its subject; None for a commit a script wrote."""
    rows = message.strip().splitlines()
    if not rows or GENERATED.match(rows[0]):
        return None
    body = " ".join(row.strip() for row in rows[1:] if row.strip() and not TRAILER.match(row))
    return len(body) >= REASON_CHARACTERS


def commit_reasons(root: Path, repos: list, days: int = 7) -> list[str]:
    places = [(name, repo, session.base_ref(repo)) for name, repo in session.repositories(root)]
    places += [(repo.repository, repo.checkout, f"origin/{repo.branch}") for repo in repos]
    lines = []
    for name, repo, ref in places:
        found = [gives_reason(m) for m in git(repo, "log", "--no-merges", f"--since={days}.days", "--format=%B%x01", ref).split("\x01")
                 if m.strip()]
        hand = [f for f in found if f is not None]
        if hand:
            lines.append(f"{name}: {sum(hand)} of {len(hand)} hand-written commits give a reason ({100 * sum(hand) // len(hand)}%)")
    return lines


def report(root: Path, fetch: bool, fix: set[str]) -> int:
    repos = projects(root)
    if fetch:
        for repo in [r for _, r in session.repositories(root)] + [p.checkout for p in repos]:
            git(repo, "fetch", "--quiet", "--prune", "origin", timeout=90)
    now = datetime.datetime.now()
    sections = [
        (f"Long state and knowledge files (over {state.LIMIT:,} characters, near from {NEAR:,})", long_files(root, repos)),
        ("Stale handover entries in project repositories", stale_handovers(repos, now.date())),
        (f"Session copies idle {IDLE_DAYS} days or more", session_copies(root, now.timestamp())),
        ("Session branches already merged", merged_branches(root, "branches" in fix)),
        ("Project working copies and branches already merged", project_worktrees(repos)),
        ("Project folders behind their remote", project_folders(repos)),
        ("Inbox", inbox(root)),
        ("Preflight warnings, by kind", warnings(root)),
        ("Leftovers", leftovers(root, now.timestamp())),
        ("Commits of the last 7 days that give a reason (a figure to watch, nothing to clear)", commit_reasons(root, repos)),
    ]
    print(f"Weekly cleanup of {now.strftime('%Y-%m-%d %H:%M')}: a report; nothing here fails a commit.")
    for title, lines in sections:
        print(f"\n## {title}\n")
        print("\n".join(lines) if lines else "nothing")
    busy = sum(1 for _, lines in sections[:-1] if lines)
    print(f"\n{busy} of {len(sections) - 1} sections have something to clear.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=HERE.parents[3])
    parser.add_argument("--no-fetch", action="store_true", help="read what was last fetched instead of fetching every repository")
    parser.add_argument("--fix", action="append", default=[], choices=["branches"],
                        help="also clear what is safe to clear: merged local session branches")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    return report(args.root.resolve(), not args.no_fetch, set(args.fix))


if __name__ == "__main__":
    sys.exit(main())
