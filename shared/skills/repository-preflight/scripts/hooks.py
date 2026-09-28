"""Hooks from one host-neutral list: the brain's own scripts, triggered by Git and by any host that has hooks.

  python shared/skills/repository-preflight/scripts/hooks.py install        git hooks in every brain repository
  python shared/skills/repository-preflight/scripts/hooks.py session-start  what a session does first
  python shared/skills/repository-preflight/scripts/hooks.py pre-commit     run by Git before each commit
  python shared/skills/repository-preflight/scripts/hooks.py pre-compact    the handover reminder

The list is hooks/events.json beside this folder. `.claude/settings.json` at the brain root calls
session-start and pre-compact; a host without hooks follows the same steps from the contract
(SMART-RULE-0007: the behaviour lives in the brain, the host file only triggers it).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EVENTS = HERE.parent / "hooks" / "events.json"
MARK = "brain-hooks"
UNTRACKED = "brain-session-untracked.txt"


def brain_root(start: Path) -> Path:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file() and (folder / "shared").is_dir():
            return folder
    raise SystemExit("brain root not found")


ROOT = brain_root(HERE)


def repositories(root: Path) -> list[Path]:
    return [r for r in (root, root / "library", root / "memory") if (r / ".git").exists()]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout


def git_dir(repo: Path) -> Path:
    return Path(git(repo, "rev-parse", "--absolute-git-dir").strip())


def run(*args: str) -> str:
    result = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", stdin=subprocess.DEVNULL)
    return (result.stdout + result.stderr).strip()


def install() -> list[str]:
    """Write a pre-commit hook in every brain repository; keep any hook already there as pre-commit.local."""
    done = []
    script = Path(__file__).resolve().as_posix()
    for repo in repositories(ROOT):
        # Git reads hooks from the common directory, shared by every worktree of the repository.
        common = Path(git(repo, "rev-parse", "--git-common-dir").strip())
        hooks = (common if common.is_absolute() else repo / common) / "hooks"
        hooks.mkdir(exist_ok=True)
        hook = hooks / "pre-commit"
        if hook.exists() and MARK not in hook.read_text(encoding="utf-8", errors="replace"):
            hook.replace(hooks / "pre-commit.local")
        hook.write_text(f'#!/bin/sh\n# {MARK}: generated from hooks/events.json; do not edit\n'
                        f'if [ -x "$(dirname "$0")/pre-commit.local" ]; then "$(dirname "$0")/pre-commit.local" || exit 1; fi\n'
                        f'exec "{Path(sys.executable).as_posix()}" "{script}" pre-commit\n', encoding="utf-8", newline="\n")
        os.chmod(hook, 0o755)
        done.append(str(repo))
    return done


def session_start() -> str:
    install()
    lines = ["Session start (brain hooks):", run("shared/skills/repository-preflight/scripts/sync.py")]
    for repo in repositories(ROOT):
        untracked = [l[3:] for l in git(repo, "status", "--porcelain", "--untracked-files=all").splitlines()
                     if l.startswith("??")]
        (git_dir(repo) / UNTRACKED).write_text("\n".join(untracked), encoding="utf-8")
        if untracked:
            lines.append(f"{repo.name}: {len(untracked)} untracked file(s) belong to someone else; never commit them: "
                         + ", ".join(untracked[:10]))
    if (ROOT / "memory" / "tasks").is_dir():
        lines.append(run("shared/skills/tasks/scripts/tasks.py", "review"))
    lines.append(run("shared/skills/skill-exchange/scripts/skill_exchange.py", "due"))
    return "\n".join(l for l in lines if l)


def pre_commit(repo: Path) -> int:
    staged = git(repo, "diff", "--cached", "--name-only").split("\n")
    record = git_dir(repo) / UNTRACKED
    foreign = set(record.read_text(encoding="utf-8").splitlines()) if record.is_file() else set()
    swept = sorted(p for p in staged if p and p in foreign)
    if swept:
        print("pre-commit: these files were untracked when the session started and are not this session's "
              "to commit:\n  " + "\n  ".join(swept) + "\nUnstage them: git restore --staged <path>", file=sys.stderr)
        return 1
    check = subprocess.run([sys.executable, str(HERE / "preflight.py")], cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if check.returncode:
        print("pre-commit: the repository preflight fails; fix it before committing:\n" + check.stdout[-3000:],
              file=sys.stderr)
        return 1
    return 0


def host_settings() -> dict:
    """The Claude Code project settings generated from the event list."""
    events = json.loads(EVENTS.read_text(encoding="utf-8"))
    hooks = {}
    for event in events["events"]:
        if event.get("claude_code"):
            hooks[event["claude_code"]] = [{"hooks": [{"type": "command", "command": f"python {event['command']}"}]}]
    return {"hooks": hooks}


def pre_compact() -> str:
    return ("Before the context is compacted: if work is in flight, write the handover now under "
            "`## Handover` in the owning node's STATE.md, with the handover prompt under `## Handover prompt` "
            "in the same file, and commit.")


def main(argv: list[str]) -> int:
    # A Windows console defaults to cp1252; the brain's text is UTF-8.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    command = argv[0] if argv else ""
    if command == "install":
        print("\n".join(install()))
    elif command == "session-start":
        print(session_start())
    elif command == "pre-commit":
        return pre_commit(Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip() or "."))
    elif command == "host-settings":
        target = ROOT / ".claude" / "settings.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(host_settings(), indent=2) + "\n", encoding="utf-8")
        print(target)
    elif command == "pre-compact":
        print(pre_compact())
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
