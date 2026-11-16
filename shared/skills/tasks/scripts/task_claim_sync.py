"""A claim in a shared repository reaches the other brains at once, or is not made (task_claims.py).

    ready(store)                              refuse before anything is written
    publish(store, paths, subject, ...)       commit exactly these paths and push the store branch
    ClaimNotMade                              the change could not be published and was undone here
    ClaimLost                                 another brain changed the card first; undone here

A claim that stays on one computer protects nothing: the other brains still see a free card. So
a claim or a release written to a repository store either reaches origin or is taken back, and
the command fails; it never ends as a local claim that looks like success. `--offline` is the
one deliberate exception, and says so.

To keep that promise simple, a claim is made only from a checkout with nothing staged, no
uncommitted edit inside the task store and no work of its own waiting to be pushed (`ready`):
the claim is then the only thing committed, the only thing pushed, and the only thing a
withdrawal undoes. Uncommitted edits elsewhere in the checkout are left alone: they are never
committed, and origin is not merged over them.

    commit refused (a hook)           the files are put back as they were; ClaimNotMade
    push accepted                     done
    push reported failed, yet origin
      holds the commit                done
    push refused, origin unreachable
      or not ahead (hook, protection) the claim is withdrawn by a second commit; ClaimNotMade
    push refused, origin moved,
      uncommitted edits elsewhere     withdrawn; ClaimNotMade says to pull first
    push refused, origin moved        origin is merged (never rebased) and the push tried again
      merge conflicts only in STATE.md   STATE.md is generated again and the merge completed
      merge conflicts in the card        merge abandoned, claim withdrawn; ClaimLost
      merge leaves the card another's    claim withdrawn; ClaimLost

History is never rewritten and nothing is forced. A withdrawal is its own commit of exactly
the claim's paths, set back to what they were before the claim (or, once origin has been merged
in, to what origin holds) with STATE.md generated again; it never reverts a commit, so a
regenerated STATE.md cannot make it conflict. A claim and its withdrawal can sit unpushed
together; `ready` allows that, because together they change nothing. The commit names its tool and takes its Co-Authored-By from BRAIN_CO_AUTHOR or the
newest one in the repository's history; a model is never invented.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Callable

CO_AUTHOR_ENV = "BRAIN_CO_AUTHOR"
PUSH_TIMEOUT_S = 600


class ClaimNotMade(ValueError):
    """The change could not be published, and was undone in this checkout."""


class ClaimLost(ClaimNotMade):
    """Another brain changed the card first; the change was undone in this checkout."""


def _git(checkout: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    command = ["git", "-C", str(checkout), *args]
    try:
        return subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 124, "", f"git {args[0]} took longer than {timeout} s")


def _last(done: subprocess.CompletedProcess) -> str:
    lines = [line.strip() for line in ((done.stdout or "") + "\n" + (done.stderr or "")).splitlines() if line.strip()]
    return lines[-1] if lines else "no message"


def co_author(checkout: Path) -> str | None:
    value = os.environ.get(CO_AUTHOR_ENV, "").strip()
    if value.lower().startswith("co-authored-by:"):
        value = value.split(":", 1)[1].strip()
    if value:
        return value
    done = _git(checkout, "log", "-n", "1", "-i", "--grep=^co-authored-by:",
                "--format=%(trailers:key=Co-Authored-By,valueonly)")
    found = [line.strip() for line in (done.stdout or "").splitlines() if line.strip()] if done.returncode == 0 else []
    return found[0] if found else None


def _message(checkout: Path, subject: str) -> str:
    author = co_author(checkout)
    return f"{subject}\n\nTool: tasks.py\n" + (f"Co-Authored-By: {author}\n" if author else "")


def _count(checkout: Path, span: str) -> int:
    done = _git(checkout, "rev-list", "--count", span)
    return int(done.stdout.strip() or 0) if done.returncode == 0 else 0


def ready(store) -> None:
    """Raise ClaimNotMade unless a claim made now would be the only thing committed and pushed."""
    checkout, branch = store.checkout, store.branch
    fix = f"git -C {checkout.as_posix()}"
    if _git(checkout, "diff", "--cached", "--quiet").returncode != 0:
        raise ClaimNotMade(f"{store.label}: files are staged in this checkout, and a claim commits and pushes on its "
                           f"own. Commit or unstage them first (`{fix} status`), or pass --offline for a claim only "
                           "this computer sees")
    if _git(checkout, "diff", "--quiet", "--", str(store.path)).returncode != 0:
        raise ClaimNotMade(f"{store.label}: task files here have uncommitted edits, and a claim would publish them. "
                           f"Commit or discard them first (`{fix} status`)")
    waiting = _count(checkout, f"origin/{branch}..HEAD")
    if waiting and _git(checkout, "diff", "--quiet", f"origin/{branch}", "HEAD").returncode != 0:
        raise ClaimNotMade(f"{store.label}: this checkout has {waiting} unpushed commit(s) of its own, and a claim "
                           f"never pushes other work. Push them first (`{fix} push`), or pass --offline for a claim "
                           "only this computer sees")


def _put_back(checkout: Path, names: list[str]) -> None:
    """Undo an uncommitted change to exactly these paths: tracked ones as in HEAD, new ones removed."""
    _git(checkout, "reset", "--quiet", "--", *names)
    tracked = [name for name in names if _git(checkout, "ls-files", "--error-unmatch", "--", name).returncode == 0]
    if tracked:
        _git(checkout, "checkout", "--quiet", "HEAD", "--", *tracked)
    for name in names:
        if name not in tracked and Path(name).is_file():
            Path(name).unlink()


def _withdraw(checkout: Path, names: list[str], subject: str, base: str,
              rebuild: Callable[[], object] | None) -> str:
    """Set exactly the claim's paths back to what `base` holds, generate STATE.md again and
    commit those paths. Returns "" when done (or nothing was left to undo), else what is left."""
    if _git(checkout, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        if _git(checkout, "merge", "--abort").returncode != 0:
            return f"a merge is unfinished in {checkout.as_posix()}; finish or abort it by hand"
    root = checkout.resolve()
    for name in names:
        rel = Path(name).resolve().relative_to(root).as_posix()
        if _git(checkout, "cat-file", "-e", f"{base}:{rel}").returncode == 0:
            back = _git(checkout, "checkout", "--quiet", base, "--", name)
            if back.returncode != 0:
                return f"{rel} could not be put back in {checkout.as_posix()} ({_last(back)})"
        elif Path(name).is_file():
            Path(name).unlink()
    if rebuild is not None:
        try:
            rebuild()
        except (OSError, ValueError) as err:
            return f"STATE.md could not be generated again in {checkout.as_posix()} ({err})"
    if _git(checkout, "add", "-A", "--", *names).returncode != 0:
        return f"the paths could not be staged in {checkout.as_posix()}"
    if _git(checkout, "diff", "--cached", "--quiet", "--", *names).returncode == 0:
        return ""
    done = _git(checkout, "commit", "--quiet", "-m", _message(checkout, f"Withdraw: {subject}"), "--", *names)
    if done.returncode != 0:
        _git(checkout, "reset", "--quiet", "--", *names)
        return f"the withdrawal could not be committed in {checkout.as_posix()} ({_last(done)})"
    return ""


class _Change:
    """One published change: what `_fail` needs to take it back."""

    def __init__(self, store, names: list[str], subject: str, base: str, rebuild) -> None:
        self.store, self.names, self.subject, self.base, self.rebuild = store, names, subject, base, rebuild

    def fail(self, kind: type, why: str) -> ClaimNotMade:
        left = _withdraw(self.store.checkout, self.names, self.subject, self.base, self.rebuild)
        tail = "it was withdrawn here" if not left else f"and it could NOT be withdrawn: {left}"
        return kind(f"{self.store.label}: {why}; {tail}")


def publish(store, paths: list[Path], subject: str, rebuild: Callable[[], object] | None = None,
            still_ours: Callable[[], bool] | None = None) -> list[str]:
    """Commit `paths` in the store's checkout and push its branch; returns notes to show.
    `rebuild` regenerates STATE.md (true when it changed); `still_ours` says, after a merge,
    whether the card is still as this change left it. Raises ClaimNotMade or ClaimLost, always
    after undoing the change here."""
    checkout, branch = store.checkout, store.branch
    names = sorted({str(path) for path in paths})
    state = str(store.path / "STATE.md")
    before = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    if _git(checkout, "add", "-A", "--", *names).returncode != 0:
        _put_back(checkout, names)
        raise ClaimNotMade(f"{store.label}: the change could not be staged; nothing was changed")
    if _git(checkout, "diff", "--cached", "--quiet", "--", *names).returncode == 0:
        return []
    committed = _git(checkout, "commit", "--quiet", "-m", _message(checkout, subject), "--", *names)
    claim = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    if claim == before:      # a commit that failed after it was made (a slow hook) is still made
        _put_back(checkout, names)
        raise ClaimNotMade(f"{store.label}: the commit was refused ({_last(committed)}); nothing was changed")
    made = _Change(store, names, subject, before, rebuild)
    pushed = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if pushed.returncode == 0:
        return [f"{store.label}: committed and pushed to origin/{branch}"]
    if _git(checkout, "fetch", "origin", branch).returncode != 0:
        raise made.fail(ClaimNotMade, f"origin could not be reached ({_last(pushed)})")
    if _git(checkout, "merge-base", "--is-ancestor", claim, f"origin/{branch}").returncode == 0:
        return [f"{store.label}: committed and pushed to origin/{branch} (the push reported a failure, but origin holds it)"]
    if not _count(checkout, f"HEAD..origin/{branch}"):
        raise made.fail(ClaimNotMade, f"the push was refused ({_last(pushed)})")
    if _git(checkout, "diff", "--quiet").returncode != 0:
        raise made.fail(ClaimNotMade, "origin moved meanwhile, and it is not merged over this checkout's uncommitted "
                        f"edits: run `git -C {checkout.as_posix()} pull`, then claim again")
    merge_message = _message(checkout, f"Merge origin/{branch} after: {subject}")
    merged = _git(checkout, "merge", "--no-edit", "-m", merge_message, f"origin/{branch}")
    if merged.returncode != 0:
        stuck = [line.strip().strip('"') for line in
                 _git(checkout, "diff", "--name-only", "--diff-filter=U").stdout.splitlines() if line.strip()]
        only_state = bool(stuck) and all((checkout / name).resolve() == Path(state).resolve() for name in stuck)
        if not (only_state and rebuild is not None):
            why = "another brain changed this card first" if stuck else f"origin could not be merged ({_last(merged)})"
            raise made.fail(ClaimLost if stuck else ClaimNotMade, why)
        rebuild()
        _git(checkout, "add", "--", state)
        done = _git(checkout, "commit", "--quiet", "-m", merge_message)
        if done.returncode != 0:
            raise made.fail(ClaimNotMade, f"the merge could not be completed ({_last(done)})")
    made.base = f"origin/{branch}"      # origin is merged in: a withdrawal now returns the card to what origin holds
    if still_ours is not None and not still_ours():
        raise made.fail(ClaimLost, "another brain changed this card first")
    if rebuild is not None and rebuild():
        _git(checkout, "add", "--", state)
        fresh = _git(checkout, "commit", "--quiet", "-m", _message(checkout, f"STATE.md after: {subject}"), "--", state)
        if fresh.returncode != 0:
            _git(checkout, "reset", "--quiet", "--", state)
            raise made.fail(ClaimNotMade, f"STATE.md could not be committed after the merge ({_last(fresh)})")
    again = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if again.returncode == 0:
        return [f"{store.label}: committed, merged origin/{branch} and pushed"]
    if _git(checkout, "fetch", "origin", branch).returncode == 0 and \
            _git(checkout, "merge-base", "--is-ancestor", claim, f"origin/{branch}").returncode == 0:
        return [f"{store.label}: committed, merged origin/{branch} and pushed (the push reported a failure, but origin holds it)"]
    raise made.fail(ClaimNotMade, f"the push was refused after merging ({_last(again)})")
