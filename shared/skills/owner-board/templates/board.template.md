---
id: skill-owner-board-board-template
title: The board
type: reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
parent: NODE_PATH
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# The board

Copy this file to `<node>/status/board.md` (`/shared/skills/owner-board/SKILL.md`, **Making a
board**). Set `id` to `<node-slug>-status-board`, `parent` to the node's repository-root path
(for example `/memory/projects/brain-development`), `owner`, `created` and `updated`; in the
JSON block set `id` and `label` to the same values as the board's entry in
`/memory/skills/owner-board/config/boards.json`, and `generated` to the current time. Delete
this paragraph.

Each card the owner can act on is its own file under `cards/`, written by `card.py`. What is
kept here belongs to the board and to no single card: the tracks and their parent tasks, the
versions the owner has closed, and branches abandoned with what superseded them.

```json
{
  "id": "BOARD_ID",
  "label": "BOARD_LABEL",
  "generated": "YYYY-MM-DDTHH:mm:ss+HH:MM",
  "mainVersion": "",
  "tracks": {},
  "closed": {},
  "abandoned": {},
  "elsewhere": {}
}
```

Keys, alphabetical: `abandoned` (branch -> what superseded it), `closed` (version -> what the
owner accepted), `elsewhere` (work in the owner's other threads), `generated`, `id`, `label`,
`mainVersion` (the product's version on its main branch; empty without a product
repository) and `tracks` (track key -> `{"label", "task", "done", "of"}`; a card names its
track, so add one before the first card).
