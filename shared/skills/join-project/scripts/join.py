#!/usr/bin/env python3
"""Join a shared project from its manifest (`brain/JOINING.md`), in this brain's own memory.

    python shared/skills/join-project/scripts/join.py <repository url or cloned path> [--dry-run]
        [--no-sync] [--root <brain root>] [--vault-listing <file>] [--json]

Given a repository URL or a cloned path it:

1. brings the brain repositories up to date (`sync.py`) and checks the contract and skill
   versions the manifest requires, and that each library skill it lists is under `/library/skills/`
   (a missing one is the person's step, with the command that adds it);
2. clones the repository under `project_repos_root` (from `/memory/OWNER.md`) when it is not
   there, and checks out the working branch when the clone is clean;
3. creates the pointer node in this memory from `/shared/templates/project-pointer-README.template.md`,
   or updates its `repo_url`, `local_path` and `default_branch`; it never copies project state,
   rules or knowledge, and names the node in `/memory/projects/README.md`;
4. registers each shared board the manifest lists in this brain's `boards.json`;
5. checks each vault entry the manifest names exists, by name only, through the vault's `list`
   command, and prints the exact command that creates a missing one – never a value;
6. reports the project's task store, `<repository>:brain/tasks` (whether it is there, its open
   and inbox counts, and the open tasks whose owner is this brain's author name), read through
   the tasks skill's store list; and warns when the manifest's `minimum_contract_version` is
   below 3.0.0, the contract under which a project's tasks live in its repository;
7. checks the feedback companion configuration for the manifest's team inbox and prints the
   steps for this person's own pull key;
8. ends with what is ready and what is this person's own step.

`--dry-run` says what it would do and changes nothing. It writes only inside this brain's
memory and the clone, never another owner's memory, never pushes, and never reads or prints a
secret value, a vault field or a `.env` file. Exit code 0 when the manifest was read and every
automatic step is done or would be done; 1 when it could not start (no brain, no manifest, a
failed clone).
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import joining  # noqa: E402  (one implementation of the manifest and "joined", SMART-RULE-0018)
import task_stores  # noqa: E402  (on the path through joining: the tasks skill's stores)
from task_history import author_name, brain_author  # noqa: E402
from task_records import id_sort_key, load_tasks  # noqa: E402

TEMPLATE = Path("shared") / "templates" / "project-pointer-README.template.md"
SYNC = Path("shared") / "skills" / "repository-preflight" / "scripts" / "sync.py"
VAULT = Path("shared") / "skills" / "manage-credentials" / "scripts" / "vault_credentials.py"
COMPANION = Path("memory") / "skills" / "product-feedback" / "config" / "companion.json"
STORE_CONTRACT = (3, 0, 0)   # the first contract under which a project's tasks live in its brain/tasks/


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def brain_root(start: Path) -> Path | None:
    for folder in (start, *start.parents):
        if (folder / "CONTRACT.md").is_file():
            return folder
    return None


def now_stamp() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def version_tuple(text) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", str(text or "")))


def file_version(path: Path, key: str) -> str | None:
    if not path.is_file():
        return None
    meta = joining.front_matter(path.read_text(encoding="utf-8", errors="replace"))
    value = meta.get(key)
    if value is None and isinstance(meta.get("metadata"), dict):
        value = meta["metadata"].get(key)
    return None if value is None else str(value)


class Report:
    """What is ready, what needs this person, and what would change (dry run)."""

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        self.ready: list[str] = []
        self.yours: list[str] = []
        self.changes: list[str] = []
        self.errors: list[str] = []
        self.task_store: dict | None = None

    def done(self, text: str) -> None:
        self.ready.append(text)

    def would(self, text: str) -> None:
        self.changes.append(("would " if self.dry_run else "") + text)

    def own(self, text: str) -> None:
        self.yours.append(text)

    def lines(self) -> list[str]:
        out = []
        for heading, items in (("Ready", self.ready), ("Changed" if not self.dry_run else "Would change", self.changes),
                               ("Your own steps", self.yours), ("Could not continue", self.errors)):
            if items:
                out.append(heading + ":")
                out += ["  - " + item for item in items]
        return out

    def as_dict(self) -> dict:
        data = {"dry_run": self.dry_run, "ready": self.ready, "changes": self.changes,
                "yours": self.yours, "errors": self.errors}
        if self.task_store is not None:
            data["task_store"] = self.task_store
        return data


# -- steps --

def step_sync(root: Path, report: Report, skip: bool) -> None:
    if skip:
        report.done("sync skipped" + (" (dry run)" if report.dry_run else " (--no-sync)"))
        return
    done = subprocess.run([sys.executable, str(root / SYNC), "--no-merge"], cwd=root, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    for line in done.stdout.strip().splitlines():
        (report.done if done.returncode == 0 else report.own)("sync: " + line)


def step_versions(root: Path, manifest: dict, report: Report) -> None:
    wanted = manifest.get("minimum_contract_version")
    have = file_version(root / "CONTRACT.md", "contract_version")
    if wanted:
        if have and version_tuple(have) >= version_tuple(wanted):
            report.done(f"contract {have} (manifest needs {wanted})")
        else:
            report.own(f"bring the brain to contract {wanted} (this copy reads {have or 'none'}): "
                       "python shared/skills/repository-preflight/scripts/sync.py")
    if not wanted or version_tuple(wanted) < STORE_CONTRACT:
        report.own(f"warning: the manifest's minimum_contract_version is {wanted or 'not stated'}, below 3.0.0, "
                   "the contract under which the project's tasks live in its brain/tasks/; a brain on an older "
                   "contract keeps them in its own memory. Ask the project to raise it in brain/JOINING.md")
    for skill in manifest.get("skills") or []:
        if not isinstance(skill, dict) or not skill.get("path"):
            continue
        path = str(skill["path"]).strip("/")
        skill_file = root / path / "SKILL.md"
        minimum = skill.get("minimum_version")
        if not skill_file.is_file():
            report.own(f"skill {skill['path']} is not in this brain; pull the brain or install it "
                       "(/shared/skills/skill-exchange/)")
            continue
        version = file_version(skill_file, "version")
        if not minimum:
            report.done(f"skill {skill['path']} present")
        elif version is None:
            report.own(f"skill {skill['path']} states no version; the manifest needs {minimum} – check it by hand")
        elif version_tuple(version) >= version_tuple(minimum):
            report.done(f"skill {skill['path']} {version} (manifest needs {minimum})")
        else:
            report.own(f"skill {skill['path']} is {version}; the manifest needs {minimum}: pull the brain")
    for name in manifest.get("active_skills") or []:
        active = joining.owner_profile(root / "memory").get("active_skills") or []
        if name in active:
            report.done(f"active skill {name}")
        else:
            report.own(f"list `{name}` under active_skills in /memory/OWNER.md")


def step_library(root: Path, manifest: dict, report: Report) -> None:
    """Each library skill the project needs is checked out under /library/skills/; a missing one is
    the person's step, with the command that adds it (a report, never a failure). A value that is
    not a list of plain skill names is reported as a malformed line of brain/JOINING.md."""
    names, malformed = joining.library_skill_names(manifest)
    for line in malformed:
        report.own("malformed brain/JOINING.md line, skipped: " + line)
    for name in names:
        if (root / "library" / "skills" / name / "SKILL.md").is_file():
            report.done(f"library skill {name} present")
        elif (root / "library" / ".git").exists():
            report.own(f"library skill {name} is not in /library/skills/; pull the skill library: "
                       f"cd \"{root}\"; git -C library pull")
        else:
            report.own(f"library skill {name} is needed but /library/ is not checked out; clone your skill library "
                       f"into it: cd \"{root}\"; git clone <your skill library URL> library")


def step_repository(root: Path, target: str, branch_override: str | None, report: Report) -> Path | None:
    """The clone to work in, cloned if needed (never in a dry run); None when it cannot be had."""
    profile = joining.owner_profile(root / "memory")
    base = Path(str(profile.get("project_repos_root") or root.parent))
    given = Path(target)
    if (given / ".git").exists():          # a clone; a bare repository or a URL is cloned instead
        repo = given.resolve()
    else:
        repo = base / joining.repository_name(target)
        if not repo.is_dir():
            if report.dry_run:
                report.would(f"clone {target} into {repo}")
                report.own("the manifest can be read once the repository is cloned; run again without --dry-run")
                return None
            cloned = git(base, "clone", "--quiet", target, str(repo))
            if cloned.returncode:
                report.errors.append("clone failed: " + (cloned.stderr.strip().splitlines() or ["?"])[-1])
                return None
            report.would(f"cloned {target} into {repo}")
    if not (repo / ".git").exists():
        report.errors.append(f"{repo} is not a Git repository")
        return None
    report.done(f"repository at {repo}")
    return repo


def step_branch(repo: Path, branch: str | None, report: Report) -> None:
    if not branch:
        report.done("the manifest names no working branch; staying on the checked-out branch")
        return
    current = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current == branch:
        report.done(f"on {branch}")
        return
    changed = [line for line in git(repo, "status", "--porcelain").stdout.splitlines() if line and not line.startswith("??")]
    if changed:
        report.own(f"on {current} with {len(changed)} changed file(s); commit or stash them, then: git checkout {branch}")
        return
    if report.dry_run:
        report.would(f"check out {branch} (now on {current})")
        return
    git(repo, "fetch", "--quiet", "origin")
    out = git(repo, "checkout", "--quiet", branch)
    if out.returncode:
        report.own(f"could not check out {branch}: " + (out.stderr.strip().splitlines() or ["?"])[-1])
    else:
        report.would(f"checked out {branch} (was on {current})")


def fill_template(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(key, value)
    return text


def step_pointer(root: Path, repo: Path, manifest: dict, report: Report) -> Path:
    memory = root / "memory"
    slug = str(manifest.get("pointer_node") or repo.name).strip("/").split("/")[-1]
    node = joining.find_pointer(memory, manifest.get("repository"), repo.name) or memory / "projects" / slug
    readme = node / "README.md"
    title = str(manifest.get("project_title") or manifest.get("title") or repo.name)
    branch = str(manifest.get("working_branch") or "main")
    profile = joining.owner_profile(memory)
    if readme.is_file():
        text = readme.read_text(encoding="utf-8")
        wanted = {"repo_url": str(manifest.get("repository") or ""), "local_path": repo.name, "default_branch": branch}
        updated = text
        for key, value in wanted.items():
            if not value:
                continue
            if re.search(rf"^{key}:.*$", updated, re.M):
                updated = re.sub(rf"^{key}:.*$", f"{key}: {value}", updated, count=1, flags=re.M)
            else:
                updated = re.sub(r"^(default_branch|repo_url|local_path|owner):.*$", lambda m: m.group(0) + f"\n{key}: {value}",
                                 updated, count=1, flags=re.M)
        if updated == text:
            report.done(f"pointer node {rel(root, node)} already names this repository")
        else:
            updated = re.sub(r"^updated:.*$", "updated: " + now_stamp(), updated, count=1, flags=re.M)
            report.would(f"update repo_url, local_path and default_branch in {rel(root, readme)}")
            if not report.dry_run:
                readme.write_text(updated, encoding="utf-8")
        return node
    template = root / TEMPLATE
    if not template.is_file():
        report.own(f"create the pointer node {rel(root, node)} by hand: the template {TEMPLATE.as_posix()} is missing")
        return node
    stamp = now_stamp()
    text = fill_template(template.read_text(encoding="utf-8"), {
        "id: PROJECT-ID-pointer-readme": f"id: {slug}-pointer-readme",
        "PROJECT TITLE": title,
        "created: YYYY-MM-DDTHH:mm:ss+HH:MM": "created: " + stamp,
        "updated: YYYY-MM-DDTHH:mm:ss+HH:MM": "updated: " + stamp,
        "owner: OWNER": "owner: " + str(profile.get("owner_short_name") or "brain-owner"),
        "repo_url: https://github.com/ACCOUNT/REPOSITORY": "repo_url: " + str(manifest.get("repository") or ""),
        "local_path: REPOSITORY": "local_path: " + repo.name,
        "default_branch: main": "default_branch: " + branch,
    })
    report.would(f"create the pointer node {rel(root, readme)} from the template (no project state copied)")
    report.own(f"fill the External systems row and the CONTRACT 7.1 answers in {rel(root, readme)}")
    if not report.dry_run:
        node.mkdir(parents=True, exist_ok=True)
        readme.write_text(text, encoding="utf-8")
    parent = memory / "projects" / "README.md"
    if parent.is_file():
        ptext = parent.read_text(encoding="utf-8")
        if f"##### `{slug}/`" in ptext:
            report.done(f"{rel(root, parent)} already names {slug}/")
        else:
            entry = (f"##### `{slug}/`\n\nContains the pointer node (CONTRACT section 16.1) for {title}, made by "
                     f"join-project from `{repo.name}:brain/JOINING.md`.\n\n")
            report.would(f"name {slug}/ under Folders in {rel(root, parent)}")
            if not report.dry_run:
                parent.write_text(insert_folder(ptext, slug, entry), encoding="utf-8")
    else:
        report.own(f"name {slug}/ in the Folders section of /memory/projects/README.md")
    return node


def insert_folder(text: str, slug: str, entry: str) -> str:
    """Put the entry among the `##### ` folder headings in name order, or at the end."""
    headings = list(re.finditer(r"^##### `([^`]+)/`\n", text, re.M))
    for match in headings:
        if match.group(1) > slug:
            return text[:match.start()] + entry + text[match.start():]
    if not text.endswith("\n"):
        text += "\n"
    return text + "\n" + entry.rstrip("\n") + "\n"


def step_boards(root: Path, repo: Path, manifest: dict, node: Path, report: Report) -> None:
    boards = [b for b in manifest.get("boards") or [] if isinstance(b, dict) and b.get("id")]
    if not boards:
        report.done("the manifest lists no shared board")
        return
    config = root / joining.BOARDS_CONFIG
    if not config.is_file():
        report.own("set up the owner board first (/shared/skills/owner-board/SKILL.md, Configuration), then run again "
                   "to register: " + ", ".join(str(b["id"]) for b in boards))
        return
    data = json.loads(config.read_text(encoding="utf-8"))
    registered = {str(b.get("id")): b for b in data.get("boards", []) if isinstance(b, dict)}
    changed = False
    for board in boards:
        bid, status = str(board["id"]), joining.expected_status(repo.name, board)
        have = registered.get(bid)
        if have is None:
            data.setdefault("boards", []).append({"id": bid, "label": str(board.get("label") or bid), "status": status,
                                                  "node": "/memory/" + node.relative_to(root / "memory").as_posix()})
            report.would(f"register board {bid} as {status} in {rel(root, config)}")
            changed = True
        elif str(have.get("status")) == status:
            report.done(f"board {bid} registered")
        else:
            report.own(f"board {bid} is registered as {have.get('status')} but the manifest expects {status}; "
                       "decide which, by hand")
    if changed and not report.dry_run:
        config.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def repository_store(root: Path, repo: Path, manifest: dict) -> task_stores.Store:
    """The repository's task store as the tasks skill lists it; built from the clone when this
    brain's pointer does not name the clone yet (a dry run, or a pointer to another folder)."""
    name = task_stores.repository_name(str(manifest.get("repository") or repo.name))
    for store in task_stores.stores(root):
        if (store.kind == "repository" and store.repository == name and store.checkout is not None
                and store.checkout.resolve() == repo.resolve()):
            return store
    return task_stores.Store(kind="repository", path=repo / "brain" / "tasks", node=None, repository=name,
                             checkout=repo, branch=str(manifest.get("working_branch") or "") or None)


