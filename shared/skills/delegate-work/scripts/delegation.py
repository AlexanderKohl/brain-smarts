#!/usr/bin/env python3
"""Create, dispatch and validate delegated-work packets for the Portable AI Brain.

A run is one fan-out from a conductor agent to one or more worker agents. Everything a run
produces lives under /temp/delegation/runs/<RUN-ID>/ and is ephemeral instrumentation, not a
task record. The conductor routes durable outcomes under CONTRACT sections 5 and 6.

Commands
  new-run          --title T --why-parallel TEXT [--parent ID] [--max-workers N]
                   [--plan PATH]  (an approved build plan: --max-workers may then be 1 to 8)
                   [--trial-workers 5-8 --trial-reason TEXT]  (MEMORY-RULE-0005 trial run; not with --plan)
  new-packet       --run RUN --title T --objective TEXT [--context PATH ...]
                   [--context-mode isolated|fork] [--fork-reason TEXT]
                   [--writes none|worktree|paths] [--path PATH ...]
                   [--external none|read|write] [--target TEXT]
                   [--model NAME] [--effort LEVEL] [--model-reason TEXT] [--max-tool-calls N] [--max-output-words N]
                   [--acceptance TEXT ...] [--exclude TEXT ...]
  dispatch-prompt  --run RUN --packet W01
  validate-result  --run RUN [--packet W01]
  check-writes     --run RUN [--mine PATH ...]
  summarise        --run RUN
  close-run        --run RUN --status synthesised|abandoned --host TEXT --parallel yes|no
  checkpoint-done  --session ID   (the handover checkpoint is committed; clears the compaction marker)

new-run, new-packet and close-run take exactly one of --context-tokens N | --context-unknown REASON;
new-run and new-packet also take --owner-override REASON and --session ID (see context_guard.py).
Common options: --root PATH (otherwise discovered upward from the current directory by finding
CONTRACT.md) and --now ISO-8601 (tests only). Standard library only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import context_guard

SKILL_PATH = "/shared/skills/delegate-work"
RUNS_SUBDIR = Path("temp") / "delegation" / "runs"
DEFAULT_MAX_WORKERS = 4
HARD_MAX_WORKERS = 4
# A run named on an approved build plan (--plan) may hold up to eight workers (SMART-RULE-0024).
PLAN_MAX_WORKERS = 8
# A run marked as the measured trial of MEMORY-RULE-0005 may hold five to eight workers.
TRIAL_MIN_WORKERS = 5
TRIAL_MAX_WORKERS = 8
RESULT_STATUSES = {"pending", "completed", "failed", "blocked"}
CONTEXT_MODES = {"isolated", "fork"}
WRITE_MODES = {"none", "worktree", "paths"}
EXTERNAL_MODES = {"none", "read", "write"}
REQUIRED_RESULT_SECTIONS = [
    "Summary",
    "Conclusion",
    "Verified",
    "Assumed or unverified",
    "Negative findings",
    "Sources",
    "Facts to route",
    "Open questions",
    "Suggested tasks",
]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bBearer [A-Za-z0-9\-_.]{20,}"),
    re.compile(r"PORTABLE_VAULT_PASSPHRASE\s*="),
    re.compile(r"(?i)\b(passphrase|password|client_secret|api[_-]?key)\s*[:=]\s*[^\s'\"]{12,}"),
]


# ---------------------------------------------------------------- helpers


def now_stamp(override: str | None) -> str:
    if override:
        return override
    local = datetime.now().astimezone()
    offset = local.utcoffset() or timedelta(0)
    sign = "+" if offset >= timedelta(0) else "-"
    total = abs(int(offset.total_seconds()))
    return local.strftime("%Y-%m-%dT%H:%M:%S") + f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def discover_root(explicit: str | None) -> Path:
    if explicit:
        root = Path(explicit).resolve()
        if not (root / "CONTRACT.md").exists():
            raise SystemExit(f"error: {root} does not contain CONTRACT.md")
        return root
    current = Path.cwd().resolve()
    for candidate in (current, *current.parents):
        if (candidate / "CONTRACT.md").exists():
            return candidate
    raise SystemExit("error: CONTRACT.md not found upward from the current directory")


def root_path(path: Path, root: Path) -> str:
    return "/" + path.resolve().relative_to(root.resolve()).as_posix()


def parse_front_matter(text: str) -> tuple[dict, str]:
    """Parse the YAML subset this skill writes: scalars, flat lists and one-level mappings."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    block = text[4:end]
    body = text[end + 4:]
    data: dict = {}
    key = None
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("  - ") and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(unquote(line[4:].strip()))
            continue
        if line.startswith("  ") and ":" in line and key is not None:
            if not isinstance(data.get(key), dict):
                data[key] = {}
            sub, _, raw = line.strip().partition(":")
            raw = raw.strip()
            data[key][sub.strip()] = None if raw == "null" else unquote(raw)
            continue
        if ":" in line and not line.startswith(" "):
            key, _, raw = line.partition(":")
            key = key.strip()
            raw = raw.strip()
            if raw in ("[]", ""):
                data[key] = []
            elif raw == "null":
                data[key] = None
            else:
                data[key] = unquote(raw)
    return data, body.lstrip("\n")


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def quote(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in ":#'\"[]{}") or text != text.strip():
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return text


