"""Git transactions of the synced secrets store (design: synced-secrets-repository.md, section 9).

Standard library plus the git command line only. Every remote commit is verified one at a time
before the working tree reaches it; every write is one commit built on the verified remote head
and pushed without force. A refused push is a Conflict: the caller rebuilds from fresh state.
Never rebase, merge, or force."""

from __future__ import annotations

import contextlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from . import canonical
from .accept_rules import REFUSAL_CODES, RuleRefusal
from .errors import SecretStoreError

BRANCH = "main"
REMOTE = "origin"
ALLOWED_MESSAGES = frozenset({"update", "policy", "recovery"})
GITATTRIBUTES = ".gitattributes"
GITATTRIBUTES_BYTES = b"* -text\n"
_STATE_FILE = "secret-store-state.json"
_LOCK_FILE = "secret-store.lock"
_ANY = object()
_HELD: dict[tuple[str, int], int] = {}  # (clone, thread) -> nesting depth of the lock


_SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,140}")
_COMMIT_ID = re.compile(r"[0-9a-f]{40,64}")


def refusal_text(code: Any, oid: Any = None) -> str:
    """The fixed text of a rule code from the closed list REFUSAL_CODES (plan section L), with an
    object id only when the store checked it is one of its own; never text taken from a commit,
    from Git's output or from an exception."""
    code = code if code in REFUSAL_CODES else "unclassified"
    where = f", object {oid}" if isinstance(oid, str) and _SAFE_ID.fullmatch(oid) else ""
    return f"{REFUSAL_CODES[code]} (rule {code}{where})"


class RefusedCommit(SecretStoreError):
    """A commit failed verification. Names the commit, a fixed rule code and at most an object id
    the store checked is its own (safe_oid), never a pathname, a value or other text."""

    def __init__(self, commit: str, code: Any = None, oid: Any = None) -> None:
        self.commit = commit
        self.code = code if code in REFUSAL_CODES else "unclassified"
        self.oid = oid if isinstance(oid, str) and _SAFE_ID.fullmatch(oid) else None
        self.reason = refusal_text(self.code, self.oid)
        super().__init__(f"remote commit {commit} was refused by verification: {self.reason}")


def refusal_of(error: BaseException) -> tuple[str, str | None]:
    """The code of a verifier's error and the object id the store marked safe on it (safe_oid)."""
    return getattr(error, "code", "unclassified"), getattr(error, "safe_oid", None)