def step_tasks(root: Path, repo: Path, manifest: dict, report: Report) -> None:
    """Report the project's task store: there or not, open and inbox counts, this person's own
    open tasks (owner, as an author name, equal to this brain's). Read only, dry run or not."""
    store = repository_store(root, repo, manifest)
    label = store.label
    summary = {"label": label, "present": store.path.is_dir(), "open": 0, "inbox": 0, "yours": [], "problems": []}
    report.task_store = summary
    if not store.path.is_dir():
        report.done(f"task store {label}: not there yet (no brain/tasks/ in {repo.name}); the project's first "
                    "task creates it")
        return
    tasks = load_tasks(store.path, owner=store)
    summary["open"] = sum(1 for t in tasks if t.folder in ("open", "recurring") and not t.problem)
    summary["inbox"] = sum(1 for t in tasks if t.folder == "inbox" and not t.problem)
    report.done(f"task store {label}: {summary['open']} open, {summary['inbox']} in the inbox "
                f"(read {repo.name}:brain/tasks/STATE.md)")
    for task in tasks:
        if task.problem:
            summary["problems"].append(f"{rel(root, task.path)}: {task.problem}")
            report.own(f"task record {task.path.relative_to(repo).as_posix()} in {repo.name}: {task.problem}")
    try:
        author = brain_author(root)
    except ValueError as err:
        report.own(f"your own tasks in {label} cannot be picked out: {err}")
        return
    mine = sorted((t for t in tasks if t.folder != "completed" and not t.problem
                   and author_name(t.get("owner") or "") == author), key=lambda t: id_sort_key(t.tid))
    summary["yours"] = [{"id": t.tid, "status": t.get("status"), "title": t.get("title")} for t in mine]
    if mine:
        report.own(f"your {len(mine)} open task(s) in {label}: "
                   + "; ".join(f"{t.tid} ({t.get('status')}) {t.get('title')}" for t in mine))
    else:
        report.done(f"no open task in {label} is yours ({author})")