def render_front_matter(fields: dict) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if isinstance(value, dict):
            lines.append(f"{key}:")
            lines.extend(f"  {sub}: {quote(item)}" for sub, item in value.items())
        elif isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {quote(item)}" for item in value)
        else:
            lines.append(f"{key}: {quote(value)}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def template_body(root: Path, name: str) -> str:
    path = root / SKILL_PATH.lstrip("/") / "templates" / name
    _, body = parse_front_matter(path.read_text(encoding="utf-8"))
    return body


def sections(body: str) -> dict[str, str]:
    """Map '## Heading' -> content until the next '## ' heading."""
    found: dict[str, str] = {}
    current = None
    buffer: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current is not None:
                found[current] = "\n".join(buffer).strip()
            current = line[3:].strip()
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        found[current] = "\n".join(buffer).strip()
    return found


def has_content(text: str, template_text: str = "") -> bool:
    """True when a section holds more than the template's own explanatory prose."""
    if template_text:
        text = text.replace(template_text.strip(), "")
    for line in text.splitlines():
        stripped = line.strip().strip("-*_ ").lower()
        if stripped and stripped not in {"none", "n/a", "tbd", "todo"}:
            return True
    return False


def within(path: Path, scope: Path) -> bool:
    """True when `path` is `scope` or lies inside it (both already resolved)."""
    return path == scope or scope in path.parents


def brain_changes(root: Path) -> list[str]:
    """Every changed or untracked file in the brain's repositories, as repository-root paths.

    Read from Git rather than from any worker's report (SMART-RULE-0038): the mechanics at the
    root, and the library and memory beneath it when they are repositories. Local scratch under
    /temp/ is not a repository write.
    """
    found: list[str] = []
    for repo in (root, root / "library", root / "memory"):
        if not (repo / ".git").exists():
            continue
        done = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "-z", "--untracked-files=all"],
                              capture_output=True, text=True, encoding="utf-8")
        if done.returncode:
            continue
        entries = done.stdout.split("\0")
        skip_next = False
        for entry in entries:
            if skip_next:          # the source path of a rename or copy
                skip_next = False
                continue
            if len(entry) < 4:
                continue
            skip_next = entry[0] in "RC"
            path = (repo / entry[3:]).resolve()
            if within(path, (root / "temp").resolve()):
                continue
            found.append(root_path(path, root))
    return sorted(set(found))


def run_dir(root: Path, run_id: str) -> Path:
    path = root / RUNS_SUBDIR / run_id
    if not (path / "RUN.md").exists():
        raise SystemExit(f"error: run {run_id} not found under /{RUNS_SUBDIR.as_posix()}")
    return path


