"""Git transactions of the synced secrets store (design: synced-secrets-repository.md, section 9).

Standard library plus the git command line only. Every remote commit is verified one at a time
before the working tree reaches it; every write is one commit built on the verified remote head
and pushed without force. A refused push is a Conflict: the caller rebuilds from fresh state.
Never rebase, merge, or force."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from . import canonical
from .errors import SecretStoreError

BRANCH = "main"
REMOTE = "origin"
ALLOWED_MESSAGES = frozenset({"update", "policy", "recovery"})
GITATTRIBUTES = ".gitattributes"
GITATTRIBUTES_BYTES = b"* -text\n"
_STATE_FILE = "secret-store-state.json"
_LOCK_FILE = "secret-store.lock"


class RefusedCommit(SecretStoreError):
    """A remote commit failed verification. Names the commit, never the content."""

    def __init__(self, commit: str) -> None:
        super().__init__(f"remote commit {commit} was refused by verification")
        self.commit = commit


class Conflict:
    """The remote moved on: fetch, verify (pull) and rebuild the change from fresh state."""

    def __init__(self, remote_head: str | None) -> None:
        self.remote_head = remote_head

    def __repr__(self) -> str:
        return f"Conflict(remote_head={self.remote_head!r})"


@contextlib.contextmanager
def repo_lock(lock_path: Path, timeout: float = 120.0) -> Iterator[None]:
    """Exclusive per-repository lock on Windows and POSIX; released in finally (and by the OS
    if the process dies, so a crash never leaves a stale lock)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+b")
    deadline = time.monotonic() + timeout
    try:
        if os.name == "nt":
            import msvcrt
            while True:
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise SecretStoreError("timed out waiting for the repository lock") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise SecretStoreError("timed out waiting for the repository lock") from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


