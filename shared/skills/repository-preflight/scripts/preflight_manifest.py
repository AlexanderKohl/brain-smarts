"""The generated repository manifests, and the personal-data check of the shareable repositories.

Moved unchanged from preflight.py. preflight.py imports these names back, so everything that uses
preflight sees the same names.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from preflight_base import LIBRARY_DIR, memory_root, library_root, Result, message_layer, root_path


MANIFEST_NAME = "repository-manifest.json"
VALIDATOR_PATH = "/shared/skills/repository-preflight/scripts/preflight.py"


def manifest_paths(root: Path) -> dict[str, Path]:
    paths = {"mechanics": root / MANIFEST_NAME}
    memory = memory_root(root)
    if memory is not None:
        paths["memory"] = memory / MANIFEST_NAME
    library = library_root(root)
    if library is not None:
        paths["library"] = library / MANIFEST_NAME
    return paths


def validate_manifest(
    root: Path, result: Result, writing: bool
) -> None:
    for layer, path in manifest_paths(root).items():
        display = root_path(path, root)
        if not path.exists():
            if writing:
                continue
            if layer == "mechanics":
                result.errors.append(f"{display}: missing")
            else:
                result.warnings.append(
                    f"{display}: missing; create it with --write-manifest"
                )
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"{display}: {exc}")
            continue
        if (
            not writing
            and manifest.get("contract_version") != result.contract_version
        ):
            result.errors.append(
                f"{display}: contract_version does not match /CONTRACT.md"
            )


def write_manifests(root: Path, result: Result) -> None:
    """Write one manifest per repository, each holding only its own layer's messages."""
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    names = {"mechanics": "Portable AI Brain – mechanics", "memory": "Portable AI Brain – memory",
             "library": "Portable AI Brain – skill library"}
    for layer, path in manifest_paths(root).items():
        created = now
        name = names[layer]
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                created = existing.get("created", created)
                name = existing.get("name", name)
            except (OSError, json.JSONDecodeError):
                pass
        manifest = {
            "name": name,
            "layer": layer,
            "created": created,
            "updated": now,
            "validated_at": now,
            "contract_version": result.contract_version,
            "markdown_files": result.layer_markdown_files.get(layer, 0),
            "unique_ids": result.layer_unique_ids.get(layer, 0),
            "validation_errors": [m for m in result.errors if message_layer(m) == layer],
            "validation_warnings": [m for m in result.warnings if message_layer(m) == layer],
            "root_contract": "/CONTRACT.md",
            "validator": VALIDATOR_PATH,
        }
        temporary = path.with_suffix(path.suffix + ".tmp")
        # LF on every platform, so a rewrite on Windows is not a whole-file change.
        temporary.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        temporary.replace(path)


def shareable_repositories(root: Path) -> list[Path]:
    """The repositories that must hold no personal data: the mechanics, and the skill library when
    it is checked out (CONTRACT §3.4)."""
    library = root / LIBRARY_DIR
    return [root] + ([library] if library.is_dir() else [])


def validate_personal_data(root: Path, result: Result) -> None:
    """SMART-RULE-0008: a shareable repository is written clean, and this confirms it. Owner terms
    come from memory at run time; without memory only the patterns run."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import personal_data

    for repo in shareable_repositories(root):
        hits, problems = personal_data.check_repository(root, repo)
        result.errors.extend(f"personal-data exemptions: {problem}" for problem in problems)
        # The value itself is withheld: errors are written into the committed manifest, and
        # repeating it there would copy the leak. File, line and kind are enough to find it;
        # `skill_exchange.py scrub <file>` prints the value on the console only.
        for file, line, kind, _value in hits:
            display = root_path(Path(file), root)
            result.errors.append(f"{display}:{line}: personal data ({kind}); value withheld")