def load(path: Path) -> tuple[dict, str]:
    return parse_front_matter(path.read_text(encoding="utf-8"))


def packet_files(run: Path) -> list[Path]:
    return sorted(p for p in run.glob("W??.md"))


def write(path: Path, fields: dict, body: str) -> None:
    path.write_text(render_front_matter(fields) + "\n" + body.rstrip("\n") + "\n", encoding="utf-8")


def touch_updated(path: Path, stamp: str, **changes) -> None:
    fields, body = load(path)
    fields.update(changes)
    fields["updated"] = stamp
    write(path, fields, body)


def bullets(items) -> str:
    return "\n".join(f"- {item}" for item in (items or []))


FACT_OUTPUT_LIMIT = 1500


def verify_facts(specs, root: Path, stamp: str) -> tuple[list[dict], str]:
    """Run each `label=command` (or bare command) now and return the records and their Markdown.

    A packet may only quote facts the conductor verified in the same session; a count typed
    from memory was wrong twice in the first two runs. The command runs from the repository
    root through the platform shell; its output is clipped.
    """
    records: list[dict] = []
    for spec in specs or []:
        label, sep, command = spec.partition("=")
        if not sep:
            label, command = spec, spec
        label, command = label.strip(), command.strip()
        try:
            done = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=root, timeout=120)
            output = (done.stdout + done.stderr).strip()
            code = done.returncode
        except (OSError, subprocess.TimeoutExpired) as exc:
            output, code = f"(could not run: {exc})", -1
        if len(output) > FACT_OUTPUT_LIMIT:
            output = output[:FACT_OUTPUT_LIMIT] + "\n… (clipped)"
        records.append({"label": label, "command": command, "exit": code, "output": output, "at": stamp})
    if not records:
        return records, "- None recorded. Any count or identifier in the objective is unverified; treat it as a hint, not a fact."
    blocks = []
    for r in records:
        blocks.append(f"**{r['label']}** (`{r['command']}`, exit {r['exit']}, {r['at']})\n\n```text\n{r['output'] or '(no output)'}\n```")
    return records, "\n\n".join(blocks)


def resolve(root: Path, ref: str) -> Path:
    path = Path(ref)
    if path.is_absolute() and path.exists():
        return path
    return root / ref.lstrip("/")


# ---------------------------------------------------------------- commands


