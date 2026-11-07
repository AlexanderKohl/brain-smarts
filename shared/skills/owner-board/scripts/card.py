"""Create or change one card, then rebuild the board and reconcile it.

The card files are the truth, and one truth is edited in one way. This writes the card,
regenerates `status.html`, `state.json` and the directory page, and runs the reconciliation,
so a card can never change without the page and the check seeing it. A card's id is
`<author>-<UTC stamp>` from this brain's `owner_short_name`, so two brains never write one name;
its body is edited only by its author (another author saves an `amend` event instead).

    python card.py [--board <id>] new --track <track> --state building --version 1.4.0 \
                                 --branch fix/x --title "<the owner's words>" --landed "..." \
                                 --review "..." --where-text "Product - Page" --where-href "<link>" \
                                 [--note <release-note slug>]
    python card.py [--board <id>] set  <id> --state needs_review --version 1.4.0 --branch -
    python card.py [--board <id>] show <id>
    python card.py [--board <id>] list
    python card.py [--board <id>] drop <id>      # a card written by mistake, never a closed one

`--branch -` clears the branch, which is what merging a card means. Any field not named is left
exactly as it was: a partial edit never silently drops the rest of the card.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import board_config  # noqa: E402
import build_status  # noqa: E402
import cards  # noqa: E402
import events  # noqa: E402

FIELDS = ["track", "state", "version", "branch", "increment", "asked", "startedAt",
          "title", "landed", "review", "image", "where_text", "where_view", "where_href", "release_note"]


def now() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def one(board: dict, card_id: str) -> dict:
    for card in cards.load(board)["items"]:
        if card["id"] == card_id:
            return card
    raise SystemExit("no card with id " + card_id)


def apply(card: dict, args) -> dict:
    for field in FIELDS:
        value = getattr(args, field, None)
        if value is None:
            continue
        if field.startswith("where_"):
            card.setdefault("where", {})[field.split("_", 1)[1]] = "" if value == "-" else value
        elif value == "-":
            card[field] = None
        else:
            card[field] = value
    if args.area is not None:
        card["area"] = args.area
    return card


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    board_config.add_common_arguments(p)
    p.add_argument("--board", help="board id (default: the board whose folder holds the current directory, or the only one)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("new", "set"):
        q = sub.add_parser(name)
        if name == "set":
            q.add_argument("id")
        for field in FIELDS:
            flag = "--note" if field == "release_note" else "--" + field.replace("_", "-")
            q.add_argument(flag, dest=field)
        q.add_argument("--area", nargs="*")
    for name in ("show", "drop"):
        sub.add_parser(name).add_argument("id")
    sub.add_parser("list")
    args = p.parse_args(argv)
    config = board_config.load(args)
    board = config.board(args.board)

    if args.cmd == "list":
        for card in events.state(board)["items"]:
            print("%-26s %-13s %-9s %-22s %s" % (
                card["id"], (card.get("fold") or card.get("state") or "-"), card.get("version") or "-",
                card.get("branch") or "-", (card.get("title") or "")[:58]))
        return 0
    if args.cmd == "show":
        card = one(board, args.id)
        for key in sorted(card):
            print(key + ":", str(card[key])[:300])
        return 0
    if args.cmd == "drop":
        card = one(board, args.id)
        if card.get("closed"):
            raise SystemExit(args.id + " is closed; a closed card is never dropped")
        if card.get("author") != board["author"]:
            raise SystemExit(args.id + " was written by " + str(card.get("author")) + "; only its author drops it")
        path = os.path.join(cards.cards_folder(board), args.id + ".md")
        os.remove(path)
        print("removed", path)
        build_status.build(config, board)
        return 0

    if args.cmd == "new":
        moment = events.utc()
        taken = {c["id"] for c in cards.load(board)["items"]}
        # The id carries the moment in UTC; `created` keeps it as a local time with its offset.
        card = {"id": events.new_id(board["author"], moment, taken), "author": board["author"],
                "asked": datetime.date.today().isoformat(), "created": moment.astimezone().isoformat(),
                "startedAt": now(), "state": "building", "area": [], "where": {}}
    else:
        card = one(board, args.id)
        if card.get("author") != board["author"]:
            raise SystemExit(args.id + " was written by " + str(card.get("author"))
                             + "; a card's body is edited only by its author - save an amend event instead")
    card = apply(card, args)
    if not card.get("track"):
        raise SystemExit("a card needs a track")
    print("wrote", cards.write(board, card))
    build_status.build(config, board)
    return 0


if __name__ == "__main__":
    sys.exit(board_config.cli(main))
