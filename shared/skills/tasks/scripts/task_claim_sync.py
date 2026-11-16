"""A claim in a shared repository reaches the other brains at once (see task_claims.py).

    publish(store, paths, subject)   commit exactly these paths and push the store branch
    ClaimLost                        another brain changed the card first; the claim was withdrawn

A claim that stays on one computer protects nothing: the other brains still see a free card. So
a claim or a release written to a repository store is committed on its own and pushed straight
away. Nothing else is ever pushed with it: when the checkout already carries commits of its own
that origin does not have, the claim is committed and the push is left to the conductor, with a
note saying the claim is invisible until then.

When origin moved between the fetch and the push, origin is merged (never rebased) and the push is
tried once more. When that merge conflicts, another brain changed the same card first: the merge
is abandoned, the claim is withdrawn by a second commit, and ClaimLost says so. History is never
rewritten and nothing is forced.

The commit names its tool, and takes its Co-Authored-By from BRAIN_CO_AUTHOR or, failing that,
the newest one in the repository's history; a model is never invented.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

CO_AUTHOR_ENV = "BRAIN_CO_AUTHOR"
PUSH_TIMEOUT_S = 600


class ClaimLost(ValueError):
    """Another brain changed the card first; the local claim was withdrawn."""


def _git(checkout: Path, *args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _last(done: subprocess.CompletedProcess) -> str:
    lines = [line.strip() for line in ((done.stderr or "") + "\n" + (done.stdout or "")).splitlines() if line.strip()]
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


def _ahead(checkout: Path, branch: str) -> int:
    done = _git(checkout, "rev-list", "--count", f"origin/{branch}..HEAD")
    return int(done.stdout.strip() or 0) if done.returncode == 0 else 0


def publish(store, paths: list[Path], subject: str) -> list[str]:
    """Commit `paths` in the store's checkout and push its branch; returns notes to show.
    Raises ClaimLost when another brain changed the card first."""
    checkout, branch = store.checkout, store.branch
    names = sorted({str(path) for path in paths})
    waiting = _ahead(checkout, branch)
    _git(checkout, "add", "-A", "--", *names)
    if _git(checkout, "diff", "--cached", "--quiet", "--", *names).returncode == 0:
        return []
    committed = _git(checkout, "commit", "--quiet", "-m", _message(checkout, subject), "--", *names)
    if committed.returncode != 0:
        return [f"{store.label}: written but not committed ({_last(committed)}); commit and push it now, "
                "the other brains cannot see it until then"]
    if waiting:
        return [f"{store.label}: committed, not pushed: this checkout has {waiting} unpushed commit(s) of its "
                "own, and a claim never pushes other work. The other brains cannot see it until you push"]
    pushed = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if pushed.returncode == 0:
        return [f"{store.label}: committed and pushed to origin/{branch}"]
    if _git(checkout, "fetch", "origin", branch).returncode != 0:
        return [f"{store.label}: committed, not pushed ({_last(pushed)}); push it now, the other brains "
                "cannot see it until then"]
    if _ahead(checkout, branch) and _git(checkout, "rev-list", "--count", f"HEAD..origin/{branch}").stdout.strip() in ("", "0"):
        return [f"{store.label}: committed, not pushed ({_last(pushed)}); push it now, the other brains "
                "cannot see it until then"]
    merged = _git(checkout, "merge", "--no-edit", "-m", _message(checkout, f"Merge origin/{branch} after a claim"),
                  f"origin/{branch}")
    if merged.returncode != 0:
        _git(checkout, "merge", "--abort")
        _git(checkout, "revert", "--no-commit", "HEAD")
        _git(checkout, "commit", "--quiet", "-m", _message(checkout, f"Withdraw: {subject}"))
        raise ClaimLost(f"{store.label}: another brain changed this card first, so the change was withdrawn here. "
                        f"Run `git -C {checkout.as_posix()} pull --no-rebase`, then look at who holds the card")
    again = _git(checkout, "push", "origin", f"HEAD:{branch}", timeout=PUSH_TIMEOUT_S)
    if again.returncode == 0:
        return [f"{store.label}: committed, merged origin/{branch} and pushed"]
    return [f"{store.label}: committed and merged, not pushed ({_last(again)}); push it now, the other brains "
            "cannot see it until then"]