def cmd_new_run(args) -> int:
    root = discover_root(args.root)
    stamp = now_stamp(args.now)
    context_tokens, override = context_guard.guard(root, args, "new-run", datetime.fromisoformat(stamp))
    run_id = args.run_id or ("RUN-" + stamp[:19].replace("-", "").replace(":", "").replace("T", "-"))
    trial = None
    plan = None
    if args.plan is not None:
        if args.trial_workers is not None or args.trial_reason:
            raise SystemExit("error: --plan and --trial-workers cannot be combined")
        plan_file = resolve(root, args.plan)
        if not plan_file.is_file():
            raise SystemExit(f"error: --plan names no file: {args.plan}")
        try:
            plan = root_path(plan_file, root)
        except ValueError:  # outside the brain: record the absolute path as given
            plan = plan_file.resolve().as_posix()
        max_workers = args.max_workers or DEFAULT_MAX_WORKERS
        if not 1 <= max_workers <= PLAN_MAX_WORKERS:
            raise SystemExit(f"error: max workers is 1 to {PLAN_MAX_WORKERS} per run with --plan "
                             "(SMART-RULE-0024 budget); more than eight needs a measured trial "
                             "(--trial-workers with --trial-reason)")
    elif args.trial_workers is not None or args.trial_reason:
        if args.trial_workers is None:
            raise SystemExit("error: --trial-reason needs --trial-workers")
        if not (args.trial_reason or "").strip():
            raise SystemExit("error: --trial-reason is required with --trial-workers")
        if not TRIAL_MIN_WORKERS <= args.trial_workers <= TRIAL_MAX_WORKERS:
            raise SystemExit(f"error: --trial-workers must be {TRIAL_MIN_WORKERS} to {TRIAL_MAX_WORKERS} "
                             "(MEMORY-RULE-0005 trial)")
        if args.max_workers is not None:
            raise SystemExit("error: --max-workers and --trial-workers cannot be combined")
        trial = {"workers": args.trial_workers, "reason": args.trial_reason.strip()}
        max_workers = args.trial_workers
    else:
        max_workers = args.max_workers or DEFAULT_MAX_WORKERS
        if max_workers > HARD_MAX_WORKERS:
            raise SystemExit(f"error: max workers is {HARD_MAX_WORKERS} per run (SMART-RULE-0024 budget); "
                             f"up to {PLAN_MAX_WORKERS} with --plan naming an approved build plan")
    path = root / RUNS_SUBDIR / run_id
    if path.exists():
        raise SystemExit(f"error: run {run_id} already exists")
    path.mkdir(parents=True)
    fields = {
        "id": run_id,
        "title": args.title,
        "type": "delegation_run",
        "schema_version": "0.2",
        "contract": "/CONTRACT.md",
        "status": "open",
        "parent": args.parent,
        "max_workers": max_workers,
        **({"plan": plan} if plan else {}),
        **({"trial": trial} if trial else {}),
        "max_depth": 1,
        "host": None,
        "parallel": None,
        "context_tokens_at_open": context_tokens,
        **({"owner_override": override} if override else {}),
        # What was already changed before any worker started, so check-writes does not blame
        # a worker for it.
        "dirty_at_start": brain_changes(root),
        "created": stamp,
        "updated": stamp,
    }
    body = template_body(root, "run.template.md")
    body = body.replace("{{TITLE}}", args.title).replace("{{WHY_PARALLEL}}", args.why_parallel)
    write(path / "RUN.md", fields, body)
    print(root_path(path, root))
    return 0


def worker_instructions(fields: dict, result_ref: str) -> str:
    if fields["writes"] == "none":
        bootstrap = ("This packet allows no durable writes, so the scoped bootstrap tier applies: "
                     "read only the context files listed above.")
        write_rule = "Do not modify any file in this repository outside the run folder (writes: none)."
    elif fields["writes"] == "paths":
        bootstrap = "This packet allows writes, so complete the full bootstrap before changing anything."
        write_rule = ("Modify only these paths: " + ", ".join(f"`{p}`" for p in fields["write_paths"])
                      + ". Nothing else outside the run folder.")
    else:
        bootstrap = "This packet allows writes, so complete the full bootstrap before changing anything."
        write_rule = ("Work only in an isolated worktree or branch. Do not touch the shared worktree "
                      "outside the run folder.")
    external = {
        "none": "do not use any credential, vault entry, external API, email or browser session.",
        "read": ("read-only access only, no side effects; record source system, retrieval time and "
                 "scope for every retrieved fact (CONTRACT section 10.4)."),
        "write": (f"side effects only against the owner-confirmed target `{fields['external_target']}`; "
                  "nothing else."),
    }[fields["external"]]
    lines = [
        f"1. Bootstrap: read `/CONTRACT.md` section 1. {bootstrap}",
        f"2. {write_rule}",
        ("3. Commit on your own branch at each logical checkpoint and push that branch; never merge "
         "into main and never touch the shared worktree. The conductor merges (`SMART-RULE-0014`)."
         if fields["writes"] == "worktree" else
         "3. Do not commit, stage or push. The conductor owns Git (`SMART-RULE-0014`)."),
        f"4. External systems and credentials: {external}",
        "5. Do not delegate further. Depth is one.",
        f"6. Stay within about {fields['max_tool_calls']} tool calls and {fields['max_output_words']} "
        "words of result body.",
        f"7. Write your report into `{result_ref}` (the skeleton already exists): fill every section, "
        "set `status` to `completed`, `failed` or `blocked`, set `host` and `model` to what actually "
        "ran (write `unknown` rather than guessing), and list every changed path and artifact.",
        "8. If you need an owner decision, stop, set `status: blocked` and put the question under "
        "Open questions. Do not guess.",
        "9. Separate what you verified from what you assumed. Record what you ruled out and the "
        "evidence. Never include secrets, tokens or credentials.",
    ]
    return "\n".join(lines)


