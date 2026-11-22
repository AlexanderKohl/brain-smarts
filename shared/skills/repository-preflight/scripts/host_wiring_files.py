"""What host_wiring.py writes: one Item per file, built from the host-pointer templates."""
from __future__ import annotations

import json
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import host_wiring_merge as merge

HOSTS = ("claude-code", "codex", "cursor", "cursor-cli")
LEVELS = ("routine", "edits", "defaults")
TEMPLATES = Path("shared") / "templates" / "host-pointers"


@dataclass
class Item:
    path: Path
    kind: str                       # pointer | copy | json | toml
    content: str                    # the text to write
    action: str                     # create | replace | merge | unchanged | keep | skip (never written)
    conflicts: list[str] = field(default_factory=list)


def posix(path: str | Path) -> str:
    return str(path).replace("\\", "/")


def project_repos_root(root: Path) -> str:
    owner = root / "memory" / "OWNER.md"
    if owner.is_file():
        found = re.search(r"^project_repos_root:\s*(\S.*)$", owner.read_text(encoding="utf-8", errors="replace"), re.M)
        if found:
            return found.group(1).strip().strip("'\"")
    return str(root.parent)


def native(value: str) -> str:
    """The form Codex records: backslashes on Windows, as given elsewhere."""
    return str(Path(value)) if os.name == "nt" else value


def _norm(text: str) -> str:
    return text.replace("\r\n", "\n")


def _read(path: Path) -> str | None:
    return _norm(path.read_text(encoding="utf-8")) if path.is_file() else None


def _pointer_body(text: str) -> str:
    text = _norm(text)
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            text = text[end + 5:]
    return text.strip("\n") + "\n"


def _plain(path: Path, kind: str, content: str) -> Item:
    old = _read(path)
    return Item(path, kind, content, "create" if old is None else "unchanged" if old == _norm(content) else "replace")


def _commands(entries: list) -> set[str]:
    return {h.get("command") for e in entries if isinstance(e, dict)
            for h in e.get("hooks", []) if isinstance(h, dict)}


def merge_hooks(merged: dict, template_hooks: dict | None) -> list[str]:
    """Add each template hook entry whose command the event does not run yet; keep every hook the
    person has. Returns a conflict line when the person's `hooks` cannot take the entries."""
    if not template_hooks:
        return []
    hooks = merged.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        return [f"hooks: kept {json.dumps(hooks)}, template adds {', '.join(sorted(template_hooks))}"]
    conflicts = []
    for event, entries in template_hooks.items():
        current = hooks.setdefault(event, [])
        if not isinstance(current, list):
            conflicts.append(f"hooks.{event}: kept {json.dumps(current)}, template has {json.dumps(entries)}")
            continue
        current += [e for e in entries if not _commands([e]) <= _commands(current)]
    return conflicts


def _unparsed(path: Path, kind: str, old: str, reason: str) -> Item:
    """A configuration file that cannot be read as its format: reported and left exactly as it is."""
    return Item(path, kind, old, "skip", [f"{path}: cannot be parsed ({reason}); left untouched"])


def _json_item(path: Path, template: Path, mapping: dict[str, str]) -> Item:
    data = merge.fill(json.loads(template.read_text(encoding="utf-8")), mapping)
    template_hooks = data.pop("hooks", None)     # hooks merge per event and command, not as one value
    old = _read(path)
    try:
        existing = json.loads(old) if old is not None and old.strip() else None
    except ValueError as exc:
        return _unparsed(path, "json", old or "", str(exc))
    if existing is not None and not isinstance(existing, dict):
        return _unparsed(path, "json", old or "", "not a JSON object")
    merged, conflicts = merge.merge_json(existing, data)
    conflicts += merge_hooks(merged, template_hooks)
    action = "create" if old is None else "unchanged" if merged == existing else "merge"
    return Item(path, "json", merge.dump_json(merged), action, conflicts)


def _toml_item(path: Path, text: str, hooks: list | None = None) -> Item:
    old = _read(path)
    try:
        merged, conflicts = merge.merge_toml(old or "", text)
    except tomllib.TOMLDecodeError as exc:
        return _unparsed(path, "toml", old or "", str(exc))
    if hooks:
        merged, more = merge.add_toml_hooks(merged, hooks)
        conflicts += more
    action = "create" if old is None else "unchanged" if merged == old else "merge"
    return Item(path, "toml", merged, action, conflicts)


BRAIN_COPY = "# From the brain's "                   # opens the marker line of every brain worker definition


def _toml_name(text: str) -> str | None:
    try:
        name = tomllib.loads(text).get("name")
    except tomllib.TOMLDecodeError:
        return None
    return name if isinstance(name, str) else None


