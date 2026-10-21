"""Setup runs only from the shared checkout, never from a session copy.

  python shared/skills/repository-preflight/scripts/setup_guard.py [<setup command to name>]

Setup scripts find the brain by walking up from their own location, so one run from a session copy
installs the vault, login items and scheduled tasks pointing at that copy, and they break when the
copy is removed (SMART-RULE-0038 keeps session copies short-lived). A session copy is a linked Git
worktree of the mechanics: its own git directory differs from the common one, the same test
session.py uses to find the shared checkout.

Prints nothing and exits 0 in the shared checkout or in a brain that is not a Git checkout. In a
session copy it prints the shared checkout's path (`brain_root` in /memory/OWNER.md when that names
a brain, otherwise the checkout the copy belongs to) and the command to run there, and exits 1.
A setup script in Python calls `refuse_session_copy(Path(__file__))` before it changes anything.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import session  # noqa: E402  (one canonical test for the shared checkout: session.shared_root)

DEFAULT_COMMAND = "python shared/skills/repository-preflight/scripts/setup_guard.py"


def owner_brain_root(shared: Path) -> Path | None:
    """`brain_root` from the front matter of /memory/OWNER.md, when it names a folder holding the contract."""
    owner = shared / "memory" / "OWNER.md"
    if not owner.is_file():
        return None
    found = re.search(r"^brain_root:\s*(\S.*)$", owner.read_text(encoding="utf-8", errors="replace"), re.M)
    if not found:
        return None
    named = Path(found.group(1).strip().strip("'\""))
    return named if (named / "CONTRACT.md").is_file() else None


def refusal(start: Path, command: str = DEFAULT_COMMAND) -> str | None:
    """The message that stops setup in a session copy, or None where setup may run."""
    root = session.sync.brain_root(start)
    if root is None:
        return None
    top = session.git(root, "rev-parse", "--show-toplevel")
    if top.returncode or Path(top.stdout.strip()).resolve() != root.resolve():
        return None                                      # not a checkout of its own (or inside another repository)
    shared = session.shared_root(root)
    if shared is None or shared.resolve() == root.resolve():
        return None
    target = owner_brain_root(shared) or shared
    return (f"setup: {root} is a session copy, which is removed once its work is merged; anything set up "
            f"from it would point at it and break then (SMART-RULE-0038).\n"
            f"Run setup from the shared checkout instead:\n  cd \"{target}\"; {command}")


def refuse_session_copy(start: Path, command: str = DEFAULT_COMMAND) -> None:
    """Stop a setup script that was started from inside a session copy."""
    message = refusal(start, command)
    if message:
        raise SystemExit(message)


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    message = refusal(Path.cwd(), " ".join(argv) or DEFAULT_COMMAND)
    if message:
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
