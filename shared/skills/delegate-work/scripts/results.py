"""Validation and summarisation of delegation run results.

Functions in this module are imported from delegation.py at run time to avoid
an import cycle (delegation.py is __main__ and must not import results at
module level).
"""

from __future__ import annotations

from pathlib import Path

from delegation import (trial_line, discover_root, run_dir, load, packet_files, root_path, sections, has_content,
                        template_body, resolve, within, RESULT_STATUSES,
                        SECRET_PATTERNS, REQUIRED_RESULT_SECTIONS)

import re

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
    if packet.get("writes") == "paths":
        allowed = [resolve(root, scope).resolve() for scope in packet.get("write_paths") or []]
        for changed in outside_run:
            if not any(within(resolve(root, changed).resolve(), scope) for scope in allowed):
                errors.append(f"{display}: changed path is outside the packet's write_paths: {changed}")
    for changed in result["changed_paths"]:
        if resolve(root, changed).exists():
            continue
        # A worktree packet works in another repository, so its paths are that
        # repository's and cannot be resolved here. Reporting them as missing files
        # teaches a conductor to read past the validator, which is worse than the noise.
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
    if trial_line(run_meta):
        print(trial_line(run_meta))
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
