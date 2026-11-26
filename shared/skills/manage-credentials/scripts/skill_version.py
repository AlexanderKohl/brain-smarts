"""The version of the credential skill (SMART-RULE-0026) and the check that it moves with the skill.

  python skill_version.py                  the version
  python skill_version.py --verbose        with the commit, the branch and whether the tree has changes
  python skill_version.py --record         after a change: record the version with the files' fingerprint

The version lives in one place, `metadata.version` in SKILL.md (where join-project reads it too).
VERSION-LEDGER.json beside it records that version together with a fingerprint of every file of the
skill, so tests/test_skill_version.py fails when a file changes and the version does not, without
needing Git history (the tests run from a copy that has none). `--record` refuses to record a
changed fingerprint under the version already recorded: bump the version first. Nothing here reads
a credential; it hashes the skill's own code and text."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
LEDGER = SKILL / "VERSION-LEDGER.json"
_VERSION = re.compile(r"^\s+version:\s*([0-9]+\.[0-9]+\.[0-9]+)\s*$", re.MULTILINE)
_SKIPPED_PARTS = {"__pycache__", ".pytest_cache"}


def version() -> str:
    text = (SKILL / "SKILL.md").read_text("utf-8")
    front = text.split("---", 2)[1] if text.startswith("---") else ""
    found = _VERSION.search(front)
    if not found:
        raise SystemExit("SKILL.md states no metadata.version")
    return found.group(1)


def product_files() -> list[Path]:
    """Every file of the skill but the ledger and caches, in a fixed order."""
    return sorted(path for path in SKILL.rglob("*")
                  if path.is_file() and path != LEDGER and not _SKIPPED_PARTS & set(path.parts)
                  and path.suffix != ".pyc")


def fingerprint() -> str:
    """SHA-256 over each file's path and its bytes with line endings made LF, so a checkout that turns
    LF into CRLF has the same fingerprint."""
    digest = hashlib.sha256()
    for path in product_files():
        digest.update(path.relative_to(SKILL).as_posix().encode("utf-8") + b"\0")
        digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()


def recorded() -> dict:
    return json.loads(LEDGER.read_text("utf-8")) if LEDGER.is_file() else {}


def committed() -> dict:
    """The ledger as the last commit holds it (a change may be recorded several times before it is
    committed); the file itself when there is no Git checkout."""
    import child_process
    path = LEDGER.relative_to(SKILL.parent.parent.parent).as_posix()
    if child_process.run(["git", "-C", str(SKILL), "rev-parse", "HEAD"], capture_output=True).returncode != 0:
        return recorded()  # no Git checkout
    result = child_process.run(["git", "-C", str(SKILL), "show", f"HEAD:{path}"], capture_output=True)
    if result.returncode != 0:
        return {}  # no ledger committed yet
    try:
        return json.loads(result.stdout.decode("utf-8"))
    except ValueError:
        return {}


def record() -> str:
    now, ledger, current = version(), committed(), fingerprint()
    if recorded() == {"version": now, "fingerprint": current}:
        return f"{now}: already recorded"
    if ledger.get("version") == now and ledger.get("fingerprint") != current:
        raise SystemExit(f"the skill changed but its version is still {now}: raise metadata.version in SKILL.md "
                         "(SMART-RULE-0026), then record again")
    LEDGER.write_text(json.dumps({"version": now, "fingerprint": current}, indent=2) + "\n", "utf-8")
    return f"{now}: recorded"


def identity(verbose: bool = False) -> str:
    """The version, and with verbose the commit, branch and changed state of the brain checkout."""
    text = f"manage-credentials {version()}"
    if not verbose:
        return text
    import child_process

    def git(*args: str) -> str:
        result = child_process.run(["git", "-C", str(SKILL), *args], capture_output=True)
        return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""
    commit = git("rev-parse", "--short", "HEAD") or "unknown commit"
    branch = git("rev-parse", "--abbrev-ref", "HEAD")
    changed = git("status", "--porcelain", "--", str(SKILL))
    built = git("log", "-1", "--format=%cI")
    parts = [text, f"commit {commit}"] + ([f"branch {branch}"] if branch and branch != "main" else [])
    parts += ([f"committed {built}"] if built else []) + (["with uncommitted changes"] if changed else [])
    return ", ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true", help="add the commit, branch and changed state")
    parser.add_argument("--record", action="store_true", help="record the version with the files' fingerprint")
    args = parser.parse_args(argv)
    print(record() if args.record else identity(args.verbose))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
