#!/usr/bin/env python3
"""Create, dispatch and validate delegated-work packets for the Portable AI Brain.

A run is one fan-out from a conductor agent to one or more worker agents. Everything a run
produces lives under /temp/delegation/runs/<RUN-ID>/ and is ephemeral instrumentation, not a
task record. The conductor routes durable outcomes under CONTRACT sections 5 and 6.

Commands
  new-run          --title T --why-parallel TEXT [--parent ID] [--max-workers N]
  new-packet       --run RUN --title T --objective TEXT [--context PATH ...]
                   [--context-mode isolated|fork] [--fork-reason TEXT]
                   [--writes none|worktree|paths] [--path PATH ...]
                   [--external none|read|write] [--target TEXT]
                   [--model NAME] [--max-tool-calls N] [--max-output-words N]
                   [--acceptance TEXT ...] [--exclude TEXT ...]
  dispatch-prompt  --run RUN --packet W01
  validate-result  --run RUN [--packet W01]
  summarise        --run RUN
  close-run        --run RUN --status synthesised|abandoned --host TEXT --parallel yes|no

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

SKILL_PATH = "/shared/skills/delegate-work"
RUNS_SUBDIR = Path("temp") / "delegation" / "runs"
DEFAULT_MAX_WORKERS = 4
HARD_MAX_WORKERS = 4
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
    """Parse the YAML subset this skill writes: scalars and flat lists."""
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
        if isinstance(value, list):
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
    run_id = args.run_id or ("RUN-" + stamp[:19].replace("-", "").replace(":", "").replace("T", "-"))
    max_workers = args.max_workers or DEFAULT_MAX_WORKERS
    if max_workers > HARD_MAX_WORKERS:
        raise SystemExit(f"error: max workers is {HARD_MAX_WORKERS} per run (RULE-2026-0037 budget)")
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
        "max_depth": 1,
        "host": None,
        "parallel": None,
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
         "into main and never touch the shared worktree. The conductor merges (`RULE-2026-0023`)."
         if fields["writes"] == "worktree" else
         "3. Do not commit, stage or push. The conductor owns Git (`RULE-2026-0023`)."),
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
    if args.external not in EXTERNAL_MODES:
        raise SystemExit(f"error: external must be one of {sorted(EXTERNAL_MODES)}")
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
        "max_tool_calls": args.max_tool_calls,
        "max_output_words": args.max_output_words,
        "context_refs": args.context or [],
        "facts_verified": [f["label"] for f in facts],
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
    touch_updated(run / "RUN.md", stamp)
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


PATH_RE = re.compile(r"^(/|[A-Za-z]:[\/]|\.{1,2}[\/])\S*$")


def looks_like_path(text: str) -> bool:
    """A repository-root, absolute or relative path without spaces; anything else is free text."""
    return bool(PATH_RE.match(text.strip()))


def validate_one(root: Path, run: Path, short: str, warnings: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    warnings = warnings if warnings is not None else []
    packet_path = run / f"{short}.md"
    result_path = run / f"{short}.result.md"
    if not packet_path.exists():
        return [f"{short}: packet file missing"]
    if not result_path.exists():
        return [f"{short}: result file missing"]
    packet, _ = load(packet_path)
    result, body = load(result_path)
    display = root_path(result_path, root)

    for key in ("id", "type", "contract", "run", "packet", "status", "created", "updated"):
        if key not in result:
            errors.append(f"{display}: missing front matter field {key}")
    if result.get("type") != "delegation_result":
        errors.append(f"{display}: type must be delegation_result")
    if result.get("packet") != short:
        errors.append(f"{display}: packet must be {short}")
    status = result.get("status")
    if status not in RESULT_STATUSES:
        errors.append(f"{display}: invalid status {status}")
    if status == "pending":
        errors.append(f"{display}: worker has not reported (status pending)")
        return errors
    for key in ("host", "model"):
        value = result.get(key)
        if not value or not str(value).strip():
            errors.append(f"{display}: {key} must be set (use 'unknown' rather than guessing)")
    for key in ("changed_paths", "validation", "artifacts"):
        if not isinstance(result.get(key), list):
            errors.append(f"{display}: {key} must be a list")
            result[key] = []

    # Files inside the run folder (the result itself, artifacts) are not repository writes.
    outside_run = [
        changed for changed in result["changed_paths"]
        if not resolve(root, changed).resolve().is_relative_to(run.resolve())
    ]
    if packet.get("writes") == "none" and outside_run:
        errors.append(f"{display}: packet allows no writes but changed_paths is not empty")
    for changed in result["changed_paths"]:
        if resolve(root, changed).exists():
            continue
        # A worktree packet works in another repository, so its paths are that
        # repository's and cannot be resolved here. Reporting them as missing files
        # said seventeen real files did not exist (16 September 2026) and taught a
        # conductor to read past the validator, which is worse than the noise.
        if packet.get("writes") == "worktree":
            warnings.append(f"{display}: changed path is not in this repository, which a worktree packet expects: {changed}")
        else:
            errors.append(f"{display}: changed path does not exist: {changed}")
    if result["changed_paths"] and not result["validation"]:
        errors.append(f"{display}: changed paths reported without validation results")
    for artifact in result["artifacts"]:
        # A branch, a commit or a URL is an artifact too; only a path is checked on disk.
        if looks_like_path(artifact) and not resolve(root, artifact).exists():
            errors.append(f"{display}: artifact does not exist: {artifact}")

    budget = packet.get("max_output_words")
    words = len(body.split())
    if budget and str(budget).isdigit() and words > int(budget):
        # Acceptance criteria decide the size; the budget is advice to the worker.
        warnings.append(f"{display}: body is {words} words against a budget of {budget}")

    found = sections(body)
    defaults = sections(template_body(root, "result.template.md"))
    for name in REQUIRED_RESULT_SECTIONS:
        if name not in found:
            errors.append(f"{display}: missing section '## {name}'")
    if status == "blocked" and not has_content(found.get("Open questions", ""),
                                               defaults.get("Open questions", "")):
        errors.append(f"{display}: blocked result must state the question under Open questions")
    if status == "completed" and not has_content(found.get("Summary", ""),
                                                 defaults.get("Summary", "")):
        errors.append(f"{display}: completed result has an empty Summary")
    for pattern in SECRET_PATTERNS:
        if pattern.search(body):
            errors.append(f"{display}: body matches a secret pattern ({pattern.pattern[:30]}...)")
            break
    return errors


def cmd_validate_result(args) -> int:
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    shorts = [args.packet] if args.packet else [p.stem for p in packet_files(run)]
    if not shorts:
        print("no packets in run")
        return 1
    errors: list[str] = []
    warnings: list[str] = []
    for short in shorts:
        errors.extend(validate_one(root, run, short, warnings))
    for warning in warnings:
        print(f"WARN {warning}")
    if errors:
        for error in errors:
            print(f"ERROR {error}")
        print(f"FAIL: {len(errors)} error(s)")
        return 1
    print(f"PASS: {len(shorts)} result(s) valid" + (f", {len(warnings)} warning(s)" if warnings else ""))
    return 0


def cmd_summarise(args) -> int:
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    run_meta, _ = load(run / "RUN.md")
    print(f"# Run {run_meta.get('id')}: {run_meta.get('title')}")
    print(f"status: {run_meta.get('status')}; host: {run_meta.get('host')}; "
          f"parallel: {run_meta.get('parallel')}; parent: {run_meta.get('parent')}")
    print()
    print("| Packet | Title | Status | Host | Model | Changed paths | Artifacts |")
    print("|---|---|---|---|---|---|---|")
    collected: dict[str, list[tuple[str, str]]] = {
        "Summary": [], "Facts to route": [], "Open questions": [], "Suggested tasks": [],
    }
    defaults = sections(template_body(root, "result.template.md"))
    for packet_path in packet_files(run):
        short = packet_path.stem
        packet, _ = load(packet_path)
        result_path = run / f"{short}.result.md"
        result, body = load(result_path) if result_path.exists() else ({}, "")
        found = sections(body)
        print(
            f"| {short} | {packet.get('title')} | {result.get('status', 'missing')} | "
            f"{result.get('host') or '-'} | {result.get('model') or '-'} | "
            f"{len(result.get('changed_paths') or [])} | {len(result.get('artifacts') or [])} |"
        )
        for name in collected:
            text = found.get(name, "")
            if has_content(text, defaults.get(name, "")):
                collected[name].append((short, text.replace(defaults.get(name, "").strip(), "").strip()))
    for name, items in collected.items():
        print()
        print(f"## {name}")
        if not items:
            print("- none reported")
        for short, text in items:
            print(f"### {short}")
            print(text)
    return 0


def cmd_close_run(args) -> int:
    root = discover_root(args.root)
    run = run_dir(root, args.run)
    if args.status not in {"synthesised", "abandoned"}:
        raise SystemExit("error: status must be synthesised or abandoned")
    touch_updated(run / "RUN.md", now_stamp(args.now), status=args.status, host=args.host,
                  parallel=(args.parallel == "yes"))
    print(root_path(run / "RUN.md", root))
    return 0


# ---------------------------------------------------------------- CLI


def build_parser() -> argparse.ArgumentParser:
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
    p.add_argument("--run-id", help=argparse.SUPPRESS)
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
    p.add_argument("--model", default="inherit")
    p.add_argument("--max-tool-calls", type=int, default=15)
    p.add_argument("--max-output-words", type=int, default=800)
    p.set_defaults(func=cmd_new_packet)

    p = sub.add_parser("dispatch-prompt")
    p.add_argument("--run", required=True)
    p.add_argument("--packet", required=True)
    p.set_defaults(func=cmd_dispatch_prompt)

    p = sub.add_parser("validate-result")
    p.add_argument("--run", required=True)
    p.add_argument("--packet")
    p.set_defaults(func=cmd_validate_result)

    p = sub.add_parser("summarise")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_summarise)

    p = sub.add_parser("close-run")
    p.add_argument("--run", required=True)
    p.add_argument("--status", required=True)
    p.add_argument("--host", required=True)
    p.add_argument("--parallel", required=True, choices=["yes", "no"])
    p.set_defaults(func=cmd_close_run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
