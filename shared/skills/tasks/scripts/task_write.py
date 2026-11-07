"""The one path a change to an existing task takes, in every store (plan section 2.2).

    change(root, task, fields, what, ...)  resolve the author, check the store may be written,
                                           build the text with apply_change, write it (moving it
                                           to another folder when asked), regenerate STATE.md
    regenerate(store)                      STATE.md again, or the command that does it
    locate(store, tid)                     the brain root above an owner store, and the task
                                           found in any of its stores
    save_images / decode_image             screenshots kept beside the store, plain images only

Every step that fails before the record is written writes nothing. A STATE.md that cannot be
regenerated leaves the record standing and names `tasks.py state --store <label>`.
"""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

import task_state
from task_git import WriteRefused, ready_to_write
from task_history import apply_change, brain_author, owner_now
from task_private import MEMORY_PATH
from task_records import Task, move_record
import task_stores
from task_stores import owner_store

# A screenshot is kept only when it is plainly one of these images; anything else is dropped.
IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=]+)$")


def brain_root(start: Path) -> Path | None:
    for parent in (start.resolve(), *start.resolve().parents):
        if (parent / "CONTRACT.md").is_file():
            return parent
    return None


def locate(store: Path, tid: str) -> tuple[Path, Task]:
    """The brain that holds this owner store, and the task found in any of its stores."""
    root = brain_root(store)
    if root is None:
        raise LookupError(f"no brain root (CONTRACT.md) above {store.as_posix()}")
    return root, task_stores.find(root, tid)


def stamp(root: Path, now: str | None) -> tuple[str, list[str]]:
    if now:
        return now, []
    at, note = owner_now(root)
    return at, [note] if note else []


def decode_image(data_uri: str) -> tuple[str, bytes] | None:
    """A pasted screenshot as (file extension, bytes), or None when it is not a plain image."""
    found = IMAGE_RE.match(str(data_uri))
    if not found:
        return None
    try:
        raw = base64.b64decode(found.group(2), validate=True)
    except (binascii.Error, ValueError):
        return None
    return ("jpg" if found.group(1) == "jpeg" else found.group(1)), raw


def save_images(store_path: Path, tid: str, at: str, shots: list[str] | None) -> list[str]:
    """Write pasted screenshots to <store>/img/<TID>-<stamp>-<n>.<ext>; returns store-relative paths."""
    digits = re.sub(r"[^0-9]", "", at)[:14] or "undated"
    paths = []
    for n, shot in enumerate(shots or [], 1):
        image = decode_image(shot)
        if not image:
            continue
        rel = f"img/{tid}-{digits}-{n}.{image[0]}"
        (store_path / "img").mkdir(parents=True, exist_ok=True)
        (store_path / rel).write_bytes(image[1])
        paths.append(rel)
    return paths


def regenerate(store) -> list[str]:
    try:
        changed = task_state.write(store)
    except (OSError, ValueError) as err:
        return [f"STATE.md: not regenerated ({err}); run `tasks.py state --store {store.label}`"]
    return [f"STATE.md: regenerated for {store.label}"] if changed else []


def refuse_memory_paths(store, text: str, where: str) -> None:
    """A repository record never names /memory/: its readers cannot resolve it, and it is private."""
    if store.kind == "repository" and MEMORY_PATH.search(text):
        raise WriteRefused(f"{where} names a /memory/ path, which is never written into {store.label}; "
                           "keep it in the companion file instead (`note --private`)")


def change(root: Path, task: Task, fields: dict, what: str, *, note: str | None = None,
           shots: list[str] | None = None, shot_stamp: str | None = None, folder: str | None = None,
           now: str | None = None, offline: bool = False) -> tuple[Path, list[str]]:
    """Apply one attributed change to a record and regenerate its store's STATE.md."""
    author = brain_author(root)
    store = task.store or owner_store(root)
    said = ready_to_write(store, offline=offline, record=task.path)
    at, notes = stamp(root, now)
    said += notes
    original = task.path.read_text(encoding="utf-8")
    text = apply_change(original, fields, what, author, at, note)
    refuse_memory_paths(store, text, f"the change to {task.tid}")
    images = save_images(store.path, task.tid, shot_stamp or at, shots)
    if images:
        text = apply_change(original, fields, what, author, at, note, images)
    target = store.path / (folder or task.folder) / task.path.name
    move_record(task.path, target, text)
    return target, said + regenerate(store)