class SecretRepo:
    def __init__(self, path: str | os.PathLike, remote_url: str) -> None:
        self.path = Path(path)
        self.remote_url = str(remote_url)

    # -- git plumbing -------------------------------------------------------------------------
    def _git(self, *args: str, check: bool = True, cwd: Path | None = None) -> subprocess.CompletedProcess:
        result = subprocess.run(["git", *args], cwd=str(cwd or self.path), capture_output=True)
        if check and result.returncode != 0:
            raise SecretStoreError(f"git {args[0]} failed")
        return result

    def _out(self, *args: str) -> str:
        return self._git(*args).stdout.decode("utf-8").strip()

    def _rev(self, ref: str) -> str | None:
        result = self._git("rev-parse", "--verify", "-q", ref + "^{commit}", check=False)
        if result.returncode != 0:
            return None
        return result.stdout.decode().strip() or None

    def _remote_ref(self) -> str:
        return f"refs/remotes/{REMOTE}/{BRANCH}"

    def _is_ancestor(self, older: str, newer: str) -> bool:
        return self._git("merge-base", "--is-ancestor", older, newer, check=False).returncode == 0

    def _fetch(self) -> str | None:
        result = self._git("fetch", "--quiet", "--no-tags", REMOTE,
                           f"+refs/heads/{BRANCH}:{self._remote_ref()}", check=False)
        if result.returncode != 0:
            ls = self._git("ls-remote", "--heads", REMOTE, BRANCH, check=False)
            if ls.returncode == 0 and not ls.stdout.strip():
                return None  # the remote is still empty
            raise SecretStoreError("could not fetch from the secrets repository")
        return self._rev(self._remote_ref())

    def _state(self) -> dict[str, Any]:
        state_path = self.path / ".git" / _STATE_FILE
        if not state_path.exists():
            return {}
        return json.loads(state_path.read_text("utf-8"))

    def _set_state(self, **values: Any) -> None:
        state_path = self.path / ".git" / _STATE_FILE
        tmp = state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(values), "utf-8")
        os.replace(tmp, state_path)

    # -- public API ---------------------------------------------------------------------------
    def clone_or_open(self) -> "SecretRepo":
        if (self.path / ".git").is_dir():
            if self._out("remote", "get-url", REMOTE) != self.remote_url:
                raise SecretStoreError("the local clone points at a different remote")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._git("clone", "--quiet", "--no-checkout", self.remote_url, str(self.path), cwd=self.path.parent)
            self._git("symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
            # The clone's own branch is unverified: start unborn so pull verifies from the root.
            self._git("update-ref", "-d", f"refs/heads/{BRANCH}", check=False)
            self._git("read-tree", "--empty")
        for key in ("user.name", "user.email"):
            value = self._git("config", "--global", key, check=False).stdout.decode().strip()
            if not value:
                raise SecretStoreError(f"git config --global {key} is not set")
            self._git("config", "--local", key, value)
        self._git("config", "--local", "core.autocrlf", "false")
        self._git("config", "--local", "core.eol", "lf")
        info = self.path / ".git" / "info"
        info.mkdir(exist_ok=True)
        (info / "attributes").write_bytes(GITATTRIBUTES_BYTES)
        return self

    def head(self) -> str | None:
        return self._rev("HEAD")

    def pull(self, verify: Callable[[str, dict[str, Any]], bool]) -> str | None:
        """Fetch, then verify every new remote commit in order; the working tree advances only to
        the last accepted commit. On refusal raise RefusedCommit naming the bad commit."""
        remote = self._fetch()
        local = self.head()
        if remote is None or remote == local:
            if remote == local:
                self._set_state()
            return local
        if local is not None and not self._is_ancestor(local, remote):
            raise SecretStoreError("the remote history does not contain this computer's state; refusing older or rewritten history")
        span = remote if local is None else f"{local}..{remote}"
        commits = self._out("rev-list", "--reverse", "--topo-order", span).split()
        for commit in commits:
            if len(self._out("rev-list", "--parents", "-n", "1", commit).split()) > 2:
                self._refuse(commit)
            try:
                accepted = verify(commit, self._changed_files(commit))
            except SecretStoreError:
                accepted = False
            if accepted is not True:
                self._refuse(commit)
            self._advance(commit)
        self._set_state()
        return self.head()

    def _refuse(self, commit: str) -> None:
        self._set_state(refused=commit)
        raise RefusedCommit(commit)

    def _changed_files(self, commit: str) -> dict[str, Any]:
        raw = self._git("diff-tree", "--root", "--no-commit-id", "-r", "-z", "--name-status",
                        "--no-renames", commit).stdout.decode("utf-8")
        fields = [f for f in raw.split("\0") if f]
        files: dict[str, Any] = {}
        for status, name in zip(fields[0::2], fields[1::2]):
            blob = None if status == "D" else self._git("cat-file", "blob", f"{commit}:{name}").stdout
            if name == GITATTRIBUTES:
                if blob != GITATTRIBUTES_BYTES:
                    raise SecretStoreError(".gitattributes changed")
                continue
            files[name] = None if blob is None else canonical.loads(blob)
        return files

    def _advance(self, commit: str) -> None:
        """Move branch, index and working tree to commit (a fast-forward, never a merge)."""
        old = self.head()
        if old is None:
            self._git("read-tree", "-u", "--reset", commit)
        else:
            self._git("read-tree", "-u", "-m", old, commit)
        self._git("update-ref", f"refs/heads/{BRANCH}", commit, *(([old]) if old else []))

    def write(self, change: dict[str, Any], message: str) -> "str | Conflict":
        """One change, one commit on the verified remote head, pushed without force."""
        if message not in ALLOWED_MESSAGES:
            raise SecretStoreError("commit message is not in the allowed set")
        if not change:
            raise SecretStoreError("an empty change is refused")
        for name in change:
            parts = Path(name).parts
            if name == GITATTRIBUTES or not parts or ".." in parts or ".git" in parts or Path(name).is_absolute():
                raise SecretStoreError("change path is not allowed")
        with repo_lock(self.path / ".git" / _LOCK_FILE):
            if self._state().get("refused"):
                raise SecretStoreError("a remote commit was refused; resolve it before writing")
            remote = self._fetch()
            local = self.head()
            if remote != local:
                if remote is not None and (local is None or self._is_ancestor(local, remote)):
                    return Conflict(remote)
                raise SecretStoreError("local head is not the verified remote head")
            blobs = {name: canonical.dumps(value) for name, value in change.items() if value is not None}
            for name, value in change.items():
                target = self.path / name
                if value is None:
                    if local is None or not self._git("cat-file", "-e", f"HEAD:{name}", check=False).returncode == 0:
                        raise SecretStoreError("removal of a file that does not exist")
                    self._git("rm", "--quiet", "--cached", "--", name)
                    target.unlink(missing_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    tmp = target.with_name(target.name + ".tmp")
                    tmp.write_bytes(blobs[name])
                    os.replace(tmp, target)
                    self._git("add", "--", name)
            if local is None or self._git("cat-file", "-e", f"HEAD:{GITATTRIBUTES}", check=False).returncode != 0:
                (self.path / GITATTRIBUTES).write_bytes(GITATTRIBUTES_BYTES)
                self._git("add", "--", GITATTRIBUTES)
            commit_result = self._git("commit", "--quiet", "--no-verify", "-m", message, check=False)
            if commit_result.returncode != 0:
                self._restore(local)
                raise SecretStoreError("nothing to commit or commit failed")
            new = self.head()
            push = self._git("push", "--quiet", "--porcelain", REMOTE,
                             f"refs/heads/{BRANCH}:refs/heads/{BRANCH}", check=False)
            if push.returncode != 0:
                text = (push.stdout + push.stderr).decode("utf-8", "replace")
                if "rejected" in text or "fetch first" in text or "non-fast-forward" in text:
                    self._restore(local)
                    return Conflict(remote)
                raise SecretStoreError("push did not complete; the change is committed locally but not synced")
            self._git("update-ref", self._remote_ref(), new)
            return new

    def settle_failed_write(self, before: str | None) -> str | None:
        """After write raised: the commit it made when the remote head is that very commit (the
        push landed and only its acknowledgement was lost); otherwise None, with any local commit
        dropped back to before, so nothing unverified stays ahead of the checkpoint."""
        with repo_lock(self.path / ".git" / _LOCK_FILE):
            local = self.head()
            if local is None or local == before:
                return None
            try:
                remote = self._fetch()
            except SecretStoreError:
                remote = None
            if remote == local:
                self._set_state()
                return local
            self._restore(before)
            return None

    def _restore(self, commit: str | None) -> None:
        """Drop a local commit that the remote refused, back to the verified head."""
        if commit is None:
            self._git("update-ref", "-d", f"refs/heads/{BRANCH}")
            self._git("read-tree", "--empty")
            self._git("clean", "-fdq", "-e", ".gitattributes")
            for name in self._out("ls-files", "--others").split("\n"):
                if name:
                    (self.path / name).unlink(missing_ok=True)
        else:
            self._git("reset", "--quiet", "--hard", commit)

    def status(self) -> str:
        """Plain-words summary, never a raw Git error."""
        refused = self._state().get("refused")
        if refused:
            return f"Refused at commit {refused}: a remote change failed verification; nothing after it is used."
        try:
            remote = self._fetch()
        except SecretStoreError:
            return "Could not reach the secrets repository; working from the local copy."
        local = self.head()
        if remote == local:
            return "Up to date."
        if remote is None:
            return "Ahead: local changes are not on the remote yet."
        if local is None:
            return "Behind: the remote has changes to pull."
        ahead, behind = (int(n) for n in self._out("rev-list", "--left-right", "--count",
                                                     f"{local}...{remote}").split())
        if ahead and behind:
            return "Diverged: local and remote both changed; the local change must be rebuilt."
        if ahead:
            return f"Ahead by {ahead} commit(s): local changes are not on the remote yet."
        return f"Behind by {behind} commit(s): pull to verify and apply them."

    def read(self, name: str) -> Any:
        return canonical.loads((self.path / name).read_bytes())