def cmd_new_packet(args) -> int:
    root = discover_root(args.root)
    stamp = now_stamp(args.now)
    _, override = context_guard.guard(root, args, "new-packet", datetime.fromisoformat(stamp))
    run = run_dir(root, args.run)
    run_meta, _ = load(run / "RUN.md")
    existing = packet_files(run)
    limit = int(run_meta.get("max_workers") or DEFAULT_MAX_WORKERS)
    if len(existing) >= limit:
        raise SystemExit(f"error: run {args.run} already has {len(existing)} packets; budget is {limit}")
    if args.context_mode not in CONTEXT_MODES:
        raise SystemExit(f"error: context mode must be one of {sorted(CONTEXT_MODES)}")
    if args.context_mode == "fork" and not args.fork_reason:
        raise SystemExit("error: --fork-reason is required when --context-mode fork")
    if args.writes not in WRITE_MODES:
        raise SystemExit(f"error: writes must be one of {sorted(WRITE_MODES)}")
    if args.writes == "paths" and not args.path:
        raise SystemExit("error: --path is required when --writes paths")
    if args.writes == "paths":
        # Workers of one run share the conductor's copy, so no two may name the same file
        # (SMART-RULE-0038). A folder overlaps every file inside it.
        for other in existing:
            other_meta, _ = load(other)
            if other_meta.get("writes") != "paths":
                continue
            for mine in args.path:
                for theirs in other_meta.get("write_paths") or []:
                    a, b = resolve(root, mine).resolve(), resolve(root, theirs).resolve()
                    if within(a, b) or within(b, a):
                        raise SystemExit(f"error: {mine} overlaps {theirs}, already named by {other.stem}; "
                                         "split the work so no two packets change the same file, or give "
                                         "one worker its own worktree")
    if args.external not in EXTERNAL_MODES:
        raise SystemExit(f"error: external must be one of {sorted(EXTERNAL_MODES)}")
    if (args.model is not None or args.effort is not None) and not (args.model_reason or "").strip():
        raise SystemExit("error: --model-reason is required when --model or --effort is given: the conductor "
                         "writes why it chose that model and effort for this packet")
    if args.external == "write" and not args.target:
        raise SystemExit("error: --target (owner-confirmed, CONTRACT section 10.5) is required "
                         "when --external write")
    for ref in args.context or []:
        if not resolve(root, ref).exists():
            raise SystemExit(f"error: context reference {ref} does not exist")

    short = f"W{len(existing) + 1:02d}"
    packet_id = f"{args.run}-{short}"
    facts, facts_md = verify_facts(args.fact, root, stamp)
    fields = {
        "id": packet_id,
        "title": args.title,
        "type": "delegation_packet",
        "schema_version": "0.2",
        "contract": "/CONTRACT.md",
        "run": args.run,
        "parent": run_meta.get("parent"),
        "context_mode": args.context_mode,
        "writes": args.writes,
        "write_paths": args.path or [],
        "external": args.external,
        "external_target": args.target,
        "model": args.model or "inherit",
        "effort": args.effort or "inherit",
        "model_reason": (args.model_reason or "").strip() or None,
        "max_tool_calls": args.max_tool_calls,
        "max_output_words": args.max_output_words,
        "context_refs": args.context or [],
        "facts_verified": [f["label"] for f in facts],
        **({"owner_override": override} if override else {}),
        "created": stamp,
        "updated": stamp,
    }
    result_ref = root_path(run, root) + f"/{short}.result.md"
    body = template_body(root, "packet.template.md")
    replacements = {
        "{{TITLE}}": args.title,
        "{{OBJECTIVE}}": args.objective,
        "{{EXCLUDE}}": bullets(args.exclude) or "- Nothing beyond the objective above.",
        "{{CONTEXT_REFS}}": bullets([f"`{ref}`" for ref in (args.context or [])])
        or "- No files beyond the contract.",
        "{{ACCEPTANCE}}": bullets(args.acceptance) or "- The objective is answered with evidence.",
        "{{FORK_REASON}}": args.fork_reason or "Not applicable: isolated context.",
        "{{FACTS}}": facts_md,
        "{{WORKER_INSTRUCTIONS}}": worker_instructions(fields, result_ref),
        "{{RESULT_PATH}}": result_ref,
    }
    for token, value in replacements.items():
        body = body.replace(token, value)
    write(run / f"{short}.md", fields, body)

    result_fields = {
        "id": packet_id + "-result",
        "title": f"Result: {args.title}",
        "type": "delegation_result",
        "schema_version": "0.2",
        "contract": "/CONTRACT.md",
        "run": args.run,
        "packet": short,
        "status": "pending",
        "host": None,
        "model": None,
        "changed_paths": [],
        "validation": [],
        "artifacts": [],
        "created": stamp,
        "updated": stamp,
    }
    result_body = template_body(root, "result.template.md").replace("{{TITLE}}", args.title)
    write(run / f"{short}.result.md", result_fields, result_body)
    touch_updated(run / "RUN.md", stamp, **({"owner_override": override} if override else {}))
    print(root_path(run / f"{short}.md", root))
    return 0


