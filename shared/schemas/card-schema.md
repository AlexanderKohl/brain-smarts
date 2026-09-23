---
id: schema-card
title: Board Card Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T19:35:05+10:00
updated: 2026-09-23T19:35:05+10:00
---

# Board Card Schema

Read `/CONTRACT.md` first. A card is the record of one thing the owner asked for, shown on a
board by `/shared/skills/owner-board/`. Cards are owner content: one file per card at
`/memory/projects/<node>/status/cards/<card-id>.md`. Cards are written only through
`card.py`, never by hand; this schema says what that script writes and what every reader may
rely on. A test in `/shared/skills/owner-board/scripts/tests/` fails when the code and this
schema disagree.

```yaml
---
id: short-card-id
title: The owner's words, as close to verbatim as they fit
type: board_card
schema_version: 0.2
contract: /CONTRACT.md
parent: /memory/projects/<node>
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: brain-owner
track: a key from the board's tracks
state: queued
version: null
branch: null
increment: null
asked: YYYY-MM-DD
startedAt: null
area: []
where_text: Product – Page
where_view: null
where_href: null
image: null
---

# The owner's words

## What landed

What actually changed, with the numbers.

## To check

What the owner does next: which page to open, what to look at, what would prove it.
```

## Fields

In the order `card.py` writes them: identity, then where the card sits on the board, then when
it moved, then where the owner goes to look. Any other key follows, alphabetically.

| Field | Meaning |
|---|---|
| `id` | Card id, unique within its board (not across boards); the file name without `.md` |
| `title` | The owner's words, as close to verbatim as they fit |
| `type` | Always `board_card` |
| `schema_version` | Metadata schema version, `0.2` |
| `contract` | Always `/CONTRACT.md` |
| `parent` | The project node that owns the board |
| `created` | When the owner asked; kept for the life of the card |
| `updated` | Every write moves it |
| `owner` | The board's owner |
| `track` | The board track the card belongs to, a key from `board.md` |
| `state` | One of the states below |
| `version` | The version the owner can load to check it, once the work has merged |
| `branch` | The branch the work is on; empty once merged |
| `increment` | Which increment of the track's task the card belongs to |
| `asked` | The date the owner asked |
| `startedAt` | When work began |
| `area` | List of product areas the card touches (the only list field) |
| `where_text` | Where to look, in words |
| `where_view` | A view key the board configuration turns into a link |
| `where_href` | A direct link to the place in the product |
| `image` | An optional image shown on the card |

Body sections, each optional:

| Section | Meaning |
|---|---|
| `## What landed` | What changed, with numbers; says so when an earlier diagnosis was wrong |
| `## To check` | What the owner does next |
| `## … sent it back` | The owner's words when they returned it, verbatim |

## States

In the order the board shows them: what the owner has to do, then what is coming toward them,
then what is not moving.

| State | Board label | Meaning |
|---|---|---|
| `needs_review` | Needs you | Merged, with a version the owner can load; waits for the owner's verdict |
| `rework` | Sent back | The owner returned it; their words are in the body |
| `building` | Being built | Work in progress |
| `yours` | Yours elsewhere | Something the owner does outside the brain |
| `queued` | Queued | Asked for, not started |

The legacy state `waiting_on_you` is still read and drawn with `needs_review`; do not write it.

Lifecycle: `queued` → `building` → `needs_review` → closed by the owner's verdict, or
`rework` → `building`. **Only the owner's verdict retires a card:** `accepted` deletes the card
file and records its version and title under `closed` in the board's `board.md`.

## Rules

- One file per card; the board page is generated from the cards and never edited as a source.
- Write cards with `card.py`, which writes, regenerates the page and reconciles in one act.
- Card records live in memory and carry the owner's own words; the schema and the skill are core
  mechanics and carry none (`SMART-RULE-0008`).
