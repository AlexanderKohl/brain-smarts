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
# SMART-RULE-0038: set to 1 for a commit made on purpose in the shared checkout.
SHARED_CHECKOUT = "BRAIN_SHARED_CHECKOUT"


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
    """Switch on each present repository's own versioned hooks: core.hooksPath = .githooks (relative).

    Relative, so it survives moves, worktrees and session copies; per repository, so a repository
    cloned on its own keeps working. Git never copies this setting with a clone, so it is run once
    per checkout (session.py start runs it for every session copy).
    """
    done = []
    for repo in repositories(ROOT):
        if (repo / ".githooks" / "pre-commit").is_file():
            git(repo, "config", "core.hooksPath", ".githooks")
            done.append(str(repo))
    return done


def layer_of(repo: Path, root: Path) -> str:
    return "memory" if repo.name == "memory" and repo.parent == root else (
        "library" if repo.name == "library" and repo.parent == root else "mechanics")


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


def shared_checkout_refusal(repo: Path) -> str | None:
    """SMART-RULE-0038: a commit on `main` in a repository's own working tree – the shared checkout –
    is refused. Session copies are linked worktrees on their own branches, so their commits pass."""
    if os.environ.get(SHARED_CHECKOUT) == "1":
        return None
    own = os.path.normcase(git(repo, "rev-parse", "--path-format=absolute", "--git-dir").strip())
    common = os.path.normcase(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    if not own or own != common or git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip() != "main":
        return None
    return ("pre-commit: this is the shared checkout, which holds only merged work (SMART-RULE-0038).\n"
            "Work in a session copy: python shared/skills/repository-preflight/scripts/session.py start <name>\n"
            f"A host that cannot work in a separate folder sets {SHARED_CHECKOUT}=1 for its commits.")


def pre_commit(repo: Path) -> int:
    """The brain's checks for one commit, scoped to the repository being committed."""
    staged = git(repo, "diff", "--cached", "--name-only").split("\n")
    record = git_dir(repo) / UNTRACKED
    foreign = set(record.read_text(encoding="utf-8").splitlines()) if record.is_file() else set()
    swept = sorted(p for p in staged if p and p in foreign)
    if swept:
        print("pre-commit: these files were untracked when the session started and are not this session's "
              "to commit:\n  " + "\n  ".join(swept) + "\nUnstage them: git restore --staged <path>", file=sys.stderr)
        return 1
    root = brain_root_above(repo)
    if root is None:
        print("pre-commit: no brain above this repository; brain checks skipped", file=sys.stderr)
        return 0
    refusal = shared_checkout_refusal(repo)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    layer = layer_of(repo, root)
    check = subprocess.run([sys.executable, str(root / "shared/skills/repository-preflight/scripts/preflight.py"),
                            "--root", str(root), "--layer", layer], cwd=root, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    if check.returncode:
        print(f"pre-commit: the repository preflight fails for {layer}; fix it before committing:\n"
              + check.stdout[-3000:], file=sys.stderr)
        return 1
    return 0


def brain_root_above(start: Path) -> Path | None:
    for folder in [start, *start.parents]:
        if (folder / "CONTRACT.md").is_file() and (folder / "shared").is_dir():
            return folder
    return None


# SMART-RULE-0009: every commit names its tool and its model in these trailers, never in the subject.
TRAILERS = ("Tool", "Co-Authored-By")


def missing_trailers(repo: Path, message_file: Path) -> list[str]:
    """The trailers a commit message lacks. A merge makes no change of its own and needs none."""
    if (git_dir(repo) / "MERGE_HEAD").exists():
        return []
    parsed = subprocess.run(["git", "interpret-trailers", "--parse", str(message_file)], cwd=repo,
                            capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    keys = {line.split(":", 1)[0].strip().lower() for line in parsed.splitlines() if ":" in line}
    return [name for name in TRAILERS if name.lower() not in keys]


def commit_msg(repo: Path, message_file: Path) -> int:
    """A commit message names its tool and model in trailers (SMART-RULE-0009), in every brain
    repository; in a shareable repository it also holds no personal data (SMART-RULE-0008).

    Uses the preflight's own personal-data patterns and the owner's terms read from memory. The
    Co-Authored-By trailer names the tool, not the owner, and is skipped.
    """
    root = brain_root_above(repo)
    if root is None:
        return 0
    missing = missing_trailers(repo, message_file)
    if missing:
        print("commit-msg: the message lacks the trailer(s) " + ", ".join(f"{m}:" for m in missing)
              + ". Name the tool and the model in trailers, not the subject (SMART-RULE-0009), for example:\n\n"
              "    Tool: Claude Code desktop\n    Co-Authored-By: Claude Opus 5.5 <the host's no-reply address>",
              file=sys.stderr)
        return 1
    if layer_of(repo, root) == "memory":
        return 0
    import tempfile
    sys.path.insert(0, str(root / "shared/skills/repository-preflight/scripts"))
    import personal_data
    lines = [l for l in message_file.read_text(encoding="utf-8", errors="replace").splitlines()
             if not l.startswith(("Co-Authored-By:", "#"))]
    with tempfile.TemporaryDirectory() as d:
        probe = Path(d) / "message.md"
        probe.write_text("\n".join(lines) + "\n", encoding="utf-8")
        hits = personal_data.scan([probe], personal_data.owner_terms(root))
    if hits:
        kinds = ", ".join(sorted({kind for _f, _l, kind, _v in hits}))
        print(f"commit-msg: the message holds personal data ({kinds}); say \"the owner\" and keep "
              f"names, addresses and identifiers out of shareable repositories (SMART-RULE-0008)", file=sys.stderr)
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
    elif command == "commit-msg":
        return commit_msg(Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip() or "."), Path(argv[1]))
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