def cmd_dispatch_prompt(args) -> int:
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    packet = run / f"{args.packet}.md"
    if not packet.exists():
        raise SystemExit(f"error: packet {args.packet} not found in run {args.run}")
    fields, _ = load(packet)
    result = root_path(run / (args.packet + ".result.md"), root)
    print(
        f"You are a worker agent for the Portable AI Brain at repository root `{root}`. "
        f"Paths that begin with `/` are relative to that root. "
        f"Read the work packet at `{root_path(packet, root)}` and execute it exactly as written, "
        f"following its Worker instructions. Write your report into the result file it names "
        f"(`{result}`) and reply with only the result file path and its status. "
        f"Context mode: {fields.get('context_mode')}; writes: {fields.get('writes')}; "
        f"external: {fields.get('external')}."
    )
    return 0


def cmd_check_writes(args) -> int:
    """Every file changed in the brain since the run started that no `writes: paths` packet named.

    Git cannot say which worker changed a file, so this names the path and the conductor finds
    out. The conductor's own changes are passed with --mine.
    """
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    run_meta, _ = load(run / "RUN.md")
    before = set(run_meta.get("dirty_at_start") or [])
    scopes = [resolve(root, p).resolve() for p in args.mine or []]
    for packet_path in packet_files(run):
        packet, _ = load(packet_path)
        if packet.get("writes") == "paths":
            scopes += [resolve(root, p).resolve() for p in packet.get("write_paths") or []]
    stray = [changed for changed in brain_changes(root)
             if changed not in before
             and not any(within(resolve(root, changed).resolve(), scope) for scope in scopes)]
    for changed in stray:
        print(f"ERROR changed but named by no packet: {changed}")
    if stray:
        print(f"FAIL: {len(stray)} changed path(s) named by no packet")
        return 1
    print("PASS: every change since the run started was named by a packet")
    return 0


def trial_line(run_meta: dict) -> str:
    """The run's budget lines for close-run and summarise: its approved plan and its measured
    trial fields, one line each, or "" for an ordinary run."""
    lines = []
    if run_meta.get("plan"):
        lines.append(f"plan: {run_meta.get('plan')}")
    trial = run_meta.get("trial")
    if isinstance(trial, dict):
        lines.append(f"trial: workers {trial.get('workers')}; reason: {trial.get('reason')}")
    return "\n".join(lines)


