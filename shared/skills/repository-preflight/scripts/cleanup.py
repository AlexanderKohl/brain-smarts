#!/usr/bin/env python3
"""Cleanup: what threads leave behind is cleared when it is no longer needed, and a weekly report
lists the rest.

Two uses. `tidy` runs at the end of every `session.py finish`, so leftovers do not pile up: it removes
only what is certainly no longer needed and loses nothing. The report is run once a week, by the
agent that meets the repeating reminder which names it, and that agent clears what it lists. Neither
is a gate: nothing here fails a commit or a push.

    cleanup.py [--root <brain root>] [--no-fetch]      the weekly report
    cleanup.py --fix all                                the report, clearing what `tidy` clears
    cleanup.py --fix branches|copies|markers|worktrees|remote-branches     one kind only
    cleanup.py --fix remote-branches --older-than 14    only branches whose last commit is that old

What `tidy` clears, and why each is safe:
  session copies      a copy whose thread the user archived, with all its work on main and no
                      uncommitted file (the thread that started a copy is noted by `session.py start`)
  markers             the compaction marker of an archived thread
  project worktrees   an extra working copy of a project repository that is merged into the working
                      branch, has no uncommitted file, and whose HEAD has not moved for 6 hours;
                      links inside it (a shared `node_modules`) are unlinked first, never followed
  remote branches     a remote branch merged into the working branch whose last commit this
                      computer's Git user wrote (by e-mail address or name), and whose name has a
                      namespace such as `feature/`; never the working, default or a protected branch
  session branches    a local session branch merged into main that no working copy uses

Report sections, in the order the work is done: long state and knowledge files, stale handover
entries, session copies, merged session branches, project working copies, remote branches, project
folders behind their remote, the inbox, threads to archive, the preflight's warnings by kind,
leftovers, and the share of the week's commits whose body gives a reason.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import session  # noqa: E402
import state  # noqa: E402
import threads  # noqa: E402

NEAR = state.LIMIT * 9 // 10      # a file this long is listed before it is over
STALE_DAYS = 14                    # a handover entry this much older than the latest commit is stale
IDLE_DAYS = 2                      # a session copy untouched this long is listed in the report
WORKTREE_HOURS = 6                 # a merged, clean working copy whose HEAD rested this long is done; as a task claim lasts
ARCHIVE_DAYS = 7                   # a thread idle this long is put to the owner to archive
REASON_CHARACTERS = 40             # a body shorter than this says no more than its subject
PROTECTED = frozenset({"main", "master", "testing", "staging", "production", "develop", "dev"})
FIXES = ("branches", "copies", "markers", "worktrees", "remote-branches")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
WORD_DATE = re.compile(r"\b(\d{1,2}) (" + "|".join(MONTHS) + r") (\d{4})\b")
TRAILER = re.compile(r"^[A-Za-z][A-Za-z-]+: \S")
GENERATED = re.compile(r"^(Finish: |Merge )")
TOOL = "python shared/skills/repository-preflight/scripts/"


def run(repo: Path, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None


def git(repo: Path, *args: str, timeout: float | None = None) -> str:
    """A Git command's output, or nothing when it fails."""
    done = run(repo, *args, timeout=timeout)
    return done.stdout if done is not None and done.returncode == 0 else ""


def ok(repo: Path, *args: str, timeout: float | None = None) -> bool:
    done = run(repo, *args, timeout=timeout)
    return done is not None and done.returncode == 0


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


# ---------------------------------------------------------------- long files and handover entries

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
    found = [(int(y), int(m), int(d)) for y, m, d in ISO_DATE.findall(top)]
    found += [(int(y), MONTHS.index(m) + 1, int(d)) for d, m, y in WORD_DATE.findall(top)]
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


# ---------------------------------------------------------------- session copies and their branches

