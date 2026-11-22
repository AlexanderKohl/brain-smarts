"""What host_wiring.py writes: one Item per file, built from the host-pointer templates."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import host_wiring_merge as merge

HOSTS = ("claude-code", "codex", "cursor-cli")
LEVELS = ("routine", "edits", "defaults")
TEMPLATES = Path("shared") / "templates" / "host-pointers"


@dataclass
class Item:
    path: Path
    kind: str                       # pointer | copy | json | toml
    content: str                    # the text to write
    action: str                     # create | replace | merge | unchanged
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


def _json_item(path: Path, template: Path, mapping: dict[str, str]) -> Item:
    data = merge.fill(json.loads(template.read_text(encoding="utf-8")), mapping)
    template_hooks = data.pop("hooks", None)     # hooks merge per event and command, not as one value
    old = _read(path)
    existing = json.loads(old) if old is not None and old.strip() else None
    if existing is not None and not isinstance(existing, dict):
        raise ValueError(f"{path}: not a JSON object")
    merged, conflicts = merge.merge_json(existing, data)
    conflicts += merge_hooks(merged, template_hooks)
    action = "create" if old is None else "unchanged" if merged == existing else "merge"
    return Item(path, "json", merge.dump_json(merged), action, conflicts)


def _toml_item(path: Path, text: str) -> Item:
    old = _read(path)
    merged, conflicts = merge.merge_toml(old or "", text)
    action = "create" if old is None else "unchanged" if merged == old else "merge"
    return Item(path, "toml", merged, action, conflicts)


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
        items.append(_toml_item(home / ".codex" / "config.toml", text))
    if "cursor-cli" in hosts and settings:
        items.append(_json_item(home / ".cursor" / "cli-config.json", tpl / "cursor-cli.cli-config.template.json", md))
    return items
