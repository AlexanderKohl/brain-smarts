"""Convert a board from the hand-kept layout to the shared one, in place or into a repository.

Before: `board.md` with a fenced JSON block (`closed`, `mainVersion`, `generated` kept by hand),
cards named by slug, verdicts filed under `verdicts-in/` and `verdicts-applied/`.
After: `board.json` holding only what a person edits (`tracks`, `production`, `release_notes`,
`abandoned`, `elsewhere`, link identifiers), cards named `<author>-<UTC created>` with an
`author` field, one event per applied verdict under `events/`, and one `accept` event without a
card per version of the old `closed` register, so the register stays honest and derived.

    python migrate_board.py --board <id> [--to <repository>:brain/status] [--dry-run]

Without `--to` the board is converted where it is. With `--to` the converted board is written
into the named repository's folder (made if absent), `status.html` and `state.json` are added to
that repository's `.gitignore`, the board's entry in `boards.json` is pointed at it, and the old
folder is left for the conductor to `git mv` out of memory with its removed-files note. The
task actions inside old verdict files were applied to this memory at the time and are not
shared; they are not copied. `--dry-run` prints every step and writes nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402

IGNORE_LINES = ("brain/status/status.html", "brain/status/state.json")
MEMORY_PATH = re.compile(r"/memory/")


def read_board_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    found = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not found:
        raise ValueError(str(path) + " has no fenced json block")
    return json.loads(found.group(1))


def new_board_json(old: dict, board: dict) -> dict:
    out = {"id": board["id"], "label": old.get("label") or board["label"], "tracks": old.get("tracks") or {}}
    if old.get("production"):
        out["production"] = old["production"]
    out["release_notes"] = list(board.get("release_notes") or [])
    for key in ("abandoned", "elsewhere"):
        if key in old:
            out[key] = old[key]
    # Identifiers `where_view_href` fills from the board's own fields: anything else top-level.
    for key, value in old.items():
        if key not in out and key not in cards.DERIVED_KEYS and key not in ("id", "label", "tracks", "production",
                                                                             "release_notes", "abandoned", "elsewhere"):
            out[key] = value
    return out


def card_id_for(card: dict, author: str, taken: set) -> str:
    created = card.get("created") or card.get("startedAt") or card.get("asked") or ""
    moment = events.utc(cards._stamp(created))
    return events.new_id(author, moment, taken)


def plan(config: board_config.Config, board: dict, target: Path | None) -> dict:
    """Everything the migration would do, as data: the conductor reads it before it runs."""
    source = Path(board["folder"])
    dest = target or source
    author = board["author"]
    old_md = source / "board.md"
    old = read_board_md(old_md) if old_md.is_file() else None
    if old is None and (source / "board.json").is_file():
        old = json.loads((source / "board.json").read_text(encoding="utf-8"))
    if old is None:
        raise ValueError("no board.md or board.json in " + str(source))
    steps: dict = {"source": str(source), "dest": str(dest), "board_json": new_board_json(old, board),
                   "cards": [], "events": [], "ignore": [], "warnings": []}
    taken_cards: set = set()
    folder = source / "cards"
    for name in sorted(os.listdir(folder)) if folder.is_dir() else []:
        if not name.endswith(".md"):
            continue
        card = cards._card_from_file(str(folder / name))
        new_id = card["id"] if events.ID_RE.match(card["id"]) else card_id_for(card, author, taken_cards)
        taken_cards.add(new_id)
        steps["cards"].append({"from": name, "to": new_id + ".md", "id": new_id, "old_id": card["id"]})
    renamed = {c["old_id"]: c["id"] for c in steps["cards"]}
    taken_events: set = set(events.ids_in({"folder": dest}))
    for sub in ("verdicts-applied",):
        vfolder = source / sub
        for name in sorted(os.listdir(vfolder)) if vfolder.is_dir() else []:
            if not name.endswith(".json") or name.endswith(".as-saved.json"):
                continue
            saved = json.loads((vfolder / name).read_text(encoding="utf-8"))
            for v in saved.get("verdicts", []):
                kind = {"accepted": "accept", "rework": "reject"}.get(str(v.get("verdict")))
                if not kind:
                    steps["warnings"].append(name + ": verdict " + str(v.get("verdict")) + " on " + str(v.get("id")) + " not converted")
                    continue
                card_id = renamed.get(v.get("id"), v.get("id"))
                event = events.make({"folder": dest}, kind, author, saved.get("savedAt"), taken_events,
                                    card=card_id, sig=v.get("sig") or None, why=v.get("why") or None,
                                    version=v.get("version") or None, source="migrated from " + sub + "/" + name)
                taken_events.add(event["id"])
                steps["events"].append(event)
            if saved.get("tasks"):
                steps["warnings"].append(name + ": " + str(len(saved["tasks"])) + " task action(s) stay in this memory, not copied")
    for version, title in sorted((old.get("closed") or {}).items(), key=lambda kv: events.version_key(kv[0])):
        event = events.make({"folder": dest}, "accept", author, None, taken_events, card=None, version=version,
                            title=str(title)[:80], source="closed register before the move")
        taken_events.add(event["id"])
        steps["events"].append(event)
    if target is not None:
        repo = Path(board["folder"]).parents[1] if board.get("shared") else target.parents[1]
        steps["ignore"] = [line for line in IGNORE_LINES]
        steps["repo"] = str(repo)
    return steps


def run(config: board_config.Config, board: dict, steps: dict, dry_run: bool) -> list:
    """Carry out a plan. Returns one line per step."""
    out = []
    source, dest = Path(steps["source"]), Path(steps["dest"])
    if not dry_run:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "cards").mkdir(exist_ok=True)
        (dest / "events").mkdir(exist_ok=True)
    out.append("board.json <- " + ", ".join(sorted(steps["board_json"])))
    if not dry_run:
        cards.write_board({"folder": dest}, steps["board_json"])
        if (source / "board.md").is_file() and dest == source:
            os.remove(source / "board.md")
    target_board = dict(board, folder=dest)
    for step in steps["cards"]:
        out.append("card " + step["from"] + " -> cards/" + step["to"])
        if dry_run:
            continue
        card = cards._card_from_file(str(source / "cards" / step["from"]))
        card["id"] = step["id"]
        card["author"] = board["author"]
        if (dest / "cards" / step["to"]).exists() and step["from"] == step["to"] and dest == source:
            continue
        cards.write(target_board, card)
        if dest == source and step["from"] != step["to"]:
            os.remove(source / "cards" / step["from"])
    for event in steps["events"]:
        out.append("event " + event["id"] + " " + event["kind"] + " " + str(event.get("card") or event.get("version")))
        if not dry_run and not (dest / "events" / (event["id"] + ".json")).exists():
            events.write(target_board, event)
    if dest == source:
        for sub in ("verdicts-in", "verdicts-applied"):
            if (source / sub).is_dir():
                out.append("remove " + sub + "/ (its verdicts are events now)")
                if not dry_run:
                    shutil.rmtree(source / sub)
    if (source / "img").is_dir() and dest != source:
        out.append("copy img/")
        if not dry_run:
            shutil.copytree(source / "img", dest / "img", dirs_exist_ok=True)
    if steps.get("repo"):
        ignore = Path(steps["repo"]) / ".gitignore"
        have = ignore.read_text(encoding="utf-8").splitlines() if ignore.is_file() else []
        missing = [line for line in steps["ignore"] if line not in have]
        if missing:
            out.append(".gitignore += " + ", ".join(missing))
            if not dry_run:
                with open(ignore, "a", encoding="utf-8", newline="\n") as fh:
                    fh.write(("" if not have or have[-1] == "" else "\n") + "\n".join(missing) + "\n")
        out.append("boards.json: status -> " + steps["status"])
        if not dry_run:
            raw = json.loads(config.path.read_text(encoding="utf-8"))
            for entry in raw.get("boards", []):
                if entry["id"] == board["id"]:
                    entry["status"] = steps["status"]
                    entry.setdefault("node", board.get("node") or "")   # the pointer node, for task routing
            config.path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
        out.append("then: git mv " + str(source) + " out of memory with its removed-files note; rebuild; commit both repositories")
    for warning in steps["warnings"]:
        out.append("note: " + warning)
    return out


def check_no_memory_paths(folder: Path) -> list:
    """Files under a repository board that still say /memory/: a collaborator cannot resolve them."""
    hits = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix in (".md", ".json") and MEMORY_PATH.search(path.read_text(encoding="utf-8", errors="replace")):
            hits.append(str(path.relative_to(folder)).replace(os.sep, "/"))
    return hits


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", required=True)
    p.add_argument("--to", help="<repository>:brain/status - the shared folder to write the board into")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    config = board_config.load(args)
    board = config.board(args.board)
    target = None
    if args.to:
        found = board_config.SHARED_STATUS.match(args.to)
        if not found:
            raise board_config.ConfigError("--to must look like <repository>:brain/status")
        base = config.profile.get("project_repos_root") or str(config.brain.parent)
        target = Path(base) / found.group(1) / found.group(2).strip("/").replace("/", os.sep)
    steps = plan(config, board, target)
    if target is not None:
        steps["status"] = args.to
    for line in run(config, board, steps, args.dry_run):
        print(("would: " if args.dry_run else "did: ") + line)
    if target is not None and not args.dry_run:
        hits = check_no_memory_paths(target)
        for hit in hits:
            print("WARNING " + hit + " mentions /memory/ - fix it before the repository is pushed")
        return 1 if hits else 0
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