def cmd_close_run(args) -> int:
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    if args.status not in {"synthesised", "abandoned"}:
        raise SystemExit("error: status must be synthesised or abandoned")
    touch_updated(run / "RUN.md", now_stamp(args.now), status=args.status, host=args.host,
                  parallel=(args.parallel == "yes"),
                  context_tokens_at_close=context_guard.context_value(args, "close-run"))
    print(root_path(run / "RUN.md", root))
    meta, _ = load(run / "RUN.md")
    line = trial_line(meta)
    if line:
        print(line)
    return 0


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
    from results import cmd_validate_result, cmd_summarise
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--root")
    parser.add_argument("--now", help="ISO 8601 timestamp override (tests)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("new-run")
    p.add_argument("--title", required=True)
    p.add_argument("--why-parallel", required=True,
                   help="one line: why parallel workers beat sequential work")
    p.add_argument("--parent", help="task or run id this run serves")
    p.add_argument("--max-workers", type=int)
    p.add_argument("--plan", help="repository-root or absolute path of the approved build plan this run "
                                  "follows; --max-workers may then be 1 to 8 (SMART-RULE-0024)")
    p.add_argument("--trial-workers", type=int,
                   help="5 to 8: mark this run as the MEMORY-RULE-0005 measured trial")
    p.add_argument("--trial-reason", help="required with --trial-workers: why this run is the trial")
    p.add_argument("--run-id", help=argparse.SUPPRESS)
    context_guard.add_context_arguments(p)
    p.set_defaults(func=cmd_new_run)

    p = sub.add_parser("new-packet")
    p.add_argument("--run", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--objective", required=True)
    p.add_argument("--context", action="append", help="repository-root path the worker should read")
    p.add_argument("--fact", action="append", metavar="LABEL=COMMAND",
                   help="run COMMAND now and paste its output into the packet as a verified fact")
    p.add_argument("--exclude", action="append")
    p.add_argument("--acceptance", action="append")
    p.add_argument("--context-mode", default="isolated")
    p.add_argument("--fork-reason")
    p.add_argument("--writes", default="none")
    p.add_argument("--path", action="append")
    p.add_argument("--external", default="none")
    p.add_argument("--target")
    p.add_argument("--model", default=None, help="the worker's model; give --model-reason with it")
    p.add_argument("--effort", default=None, help="the worker's effort; give --model-reason with it")
    p.add_argument("--model-reason", help="one line: why this model and effort for this packet")
    p.add_argument("--max-tool-calls", type=int, default=15)
    p.add_argument("--max-output-words", type=int, default=800)
    context_guard.add_context_arguments(p)
    p.set_defaults(func=cmd_new_packet)

    p = sub.add_parser("dispatch-prompt")
    p.add_argument("--run", required=True)
    p.add_argument("--packet", required=True)
    p.set_defaults(func=cmd_dispatch_prompt)

    p = sub.add_parser("validate-result")
    p.add_argument("--run", required=True)
    p.add_argument("--packet")
    p.set_defaults(func=cmd_validate_result)

    p = sub.add_parser("check-writes")
    p.add_argument("--run", required=True)
    p.add_argument("--mine", action="append", help="repository-root path the conductor changed itself")
    p.set_defaults(func=cmd_check_writes)

    p = sub.add_parser("summarise")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_summarise)

    p = sub.add_parser("close-run")
    p.add_argument("--run", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--parallel", required=True, choices=["yes", "no"])
    context_guard.add_context_arguments(p, guarded=False)
    p.set_defaults(func=cmd_close_run)

    p = sub.add_parser("checkpoint-done")
    p.add_argument("--session", required=True, help="this conductor's session id; removes its compaction marker")
    p.set_defaults(func=lambda a: context_guard.checkpoint_done(discover_root(a.root), a.session))
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # a Windows console defaults to cp1252; the messages carry an en dash
        getattr(stream, "reconfigure", lambda **_: None)(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