class MovedHead(SecretStoreError):
    """The head moved after the change was built and verified."""


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

    @contextlib.contextmanager
    def lock(self) -> Iterator[None]:
        """The repository lock, re-entrant within one thread: store.py holds it across a whole
        transaction (sync, build, verify, commit, push, checkpoint) and write/pull nest inside."""
        key = (str((self.path / ".git").resolve()), threading.get_ident())
        if _HELD.get(key):  # this thread already holds it, through this or another SecretRepo
            _HELD[key] += 1
            try:
                yield
            finally:
                _HELD[key] -= 1
            return
        with repo_lock(self.path / ".git" / _LOCK_FILE):
            _HELD[key] = 1
            try:
                yield
            finally:
                _HELD.pop(key, None)

    def commits(self) -> list[str]:
        """Commits reachable from HEAD, newest first."""
        return self._out("rev-list", "HEAD").split() if self.head() else []

    def read_at(self, commit: str, name: str) -> Any:
        found = self._git("cat-file", "blob", f"{commit}:{name}", check=False)
        return canonical.loads(found.stdout) if found.returncode == 0 else None

    def reset_to(self, commit: str) -> None:
        """Move the clone back to a verified commit; the commits after it are verified again on pull."""
        with self.lock():
            self._restore(commit)
            self._set_state()

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

    def pull(self, verify: Callable[[str, dict[str, Any]], bool],
             advanced: Callable[[str], None] | None = None) -> str | None:
        """Fetch, then verify every new remote commit in order; the working tree advances only to
        the last accepted commit, and advanced(commit) runs after each move (where the caller saves
        its checkpoint, so a checkpoint is never ahead of the clone). On refusal raise RefusedCommit."""
        with self.lock():
            return self._pull(verify, advanced)

    def _pull(self, verify: Callable[[str, dict[str, Any]], bool],
              advanced: Callable[[str], None] | None) -> str | None:
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
            if not self._shape_ok(commit):
                self._refuse(commit, "commit-shape")
            code = oid = None
            try:
                accepted = verify(commit, self._changed_files(commit))
            except Exception as error:  # noqa: BLE001 - any failure refuses; only its fixed code is kept
                accepted, (code, oid) = False, refusal_of(error)
            if accepted is not True:
                self._refuse(commit, code, oid)
            self._advance(commit)
            if advanced is not None:
                advanced(commit)
        self._set_state()
        return self.head()

    def _shape_ok(self, commit: str) -> bool:
        """One parent at most, and a subject from the allowed set (a subject could expose an entry
        or service name)."""
        return (len(self._out("rev-list", "--parents", "-n", "1", commit).split()) <= 2
                and self._out("log", "-1", "--format=%B", commit).strip() in ALLOWED_MESSAGES)

    def local_commits(self, start: str | None) -> list[str]:
        """The clone's commits after start, oldest first, for a process that holds the state at
        start while another process on this computer moved the clone (plan section G). They are
        not confirmed: the caller verifies each one and follows none past its checkpoint on disk
        unless settle_failed_write finds it on the remote (plan section J). A clone that does not
        contain start, or a commit of the wrong shape, is refused here without marking the clone
        refused for other processes."""
        head = self.head()
        if start is None or head is None or not self._is_ancestor(start, head):
            raise SecretStoreError("the local copy does not follow from the state this process holds; "
                                   "open the store again")
        commits = self._out("rev-list", "--reverse", "--topo-order", f"{start}..{head}").split()
        for commit in commits:
            if not self._shape_ok(commit):
                raise RefusedCommit(commit, "commit-shape")
        return commits

    def _refuse(self, commit: str, code: str | None = None, oid: str | None = None) -> None:
        refused = RefusedCommit(commit, code, oid)
        self._set_state(refused=commit, code=refused.code, **({"object": refused.oid} if refused.oid else {}))
        raise refused

    def _changed_files(self, commit: str) -> dict[str, Any]:
        raw = self._git("diff-tree", "--root", "--no-commit-id", "-r", "-z", "--name-status",
                        "--no-renames", commit).stdout.decode("utf-8")
        fields = [f for f in raw.split("\0") if f]
        files: dict[str, Any] = {}
        for status, name in zip(fields[0::2], fields[1::2]):
            blob = None if status == "D" else self._git("cat-file", "blob", f"{commit}:{name}").stdout
            if name == GITATTRIBUTES:
                if blob != GITATTRIBUTES_BYTES:
                    raise RuleRefusal(".gitattributes changed", "commit-attributes")
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

    commit_started = False  # this write created git commit's child, or may have (plan R11 rule 1, R15 fix 2)

    def _run_commit(self, message: str) -> subprocess.CompletedProcess:
        """Launch git commit: the only place that does. commit_started is set by the statement right
        after the child is created. An OSError from the launch (no child was created) leaves it unset;
        any other exception out of the launch (an interrupt while it is under way, or between the
        child's creation and the mark) sets it, since the launch may have happened. An exception while
        the output is collected ends the child as subprocess.run does; the mark stays set."""
        command = ["git", "commit", "--quiet", "--no-verify", "-m", message]
        try:
            child = subprocess.Popen(command, cwd=str(self.path), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.commit_started = True
        except OSError:
            raise
        except BaseException:
            self.commit_started = True
            raise
        with child:
            try:
                stdout, stderr = child.communicate()
            except BaseException:
                child.kill()  # Popen's exit waits for it
                raise
            returncode = child.poll()
        return subprocess.CompletedProcess(command, returncode, stdout, stderr)

    def write(self, change: dict[str, Any], message: str, expected_parent: Any = _ANY) -> "str | Conflict":
        """One change, one commit on the verified remote head, pushed without force. With
        expected_parent (the head the change was built and verified on), refuse when the head moved.
        commit_started is cleared here and set only by _run_commit, once git commit's child was
        created or may have been (after the head, refusal and fetch checks and the staging); this
        write never clears it again, so a commit that exists, or may, is never unknown to the caller,
        whatever interrupts it, and a commit whose child was never created is never taken for one."""
        self.commit_started = False
        if message not in ALLOWED_MESSAGES:
            raise SecretStoreError("commit message is not in the allowed set")
        if not change:
            raise SecretStoreError("an empty change is refused")
        for name in change:
            parts = Path(name).parts
            if name == GITATTRIBUTES or not parts or ".." in parts or ".git" in parts or Path(name).is_absolute():
                raise SecretStoreError("change path is not allowed")
        with self.lock():
            if expected_parent is not _ANY and self.head() != expected_parent:
                raise MovedHead("the local copy moved since this change was built and verified; refusing to write it")
            if self._state().get("refused"):
                raise SecretStoreError("a remote commit was refused; resolve it before writing")
            remote = self._fetch()
            local = self.head()
            if remote != local:
                if remote is not None and (local is None or self._is_ancestor(local, remote)):
                    return Conflict(remote)
                raise SecretStoreError("local head is not the verified remote head")
            blobs = {name: canonical.dumps(value) for name, value in change.items() if value is not None}
            self._clean(local)  # nothing staged or loose may ride along with the declared files
            try:
                self._stage(change, blobs, local)
                commit_result = self._run_commit(message)
            except BaseException:
                self._clean(local)
                raise
            if commit_result.returncode != 0:
                self._clean(local)
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

    def _clean(self, local: str | None) -> None:
        """Index and working tree exactly at the verified head local (or empty): anything staged or
        loose is dropped, then the state is proved clean."""
        if local is None:
            self._git("read-tree", "--empty")
        else:
            self._git("reset", "--quiet", "--hard", local)
        self._git("clean", "-fdq")
        if self._out("status", "--porcelain", "--untracked-files=all").strip():
            raise SecretStoreError("the local copy holds changes that cannot be removed; nothing was written")

    def _stage(self, change: dict[str, Any], blobs: dict[str, bytes], local: str | None) -> None:
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

    def settle_failed_write(self, before: str | None) -> str | None:
        """After write raised, or a writer in another process crashed (plan section J): the local
        head when the fetched remote branch holds it (the push landed and only its acknowledgement
        or the writer's checkpoint was lost; the remote may have moved on since); otherwise, and
        when the fetch fails, None, with any local commit dropped back to before, so nothing
        unconfirmed stays ahead of the checkpoint."""
        with self.lock():
            local = self.head()
            if local is None or local == before:
                return None
            try:
                remote = self._fetch()
            except SecretStoreError:
                remote = None
            if remote is not None and (remote == local or self._is_ancestor(local, remote)):
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
        state = self._state()
        refused = state.get("refused")
        if refused:
            commit = refused if isinstance(refused, str) and _COMMIT_ID.fullmatch(refused) else "(unknown)"
            return (f"Refused at commit {commit}: a remote change failed verification "
                    f"({refusal_text(state.get('code'), state.get('object'))}); nothing after it is used.")
        try:
            with self.lock():  # never races a write or pull on refs/remotes/origin/main
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