def vault_names(root: Path, listing: Path | None, report: Report) -> set[str] | None:
    """Entry names only, from a listing file (tests) or the vault's `list`; None when unavailable."""
    if listing is not None:
        return {line.strip() for line in listing.read_text(encoding="utf-8").splitlines() if line.strip()}
    script = root / VAULT
    if not script.is_file():
        report.own("the credential vault skill is not in this brain (/shared/skills/manage-credentials/)")
        return None
    done = subprocess.run([sys.executable, str(script), "list"], cwd=root, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode:
        report.own("the vault could not be listed (locked, or not initialised: vault_credentials.py init); "
                   "entries are checked once it is unlocked")
        return None
    names = set()
    for line in done.stdout.splitlines():
        line = line.strip()
        if line and not re.match(r"^\d+\s", line) and not line.lower().endswith("entries") and " " not in line:
            names.add(line)
    return names


def step_vault(root: Path, manifest: dict, listing: Path | None, report: Report) -> None:
    entries = [e for e in manifest.get("vault_entries") or [] if isinstance(e, dict) and e.get("entry")]
    if not entries:
        report.done("the manifest names no vault entry")
        return
    names = vault_names(root, listing, report)
    for entry in entries:
        name = str(entry["entry"])
        fields = [str(f) for f in (entry.get("fields") or [])]
        command = f"python {VAULT.as_posix()} put-entry --entry {name}" + "".join(f" --secret {f}" for f in fields)
        if names is not None and name in names:
            report.done(f"vault entry {name} exists")
        else:
            why = str(entry.get("purpose") or "")
            report.own(f"create your own vault entry {name}" + (f" ({why})" if why else "") +
                       f" – each value is typed at the hidden prompt, never on the command line: {command}")


def step_feedback(root: Path, manifest: dict, report: Report) -> None:
    feedback = manifest.get("feedback")
    if not isinstance(feedback, dict) or not feedback.get("inbox_url"):
        report.done("the manifest names no feedback inbox")
        return
    inbox = str(feedback["inbox_url"])
    entry = str(feedback.get("vault_entry") or "")
    config = root / COMPANION
    if not config.is_file():
        report.own(f"set up the Brain Feedback companion (/library/skills/product-feedback/SKILL.md, Joining a team inbox) "
                   f"with inbox_url {inbox}" + (f" and inbox_vault_entry {entry}" if entry else ""))
    else:
        data = json.loads(config.read_text(encoding="utf-8"))
        if str(data.get("inbox_url") or "").rstrip("/") != inbox.rstrip("/"):
            report.own(f"set inbox_url to {inbox} in {rel(root, config)}")
        elif entry and str(data.get("inbox_vault_entry") or "") != entry:
            report.own(f"set inbox_vault_entry to {entry} in {rel(root, config)}")
        else:
            report.done(f"companion configured for {inbox}")
    page = str(feedback.get("key_page") or "the product's admin feedback page")
    report.own(f"your own pull key: an admin of the product makes it on {page} (New pull key), you store it under "
               f"the vault entry {entry or 'named by the manifest'} field pull_key, then run companion.py pull – "
               "the key is yours; never send it to anyone or put it in a file")


def step_read_first(repo: Path, manifest: dict, report: Report) -> None:
    for item in manifest.get("read_first") or []:
        report.own(f"read {repo.name}:{item}")


def rel(root: Path, path: Path) -> str:
    try:
        return "/" + path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", help="repository URL, or the path of a clone")
    parser.add_argument("--dry-run", action="store_true", help="say what would be done; change nothing")
    parser.add_argument("--no-sync", action="store_true", help="do not run sync.py first")
    parser.add_argument("--root", type=Path, default=None, help="the brain root (default: found from here)")
    parser.add_argument("--branch", default=None, help="working branch, overriding the manifest")
    parser.add_argument("--vault-listing", type=Path, default=None,
                        help="a file with one vault entry name per line, instead of the vault's `list` (tests)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    root = args.root or brain_root(Path.cwd()) or brain_root(Path(__file__).resolve().parent)
    report = Report(args.dry_run)
    if root is None or not (root / "memory" / "OWNER.md").is_file():
        report.errors.append("a brain root with /memory/OWNER.md is needed; run inside your brain")
        return finish(report, args.json)
    step_sync(root, report, skip=args.no_sync or args.dry_run)
    repo = step_repository(root, args.target, args.branch, report)
    if repo is None:
        return finish(report, args.json)
    manifest = joining.load_manifest(repo)
    if manifest is None:
        report.errors.append(f"{repo.name} has no brain/JOINING.md; it is not set up for joining")
        return finish(report, args.json)
    if "error" in manifest:
        report.errors.append(f"{repo.name}:brain/JOINING.md – " + manifest["error"])
        return finish(report, args.json)
    step_versions(root, manifest, report)
    step_library(root, manifest, report)
    step_branch(repo, args.branch or manifest.get("working_branch"), report)
    node = step_pointer(root, repo, manifest, report)
    step_boards(root, repo, manifest, node, report)
    step_tasks(root, repo, manifest, report)
    step_vault(root, manifest, args.vault_listing, report)
    step_feedback(root, manifest, report)
    step_read_first(repo, manifest, report)
    return finish(report, args.json)


def finish(report: Report, as_json: bool) -> int:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
    else:
        print("\n".join(report.lines()))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