def _md_name(text: str) -> str | None:
    found = re.search(r"^name:\s*(\S+)\s*$", _norm(text).split("\n---", 1)[0], re.M)
    return found.group(1) if found else None


def _agents(source: Path, pattern: str, dest: Path, name_of) -> list[Item]:
    """Copy each brain worker definition to the host's user folder. A file there without the brain's
    marker line is the person's own: it is kept, and so is any file of theirs defining an agent of the
    same name; the brain's file is then not installed, and a conflict line says so."""
    theirs: dict[str, Path] = {}
    for path in sorted(dest.glob(pattern)) if dest.is_dir() else []:
        text = _read(path) or ""
        name = name_of(text)
        if BRAIN_COPY not in text and name:
            theirs[name] = path
    items = []
    for agent in sorted(source.glob(pattern)):
        content = agent.read_text(encoding="utf-8")
        target = dest / agent.name
        own = theirs.get(name_of(content) or "")
        if target.is_file() and BRAIN_COPY not in (_read(target) or "") and own is None:
            own = target
        if own is not None:
            items.append(Item(target, "copy", content, "keep",
                              [f"{own}: your own agent, kept; the brain's {agent.name} is not installed"]))
        else:
            items.append(_plain(target, "copy", content))
    return items


def codex_hooks(root: Path) -> list[tuple[str, str | None, str, str]]:
    """(event, matcher, command, subcommand) of the brain's PreCompact and SessionStart hooks, from the
    one event list hooks.py keeps (hooks/events.json). Codex uses the same event names, matchers and
    stdin fields (session_id, cwd, trigger, source), so the same commands run; the script is named by
    its absolute path because Codex runs a hook in the session's folder."""
    import hooks as brain_hooks                          # the canonical event list, never a copy of it
    wanted = []
    for event in brain_hooks.brain_events():
        if event.get("claude_code") not in ("PreCompact", "SessionStart"):
            continue
        script, _sep, args = event["command"].partition(" ")
        command = f'python "{posix(root / script)}" {args}'.rstrip()
        wanted.append((event["claude_code"], event.get("matcher"), command, args.split()[0]))
    return wanted


def build(root: Path, home: Path, hosts: list[str], level: str) -> list[Item]:
    tpl = root / TEMPLATES
    repos = project_repos_root(root)
    md = {"<BRAIN_ROOT>": posix(root), "<PROJECT_REPOS_ROOT>": posix(repos)}
    settings = level != "defaults"
    items: list[Item] = []
    if "claude-code" in hosts:
        body = _pointer_body((tpl / "claude-code-user.CLAUDE.template.md").read_text(encoding="utf-8"))
        items.append(_plain(home / ".claude" / "CLAUDE.md", "pointer", merge.fill(body, md)))
        for agent in sorted((root / ".claude" / "agents").glob("worker-*.md")):
            items.append(_plain(home / ".claude" / "agents" / agent.name, "copy", agent.read_text(encoding="utf-8")))
        if settings:
            items.append(_json_item(home / ".claude" / "settings.json", tpl / "claude-code.user-settings.template.json", md))
        if level == "routine":
            items.append(_json_item(root / ".claude" / "settings.local.json",
                                    tpl / "claude-code.settings.local.template.json", md))
    toml_map = {"<BRAIN_ROOT>": native(str(root)), "<PROJECT_REPOS_ROOT>": native(repos)}
    if "codex" in hosts:
        body = _pointer_body((tpl / "codex-user.AGENTS.template.md").read_text(encoding="utf-8"))
        items.append(_plain(home / ".codex" / "AGENTS.md", "pointer", merge.fill(body, md)))
        text = merge.fill((tpl / "codex.config.template.toml").read_text(encoding="utf-8"), toml_map)
        if not settings:                                 # the trust entry only
            text = f"[projects.'{toml_map['<BRAIN_ROOT>']}']\ntrust_level = \"trusted\"\n"
        items.append(_toml_item(home / ".codex" / "config.toml", text, codex_hooks(root) if settings else None))
        items += _agents(root / ".codex" / "agents", "*.toml", home / ".codex" / "agents", _toml_name)
    if "cursor" in hosts:
        # Worker types only, no hooks: Cursor's preCompact input carries no session_id, and both events
        # read a JSON reply (additional_context, user_message) that hooks.py does not print, so the
        # brain's hooks would run without effect (hosts/cursor.md, Compaction hooks).
        items += _agents(root / ".cursor" / "agents", "*.md", home / ".cursor" / "agents", _md_name)
    if "cursor-cli" in hosts and settings:
        items.append(_json_item(home / ".cursor" / "cli-config.json", tpl / "cursor-cli.cli-config.template.json", md))
    return items
