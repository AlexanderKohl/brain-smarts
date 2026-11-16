"""A claim in a shared repository reaches the other brains at once, or is not made (task_claims.py).

    ready(store)                              refuse before anything is written
    publish(store, paths, subject, ...)       commit exactly these paths and push the store branch
    ClaimNotMade                              the change could not be published and was undone here
    ClaimLost                                 another brain changed the card first; undone here

A claim that stays on one computer protects nothing: the other brains still see a free card. So
a claim or a release written to a repository store either reaches origin or is taken back, and
the command fails; it never ends as a local claim that looks like success. `--offline` is the
one deliberate exception, and says so.

To keep that promise simple, a claim is made only from a checkout with nothing staged and no
work of its own waiting to be pushed (`ready`): the claim is then the only thing committed, the
only thing pushed, and the only thing a withdrawal undoes.

    commit refused (a hook)           the files are put back as they were; ClaimNotMade
    push accepted                     done
    push refused, origin unreachable
      or not ahead (hook, protection) the claim is withdrawn by a second commit; ClaimNotMade
    push refused, origin moved        origin is merged (never rebased) and the push tried again
      merge conflicts only in STATE.md   STATE.md is generated again and the merge completed
      merge conflicts in the card        merge abandoned, claim withdrawn; ClaimLost
      merge leaves the card another's    claim withdrawn; ClaimLost

History is never rewritten and nothing is forced. A withdrawal is its own commit, so a claim
and its withdrawal can sit unpushed together; `ready` allows that, because together they change
nothing. The commit names its tool and takes its Co-Authored-By from BRAIN_CO_AUTHOR or the
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


def _withdraw(checkout: Path, claim: str, subject: str) -> str:
    """Take the claim commit back by a second commit. Returns "" when done, else what is left."""
    if _git(checkout, "rev-parse", "-q", "--verify", "MERGE_HEAD").returncode == 0:
        if _git(checkout, "merge", "--abort").returncode != 0:
            return f"a merge is unfinished in {checkout.as_posix()}; finish or abort it by hand, then revert {claim[:8]}"
    reverted = _git(checkout, "revert", "--no-commit", claim)
    if reverted.returncode != 0:
        _git(checkout, "revert", "--abort")
        return f"the commit {claim[:8]} is still in {checkout.as_posix()} ({_last(reverted)}); revert it by hand"
    done = _git(checkout, "commit", "--quiet", "-m", _message(checkout, f"Withdraw: {subject}"))
    if done.returncode != 0:
        _git(checkout, "revert", "--abort")
        return f"the commit {claim[:8]} is still in {checkout.as_posix()} ({_last(done)}); revert it by hand"
    return ""


def _fail(kind: type, store, checkout: Path, claim: str, subject: str, why: str) -> ClaimNotMade:
    left = _withdraw(checkout, claim, subject)
    tail = "it was withdrawn here, so the card is as it was" if not left else f"and it could NOT be withdrawn: {left}"
    return kind(f"{store.label}: {why}; {tail}")


def publish(store, paths: list[Path], subject: str, rebuild: Callable[[], object] | None = None,
            still_ours: Callable[[], bool] | None = None) -> list[str]:
    """Commit `paths` in the store's checkout and push its branch; returns notes to show.
    `rebuild` regenerates STATE.md (true when it changed); `still_ours` says, after a merge,
    whether the card is still as this change left it. Raises ClaimNotMade or ClaimLost, always
    after undoing the change here."""
    checkout, branch = store.checkout, store.branch
    names = sorted({str(path) for path in paths})
    state = str(store.path / "STATE.md")
    _git(checkout, "add", "-A", "--", *names)
    if _git(checkout, "diff", "--cached", "--quiet", "--", *names).returncode == 0:
        return []
    committed = _git(checkout, "commit", "--quiet", "-m", _message(checkout, subject), "--", *names)
    if committed.returncode != 0:
        _put_back(checkout, names)
        raise ClaimNotMade(f"{store.label}: the commit was refused ({_last(committed)}); nothing was changed")
    claim = _git(checkout, "rev-parse", "HEAD").stdout.strip()
    pushed = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if pushed.returncode == 0:
        return [f"{store.label}: committed and pushed to origin/{branch}"]
    if _git(checkout, "fetch", "origin", branch).returncode != 0:
        raise _fail(ClaimNotMade, store, checkout, claim, subject, f"origin could not be reached ({_last(pushed)})")
    if not _count(checkout, f"HEAD..origin/{branch}"):
        raise _fail(ClaimNotMade, store, checkout, claim, subject, f"the push was refused ({_last(pushed)})")
    merge_message = _message(checkout, f"Merge origin/{branch} after: {subject}")
    merged = _git(checkout, "merge", "--no-edit", "-m", merge_message, f"origin/{branch}")
    if merged.returncode != 0:
        stuck = [line.strip() for line in _git(checkout, "diff", "--name-only", "--diff-filter=U").stdout.splitlines()
                 if line.strip()]
        only_state = bool(stuck) and all((checkout / name).resolve() == Path(state).resolve() for name in stuck)
        if not (only_state and rebuild is not None):
            why = "another brain changed this card first" if stuck else f"origin could not be merged ({_last(merged)})"
            raise _fail(ClaimLost if stuck else ClaimNotMade, store, checkout, claim, subject, why)
        rebuild()
        _git(checkout, "add", "--", state)
        done = _git(checkout, "commit", "--quiet", "-m", merge_message)
        if done.returncode != 0:
            raise _fail(ClaimNotMade, store, checkout, claim, subject, f"the merge could not be completed ({_last(done)})")
    if still_ours is not None and not still_ours():
        raise _fail(ClaimLost, store, checkout, claim, subject, "another brain changed this card first")
    if rebuild is not None and rebuild():
        _git(checkout, "add", "--", state)
        _git(checkout, "commit", "--quiet", "-m", _message(checkout, f"STATE.md after: {subject}"), "--", state)
    again = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if again.returncode == 0:
        return [f"{store.label}: committed, merged origin/{branch} and pushed"]
    raise _fail(ClaimNotMade, store, checkout, claim, subject, f"the push was refused after merging ({_last(again)})")