def copy_state(copy: Path) -> tuple[int, int, int]:
    """Commits whose change is not on main, uncommitted files, and the time of the last commit."""
    repos = [repo for repo in (copy, copy / "library", copy / "memory") if (repo / ".git").exists()]
    if not repos:
        return -1, -1, 0
    ahead = sum(len([row for row in git(repo, "cherry", session.base_ref(repo), "HEAD").splitlines() if row.startswith("+ ")])
                for repo in repos)
    dirty = sum(count(git(repo, "status", "--porcelain")) for repo in repos)
    last = max(int(git(repo, "log", "-1", "--format=%ct").strip() or 0) for repo in repos)
    return ahead, dirty, last


def copies(root: Path) -> list[Path]:
    folder = session.sessions_folder(root, None)
    return sorted(p for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def thread_word(root: Path, copy: Path, known: dict | None) -> str:
    thread = threads.copy_thread(root, copy.name)
    if thread is None or known is None or thread not in known:
        return "its thread is not known"
    return "its thread is archived" if known[thread].archived else "its thread is live"


def tidy_copies(root: Path, known: dict | None) -> list[str]:
    """Remove each session copy whose thread is archived, when all its work is on main and nothing is uncommitted."""
    lines = []
    for copy in copies(root):
        thread = threads.copy_thread(root, copy.name)
        if known is None or thread is None or thread not in known or not known[thread].archived:
            continue
        ahead, dirty, _ = copy_state(copy)
        if ahead or dirty:
            continue
        gone = True
        for name, repo in reversed(session.repositories(root)):        # nested worktrees before the mechanics
            path = session.session_path(copy, name)
            if path.exists() and not ok(repo, "worktree", "remove", str(path)):
                gone = False
                continue
            run(repo, "branch", "-D", f"session/{copy.name}")           # safe: no change of its own, checked above
        if gone:
            for leftover in (copy, threads.record_path(root, copy.name)):
                try:
                    leftover.rmdir() if leftover.is_dir() else leftover.unlink()
                except OSError:
                    pass
            lines.append(f"session copy {copy.name} removed: its thread is archived and all its work is on main")
    return lines


def session_copies(root: Path, now: float, known: dict | None) -> list[str]:
    lines = []
    for copy in copies(root):
        ahead, dirty, last = copy_state(copy)
        if ahead < 0:
            continue
        idle = int((now - last) // 86400) if last else 0
        word = thread_word(root, copy, known)
        if idle < IDLE_DAYS and word != "its thread is archived":
            continue
        if not ahead and not dirty:
            lines.append(f"{copy.name}: all of it is on main, idle {idle} days, {word}; remove with: {TOOL}session.py finish {copy.name}")
        else:
            lines.append(f"{copy.name}: {ahead} commit(s) not on main and {dirty} uncommitted file(s), idle {idle} days, {word}; "
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
        local, _ = merged_session_branches(repo)
        if not local:
            continue
        if fix:
            gone = [b for b in local if ok(repo, "branch", "-d", b)]
            if gone:
                lines.append(f"{name}: {len(gone)} merged local session branch(es) deleted")
            kept = len(local) - len(gone)
            if kept:
                lines.append(f"{name}: {kept} merged local session branch(es) kept, because Git refused: each holds commits "
                             "its own remote branch lacks")
        else:
            lines.append(f"{name}: {len(local)} local session branch(es) are merged into main")
    if lines and not fix:
        lines.append(f"clear with: {TOOL}cleanup.py --fix branches (Git refuses an unmerged branch)")
    return lines


# ---------------------------------------------------------------- project working copies

def head_moved(path: Path) -> float:
    """When the working copy's HEAD last moved: a commit, a checkout, a merge or its making."""
    gitdir = git(path, "rev-parse", "--absolute-git-dir").strip()
    for name in ("logs/HEAD", "HEAD"):
        file = Path(gitdir) / name if gitdir else None
        if file is not None and file.is_file():
            return file.stat().st_mtime
    return 0.0


def is_link(path: Path) -> bool:
    """A symbolic link or a Windows junction: a folder that is really somewhere else."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def links_inside(folder: Path) -> list[Path]:
    """Every link under a folder, found without following any, so that removing the folder cannot
    reach through one into what it points at."""
    found, stack = [], [folder]
    while stack:
        here = stack.pop()
        try:
            entries = list(os.scandir(here))
        except OSError:
            continue
        for entry in entries:
            path = Path(entry.path)
            if is_link(path):
                found.append(path)
            elif entry.is_dir(follow_symlinks=False) and entry.name != ".git":
                stack.append(path)
    return found


def unlink(path: Path) -> bool:
    try:
        os.rmdir(path) if path.is_dir() else os.unlink(path)
    except OSError:
        try:
            os.unlink(path)
        except OSError:
            return False
    return True


def worktrees(checkout: Path) -> list[tuple[Path, str, bool]]:
    """The extra working copies of a repository: folder, branch ('' when detached), locked."""
    found = []
    for block in git(checkout, "worktree", "list", "--porcelain").strip().split("\n\n")[1:]:
        rows = block.splitlines()
        path = Path(rows[0].removeprefix("worktree "))
        branch = next((r.removeprefix("branch refs/heads/") for r in rows if r.startswith("branch ")), "")
        found.append((path, branch, any(r.startswith("locked") for r in rows)))
    return found


def done_worktrees(checkout: Path, ref: str, now: float, hours: float = WORKTREE_HOURS) -> list[tuple[Path, str]]:
    """Extra working copies that are merged into `ref`, clean, unlocked and at rest for `hours`."""
    done = []
    for path, branch, locked in worktrees(checkout):
        if locked or not path.is_dir() or not ok(path, "merge-base", "--is-ancestor", "HEAD", ref):
            continue
        if count(git(path, "status", "--porcelain")) or now - head_moved(path) < hours * 3600:
            continue
        done.append((path, branch))
    return done


def remove_worktree(checkout: Path, path: Path, branch: str) -> bool:
    for link in links_inside(path):
        if not unlink(link):
            return False
    if not ok(checkout, "worktree", "remove", str(path)):
        return False
    if branch:
        run(checkout, "branch", "-d", branch)                           # Git refuses an unmerged branch
    return True


def project_worktrees(repos: list, now: float, fix: bool) -> list[str]:
    lines = []
    for repo in repos:
        ref = f"origin/{repo.branch}"
        extra = worktrees(repo.checkout)
        done = done_worktrees(repo.checkout, ref, now)
        if fix:
            gone = [path.name for path, branch in done if remove_worktree(repo.checkout, path, branch)]
            if gone:
                lines.append(f"{repo.repository}: {len(gone)} merged working cop(ies) removed: " + ", ".join(gone[:10])
                             + (" and more" if len(gone) > 10 else ""))
        elif done:
            names = ", ".join(path.name for path, _ in done[:8]) + (" and more" if len(done) > 8 else "")
            lines.append(f"{repo.repository}: {len(done)} of {len(extra)} extra working copies are merged into {ref}, clean "
                         f"and at rest for {WORKTREE_HOURS} hours ({names})")
    if lines and not fix:
        lines.append(f"clear with: {TOOL}cleanup.py --fix worktrees; every finish of a session does the same")
    return lines


# ---------------------------------------------------------------- remote branches

def merged_remote(checkout: Path, ref: str, now: float, prefix: str = "", older_than: float = 0) -> tuple[list[str], int]:
    """Remote branches merged into `ref`: those whose last commit this computer's Git user wrote (and
    is at least `older_than` days old), by name without `origin/`; and how many others there are."""
    me = {git(checkout, "config", "user.email").strip().lower(), git(checkout, "config", "user.name").strip().lower()} - {""}
    default = git(checkout, "symbolic-ref", "--short", "refs/remotes/origin/HEAD").strip().removeprefix("origin/")
    keep = PROTECTED | {ref.removeprefix("origin/"), default}
    rows = git(checkout, "for-each-ref", "--merged", ref,
               "--format=%(refname:short)%09%(authoremail)%09%(authorname)%09%(committerdate:unix)", "refs/remotes/origin/" + prefix)
    own, others = [], 0
    for row in rows.splitlines():
        name, email, author, when = (row.split("\t") + ["", "", ""])[:4]
        name = name.removeprefix("origin/")
        if not name or name in ("origin", "HEAD") or name in keep:
            continue
        mine = email.strip("<> ").lower() in me or author.strip().lower() in me
        # A branch without a namespace (`feature/...`) may be one a deployment follows: it is counted, never deleted here.
        if mine and "/" in name and now - int(when or 0) >= older_than * 86400:
            own.append(name)
        else:
            others += 1
    return sorted(own), others


def delete_remote(checkout: Path, names: list[str]) -> int:
    gone = 0
    for start in range(0, len(names), 40):
        batch = names[start:start + 40]
        if ok(checkout, "push", "--quiet", "origin", "--delete", *batch, timeout=180):
            gone += len(batch)
        else:
            gone += sum(1 for name in batch if ok(checkout, "push", "--quiet", "origin", "--delete", name, timeout=60))
    if gone:
        run(checkout, "fetch", "--quiet", "--prune", "origin", timeout=120)
    return gone


def remote_branches(root: Path, repos: list, now: float, fix: bool, older_than: float = 0) -> list[str]:
    places = [(name, repo, session.base_ref(repo), "session/") for name, repo in session.repositories(root)]
    places += [(repo.repository, repo.checkout, f"origin/{repo.branch}", "") for repo in repos]
    lines = []
    for name, checkout, ref, prefix in places:
        own, others = merged_remote(checkout, ref, now, prefix, older_than)
        if fix and own:
            lines.append(f"{name}: {delete_remote(checkout, own)} of {len(own)} merged remote branch(es) of this computer's Git "
                         f"user deleted; {others} of other authors left to them")
        elif own or others:
            lines.append(f"{name}: {len(own)} remote branch(es) merged into {ref} are this computer's Git user's, "
                         f"{others} are other authors'")
    if lines and not fix:
        lines.append(f"clear with: {TOOL}cleanup.py --fix remote-branches for your own; every finish of a session does the same. "
                     "Another author's branch is theirs to delete")
    return lines


# ---------------------------------------------------------------- folders, inbox, threads, warnings

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


def inbox_files(root: Path) -> list[str]:
    folder = root / "memory" / "inbox"
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.name not in ("README.md", ".gitkeep")) \
        if folder.is_dir() else []


def inbox(root: Path) -> list[str]:
    files = inbox_files(root)
    return [f"{len(files)} file(s) wait in /memory/inbox: " + ", ".join(files[:6]) + (" and more" if len(files) > 6 else ""),
            "clear with: file each one under CONTRACT section 11 and remove it from the inbox; the thread that takes a "
            "file from there does both before it moves on"] if files else []


def inbox_line(root: Path) -> str | None:
    """One line for the end of a finish: a thread that took a file from the inbox files it now."""
    files = inbox_files(root)
    if not files:
        return None
    return (f"inbox: {len(files)} file(s) wait in /memory/inbox. A file this thread took from there is filed (CONTRACT "
            "section 11) and removed from the inbox before the thread moves on")


def threads_to_archive(known: dict | None, now: float) -> list[str]:
    if known is None:
        return ["this computer's hosts keep no thread record this script can read; ask the owner which threads are done"]
    idle = sorted({t for t in known.values() if not t.archived and t.last_active and now - t.last_active > ARCHIVE_DAYS * 86400},
                  key=lambda t: t.last_active)
    lines = [f"{datetime.datetime.fromtimestamp(t.last_active).strftime('%Y-%m-%d')}  {t.title[:90]}" for t in idle]
    if lines:
        lines.append(f"clear with: ask the owner which of these {len(idle)} thread(s), idle more than {ARCHIVE_DAYS} days, are "
                     "done, and archive those in the host on their yes; what an archived thread left is then removed at the "
                     "next finish")
    return lines


def archive_line(known: dict | None, now: float) -> str | None:
    """One line for the start of a session: threads the owner may want to archive."""
    if known is None:
        return None
    idle = sorted({t for t in known.values() if not t.archived and t.last_active and now - t.last_active > ARCHIVE_DAYS * 86400},
                  key=lambda t: t.last_active)
    if not idle:
        return None
    names = "; ".join(f"\"{t.title[:60]}\"" for t in idle[:4]) + (" and more" if len(idle) > 4 else "")
    return (f"to archive: {len(idle)} thread(s) idle more than {ARCHIVE_DAYS} days are not archived ({names}). Say so once in "
            "your first reply, and archive in the host those the owner says are done; what an archived thread left is "
            "cleared at the next finish")


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


# ---------------------------------------------------------------- leftovers and commit reasons

def markers(root: Path) -> list[Path]:
    return sorted((root / "temp" / "conductor" / "compacted").glob("*.json"))


def tidy_markers(root: Path, known: dict | None) -> list[str]:
    gone = 0
    for marker in markers(root):
        if known is not None and marker.stem in known and known[marker.stem].archived:
            try:
                marker.unlink()
                gone += 1
            except OSError:
                pass
    return [f"{gone} compaction marker(s) of archived threads removed"] if gone else []


def leftovers(root: Path, known: dict | None) -> list[str]:
    lines = []
    archived = [m for m in markers(root) if known is not None and m.stem in known and known[m.stem].archived]
    unknown = [m for m in markers(root) if known is None or m.stem not in known]
    if archived:
        lines.append(f"{len(archived)} compaction marker(s) belong to archived threads; clear with: {TOOL}cleanup.py --fix markers")
    if unknown:
        lines.append(f"{len(unknown)} compaction marker(s) belong to no thread this computer's host knows; each can go once "
                     "the owner confirms its thread is gone: " + ", ".join(m.stem[:8] for m in unknown[:8]))
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


# ---------------------------------------------------------------- tidy and the report

def tidy(root: Path) -> list[str]:
    """What every finish of a session clears: only what is certainly no longer needed (see the top)."""
    known = threads.known()
    now = datetime.datetime.now().timestamp()
    repos = projects(root)
    return (tidy_copies(root, known) + tidy_markers(root, known) + project_worktrees(repos, now, fix=True)
            + remote_branches(root, repos, now, fix=True) + merged_branches(root, fix=True))


def report(root: Path, fetch: bool, fix: set[str], older_than: float) -> int:
    repos = projects(root)
    if fetch:
        for repo in [r for _, r in session.repositories(root)] + [p.checkout for p in repos]:
            git(repo, "fetch", "--quiet", "--prune", "origin", timeout=90)
    now = datetime.datetime.now()
    stamp = now.timestamp()
    known = threads.known()
    cleared = (tidy_copies(root, known) if "copies" in fix else []) + (tidy_markers(root, known) if "markers" in fix else [])
    sections = [
        (f"Long state and knowledge files (over {state.LIMIT:,} characters, near from {NEAR:,})", long_files(root, repos)),
        ("Stale handover entries in project repositories", stale_handovers(repos, now.date())),
        (f"Session copies idle {IDLE_DAYS} days or more, or left by an archived thread", session_copies(root, stamp, known)),
        ("Session branches already merged", merged_branches(root, "branches" in fix)),
        ("Project working copies already merged", project_worktrees(repos, stamp, "worktrees" in fix)),
        ("Remote branches already merged", remote_branches(root, repos, stamp, "remote-branches" in fix, older_than)),
        ("Project folders behind their remote", project_folders(repos)),
        ("Inbox", inbox(root)),
        ("Threads to archive", threads_to_archive(known, stamp)),
        ("Preflight warnings, by kind", warnings(root)),
        ("Leftovers", leftovers(root, known)),
        ("Commits of the last 7 days that give a reason (a figure to watch, nothing to clear)", commit_reasons(root, repos)),
    ]
    print(f"Cleanup report of {now.strftime('%Y-%m-%d %H:%M')}: nothing here fails a commit.")
    for line in cleared:
        print("cleared: " + line)
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
    parser.add_argument("--fix", action="append", default=[], choices=[*FIXES, "all"],
                        help="also clear what is safe to clear; `all` is what every finish of a session clears")
    parser.add_argument("--older-than", type=float, default=0, metavar="DAYS",
                        help="with --fix remote-branches: only branches whose last commit is at least this old")
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    fix = set(FIXES) if "all" in args.fix else set(args.fix)
    return report(args.root.resolve(), not args.no_fetch, fix, args.older_than)


if __name__ == "__main__":
    sys.exit(main())
