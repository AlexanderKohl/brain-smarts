---
id: skill-owner-board
title: Owner Board
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/owner-board/scripts/apply_verdicts.py
  - /shared/skills/owner-board/scripts/board_config.py
  - /shared/skills/owner-board/scripts/build_boards.py
  - /shared/skills/owner-board/scripts/build_status.py
  - /shared/skills/owner-board/scripts/card.py
  - /shared/skills/owner-board/scripts/cards.py
  - /shared/skills/owner-board/scripts/page_js.py
  - /shared/skills/owner-board/scripts/reconcile.py
  - /shared/skills/owner-board/scripts/task_actions.py
  - /shared/skills/owner-board/scripts/task_board.py
  - /shared/skills/owner-board/scripts/verdicts.py
created: 2026-09-18T11:05:00+10:00
updated: 2026-09-26T16:00:00+10:00
owner: brain-owner
project_refs:
  - /memory/projects/brain-development
skill_refs:
  - /shared/skills/delegate-work
  - /shared/skills/tasks
---

# Owner Board

Read `/CONTRACT.md` first. This skill sits under `SMART-RULE-0024` (delegated parallel work)
and carries the operating detail for the one thing that rule does not cover: **how the owner
sees what is in play, and how the owner's decision gets back into the files.**

It is optional: an owner switches it on by listing `owner-board` in `active_skills` in
`/memory/OWNER.md` (see `/SETUP.md`, step C). The owner's own boards, configuration and history
are in `/memory/skills/owner-board/`.

## Purpose

Give the owner **one link that never changes**, showing every request they have made, what
state it is in, and what they have to look at – and let their verdict travel back as data
rather than as text they copy into a message and a conductor retypes. The same boards show the
owner's **tasks**: every open task record appears on exactly one board – its project's, or the
personal board – read from `/memory/tasks/` each time, never copied into a card.

The board is not a status report the conductor writes. **It is generated from the records**,
and a check runs on every regeneration comparing it against git. A board a conductor could
keep by hand is a board that can be quietly wrong, which is worse than a list.

## Where things live

There is **one implementation**, in this skill's `scripts/` folder, and it serves every board
(`SMART-RULE-0018`). Boards hold data only.

    /shared/skills/owner-board/scripts/          the scripts (this skill)
    /memory/skills/owner-board/config/boards.json the owner's registry and per-board settings
    /memory/<node>/status/                        one board per node: cards, board.md, page
    /memory/boards/index.html                     the directory above every board (generated)
    /memory/boards/personal.html                  the personal task board (generated)
    /memory/boards/projects/<slug>.html           automatic task boards, when switched on (generated)
    /memory/tasks/                                the task records boards show and reconcile against

The scripts find the brain root by moving upwards to `CONTRACT.md` from the current folder (or
from their own folder), then read `memory/skills/owner-board/config/boards.json` beneath it
(CONTRACT section 3.5). Every command also takes `--root <brain root>` and
`--config <file>`. No script names a machine path.

A board's folder is usually `/memory/projects/<node>/status/`; a project that lives in its own
repository keeps its board in the pointer node's `status/` folder and names its product
checkout in the configuration.

## Configuration

`/memory/skills/owner-board/config/boards.json`. The memory skeleton ships it with the
directory and personal-board defaults and an empty `boards` list, so the personal board and the
directory are generated from the first task, before any project board exists. `pages` lists other
generated pages the directory links to, after the personal board – a contact register's page, for
example; each names its file relative to the directory folder. A full example:

```json
{
  "owner_name": "optional – defaults to owner_short_name in /memory/OWNER.md",
  "directory": {"folder": "boards", "title": "Boards", "favicon": "optional - see below"},
  "tasks": {
    "auto_boards": false,
    "completed_days": 14,
    "personal": {"id": "personal", "label": "Personal tasks", "page": "personal.html"}
  },
  "pages": [
    {"label": "Contacts", "page": "contacts.html", "blurb": "Every contact, searchable, with their to-dos"}
  ],
  "boards": [
    {
      "id": "garden",
      "label": "Garden Planner",
      "status": "projects/example-garden/status",
      "blurb": "The planting app, in the words the owner would use",
      "repo": "{project_repos_root}/example-garden",
      "committed_version": {"file": "package.json", "key": "version"},
      "built_version": {"file": "dist/manifest.json", "key": "version"},
      "where_view_href": "example-app://{appId}/index.html[?plot={plotId}]#{view}"
    }
  ]
}
```

Board keys, alphabetical. Only `id`, `label` and `status` are required.

| Key | Default | Meaning |
|---|---|---|
| `blurb` | empty | One line on the directory page, in the owner's words. |
| `built_version` | none | `{file, key}` or `{file, regex}` in the product checkout; check 3 compares it with `committed_version`. |
| `committed_version` | none | `{file, key}` or `{file, regex}` read from the main branch with `git show`; drives checks 3, 4 and 9. |
| `copy_only_prefixes` | browser-internal schemes | Addresses a `file://` page may not open, so the card copies them instead of linking. |
| `favicon` | the directory's | This board's tab icon; the same forms as the directory's `favicon`. |
| `fetch` | `true` | Fetch the product remote before reconciling; `--no-fetch` turns it off for one run. |
| `grace_minutes` | `15` | How long a new card may name a branch that does not exist yet. |
| `id` | required | Short slug; also names verdict files and browser storage by default. |
| `label` | required | What the owner calls the project. |
| `main` | `main` | The product's main branch. |
| `merge_version_pattern` | `N.N.N` | How check 8 recognises a version in a merge subject. |
| `node` | from `status` | Repository-root path of the owning node; written into each card's `parent`. |
| `placeholder_pattern` | `temp`, `wip`, `fixup`, `squash` | Check 2: a main head commit message that was never written. |
| `remote` | `origin` | The product remote. |
| `repo` | none | Product checkout. `{project_repos_root}` and `{brain_root}` are filled from `/memory/OWNER.md`; a relative path is taken under `project_repos_root`. Without it only the task checks run. |
| `status` | required | The board folder, relative to the memory root. |
| `storage_prefix` | `<id>-status` | Browser storage keys; keep it stable or saved but unapplied verdicts in the browser are lost. |
| `title` | `<label>: where we are` | Page title. |
| `verdict_prefix` | `<id>-verdicts-` | Saved verdict file names. |
| `verdict_schema` | `owner-board/verdicts/v1` | The `schema` value inside a verdict file. |
| `where_view_href` | none | Builds a card's link from its `where_view`. `{view}` is the card's value; any other `{name}` is a top-level field of `board.md`'s JSON; a part in `[...]` is dropped when a field it uses is empty. |

`directory` keys, alphabetical: `favicon` (the tab icon of every generated page – an SVG string,
a `data:` URI, or a file path relative to the directory folder; default a neutral three-column
board glyph, inlined so a `file://` page needs no second file; a named file that is missing
stops the build), `folder` (default `boards`, under the memory root) and `title` (default
`Boards`).

`tasks` keys, alphabetical, all optional (see **Tasks on the boards**):

| Key | Default | Meaning |
|---|---|---|
| `auto_boards` | `false` | Off: a task whose projects have no registered board goes to the personal board. On: its first project under `auto_roots` gets a generated task-only board. |
| `auto_folder` | `projects` | Where automatic boards are written, under the directory folder. |
| `auto_roots` | `["/memory/projects/"]` | Which references may get an automatic board. |
| `board_declined` | `[]` | Projects the owner said need no board of their own; the build stops suggesting one for them or any folder beneath them (`SMART-RULE-0035`). |
| `completed_days` | `14` | How long a completed or cancelled task stays in *Completed recently*. |
| `enabled` | `true` | `false` draws no tasks anywhere. |
| `personal` | see the example | The personal board: `id` (must not be a registered board id), `label`, `page` (relative to the directory folder), `blurb`. |
| `store` | `tasks` | The task store, relative to the memory root. |

## Invocation and required inputs

Invoked by any conductor working on a node that has a board. Requires the configuration file
and, for the git checks, a working checkout of the product repository the board names.

## Data sources

- `<board>/cards/*.md` – **one card per owner request**. The truth.
- `<board>/board.md` – what belongs to the board and to no single card, in one fenced JSON
  block: `id`, `label`, `mainVersion`, `tracks` (each with `label`, `task`, `done`, `of`),
  `closed`, `abandoned`, `elsewhere`, and any identifiers `where_view_href` uses.
- The product repository, read by `reconcile.py`: branches, worktrees, merges, built output.
- `<board>/verdicts-in/*.json` – what the owner saved from the board; the owner's Downloads
  folder is read as a fallback.
- `/memory/skills/owner-board/config/boards.json` – every board that exists.

## Allowed operations and permissions

Write under a board's folder and the directory folder only. Never edit a card to record a
verdict the owner has not given. Never close a card on the owner's behalf – see **A card is
closed only by the owner**. No credentials. The only product-repository operations are reads
and `git fetch`.

## Procedure

### Making a board

1. Copy `/shared/skills/owner-board/templates/board.template.md` to `<node>/status/board.md`,
   fill it as its first paragraph says, create an empty `cards/` folder beside it, and add
   `status/` to the node's `README.md` (CONTRACT section 4).
2. **Register it** in `boards.json`. Creating a board is not finished until it is registered:
   a board missing from the directory is one the owner never opens, which is the same as not
   having one.
3. Run `build_status.py --board <id>` and give the owner the path of `status.html` once.

### One board, one link, forever

The board is a file at a fixed path, `<board>/status.html`. **The owner bookmarks that path
once and it never changes.** Every conductor regenerates the same file; nobody hands the owner a
new link. If a conductor finds itself about to say *here is your new board*, it has made a
second one.

The owner also bookmarks `/memory/boards/index.html`, which lists every board and how many
cards on each are waiting. Every regeneration of any board rebuilds it, so it cannot be older
than the newest board – **a page that is right only when somebody remembers is a page that will
be wrong.**

### The lifecycle

    queued -> building -> needs_review -> (the owner accepts) -> closed
                              |
                              +-> rework -> building

A card is created when the owner asks for something. It moves to `needs_review` when the work
merges, carrying the version the owner can load. **Only the owner's verdict retires it.** A
`yours` card is something the owner does elsewhere; `waiting_on_you` is drawn with
`needs_review`.

### Writing a card

Always through `card.py`, never by editing the file by hand:

    python shared/skills/owner-board/scripts/card.py --board <id> new <card-id> --track <track> \
        --branch fix/x --title "<the owner's words>" --landed "..." --review "..." \
        --where-text "Product - Page" --where-href "<link>"
    python shared/skills/owner-board/scripts/card.py --board <id> set <card-id> \
        --state needs_review --version 1.4.0 --branch -
    python shared/skills/owner-board/scripts/card.py --board <id> list

It writes the card, regenerates the page and the directory and runs the reconciliation in one
act, so a card cannot change without the check seeing it. `--branch -` clears the branch, which
is what merging means. `--board` may be left out inside a board's folder or when only one board
is registered.

**What goes in each field:**

- **`title`** is *the owner's words*, as close to verbatim as they will fit. People recognise
  their own sentence and do not recognise a paraphrase of it.
- **`landed`** is what actually changed, **with the numbers** – not *fixed the overlap* but
  *1,200 overlapping pairs before, 0 at every zoom now*. If a diagnosis given earlier turned
  out to be wrong, the card says so in the same breath.
- **`review`** is what *the owner* does next: which page to open, what to look at, what would
  prove it.
- **`where`** is a real link to the place in the product (`--where-href`), or a `--where-view`
  the configuration turns into one.

### Taking the verdict back

The owner decides on the card face and presses **Save my verdicts**, which hands the browser one
JSON file naming its board, as a download, and says in the bar which file it was. Any folder
inside Downloads will do: `apply_verdicts.py` reads Downloads and every folder directly inside
it, as well as `<board>/verdicts-in/`, so whichever folder the save dialog offers is fine. A
folder remembered through the File System Access API was tried on 26 September 2026 and failed
twice on a real owner's Chrome for a page opened from disk; it was removed rather than kept as a
second path.

A screenshot pasted into a card's reason box travels with the verdict. The page shrinks it to at
most 1600px wide, shows it as a thumbnail with a remove button, and puts it in the saved file.
Applying a *rework* writes it to `<board>/img/<card>-<saved>-<n>.<ext>` and adds it as an image
line under the owner's words, where the board draws it. Only `data:image/` PNG, JPEG, WebP or
GIF is kept.

The owner then sends one short message, and the conductor runs:

    python shared/skills/owner-board/scripts/apply_verdicts.py            # every saved file
    python shared/skills/owner-board/scripts/apply_verdicts.py --dry-run  # say, change nothing

- *accepted* retires the card: version and title into `board.md` under `closed`, card file
  deleted.
- *rework* sets the card to `rework` and keeps **the owner's words verbatim**, under their own
  heading (`## <owner> sent it back`) above the conductor's line.
- A verdict whose signature no longer matches the card is **refused and reported**, and a file
  from another board is refused: card ids are only unique within a board.
- Applied files move to `<board>/verdicts-applied/`.

`verdicts.py --board <id> [file]` applies one file to one board.

### Tasks on the boards

The task record in `/memory/tasks/` stays the only record of a task (CONTRACT sections 3.3 and
9). `task_board.py` reads the records at every regeneration and draws them; nothing is copied
into `cards/`, so there is no second list to fall out of step.

**Routing** – one rule, in one function, used by every page:

1. Walk the task's `project_refs` in order. The first reference that is a registered board's
   `node`, or a folder beneath it, decides (the deepest matching node wins).
2. With `auto_boards` on, a first reference under `auto_roots` with no registered board gets an
   automatic task-only board at `/memory/boards/projects/<slug>.html`.
3. Otherwise – no references, or only projects without a board – the **personal board**,
   `/memory/boards/personal.html`.

`auto_boards` is off by default, and that is the recommendation: a board is something the owner
opens, and a directory full of one-task boards is one they stop reading. The personal board tags
each task with its project, so nothing is lost by sharing it. When a project's tasks deserve a
page of their own, **make it a board** (Making a board) – its tasks move there at the next
regeneration. An automatic page whose tasks have all gone is kept, drawn empty, because it may
be bookmarked.

**When a project outgrows the personal board** (`SMART-RULE-0035`). Every regeneration counts,
for each project under `auto_roots`, its open tasks on the personal board; a task that names two
projects counts for both, and each project counts on its own, not with its parent. At five or
more, `build_boards.py` prints `suggest a board: <project> (<path>) has <n> open tasks on the
personal board`. The agent then asks the owner once, with a suggested answer. A "yes" is
**Making a board**; a "no" adds the project's path to `tasks.board_declined` in `boards.json`,
which silences it for good. Branch count is not visible to the build (a project without a board
names no repository), so the agent watches for three or more branches itself.

**Where they are drawn.** A registered board shows its tasks in a *Tasks* section below the
cards on its own `status.html` – still one link. The personal and automatic boards are pages of
their own beside the directory, rewritten by `build_boards.py` on every regeneration of any
board. The directory lists the personal board first, then the registered boards (each with an
open-task count), then automatic boards by label; tasks past due or due for review are counted
in the warning colour.

**Columns and order.** Inbox, Ready, In progress, Waiting, Scheduled, Blocked, Completed
recently – the way a task travels. In the action columns (inbox, ready, in progress, blocked)
the order is priority, then the nearest real deadline, then task number: what to do next is at
the top. Waiting and scheduled run by `next_review`, nearest first, because that is when they
come back; each shows `waiting_on` and the review date. Completed runs newest first. A status no
column draws is shown first, in the warning colour, rather than vanishing.

**Do now, Done and a note on every task.** Every open task card, on a board's *Tasks* section
and on the personal and automatic pages, carries two toggles, **Do now** and **Done** (pressing
the chosen one again clears it), and a note box, *Note for the agent – you can paste a
screenshot here*. The title still links to the record, and a click on the controls never follows
that link. The page changes no record: pending actions are kept in the browser under one key
shared by every page (`owner-board-task-actions`; a task is the same task wherever it is drawn),
as `{action: do_now | done | "", note, shots, title}`, and a card with something pending shows a
tag. Completed tasks carry no controls.

Saving hands them to the agent. On a board, **Save my verdicts** adds a `tasks` array
(`{id, action, note, shots, title}`) to the verdicts file, and the tally and *Copy instead*
include them. The personal and automatic pages have the same bar and save
`task-actions-<savedAt>.json` (schema `owner-board/task-actions/v1`, board `tasks`). Whatever was
saved or copied leaves the browser's storage. `apply_verdicts.py` finds both kinds of file in the
same folders and applies each task through the tasks skill (`tasks.complete`, `tasks.do_now`,
`tasks.add_note` – the one way a task changes):

- **done** – status `completed`, `updated` stamped, a History entry with the owner's note, the
  record moved to `completed/`, its `STATE.md` row removed and the open-task count corrected, and
  a line at the top of `STATE.md`'s *Recently completed* where that section exists;
- **do now** – priority `high`, status `ready` unless already `in_progress` (an inbox task moves
  to `open/` and gains its row), a History entry *Asked for now* with the note;
- **a note alone** – a History entry with the note.

Screenshots are written to `/memory/tasks/img/<task>-<saved>-<n>.<ext>` and linked in the History
entry; only PNG, JPEG, WebP or GIF data is kept. An unknown task id is reported and skipped.
`apply_verdicts.py` ends with a **Do now** list: act on it first. Applied task-actions files
move to `/memory/tasks/actions-applied/`; the task actions inside a verdicts file are filed with
it under `verdicts-applied/`. Verdicts on request cards work exactly as before.

The browser code both page kinds share – shrinking a pasted screenshot, the thumbnails and
lightbox, the download, the task controls and the task pages' save bar – is written once, in
`page_js.py`, and inlined into each page.

**A new task appears at once.** `tasks.py new` (the tasks skill) creates the record and runs
`task_board.py build --for <task>`, which rebuilds the one board the task lands on and the
directory. After editing a task record by hand, run

    python shared/skills/owner-board/scripts/task_board.py --no-fetch build

and, to prove what the owner sees, read the pages back:

    python shared/skills/owner-board/scripts/task_board.py route   # which board each task is on
    python shared/skills/owner-board/scripts/task_board.py check   # each open task once, on its board

### Then act on it

A card in `rework` with no branch is work nobody is doing. Dispatch it (see
`/shared/skills/delegate-work`) or move it, and let `reconcile.py` be the thing that notices –
not the owner.

## Ready work runs without waiting

If there is ready work, up to four workers run without waiting to be asked. **Reporting is not a
stopping point**: the moment a worker finishes, the next piece of ready work starts.

Four is `SMART-RULE-0024`'s ceiling, not a number to seek permission for. So the queued column
is a **queue to pull from**, not a list awaiting approval – and keeping it stocked is part of
the job, because an empty queue is what turns a finished worker into an idle conductor.

**A decision the owner owes is not a reason to idle.** Take the recommended option, build it,
and say on the card that it was the conductor's judgement and is cheap to change.

**Two things are not waiting, and both stay stopped:**

- work the owner has explicitly **paused** – building it anyway is deciding to unpause it;
- anything needing the owner's written authorisation in a live external system (CONTRACT 10.5).

Say which of those applies on the card, so a stopped card never reads as a forgotten one.

## Scripts or commands

Run from the brain root. Alphabetical.

| Script | Job |
| --- | --- |
| `apply_verdicts.py` | Route every saved verdicts file to the board it names, apply it and its task actions, apply every task-actions file, print the Do now list, rebuild. |
| `board_config.py` | Find the brain root and memory, read and validate `boards.json`. Imported by the others. |
| `build_boards.py` | Generate `/memory/boards/index.html` from the registry. |
| `build_status.py` | Generate a board's `status.html` (`--all` for every board), then the directory. |
| `card.py` | Create, change, show, list or drop one card, then rebuild and reconcile. |
| `cards.py` | Read and write card records; owns the signature. Imported by the others. |
| `page_js.py` | The browser code every board page shares: screenshots, lightbox, download, task controls, the task pages' save bar. Imported by the builders. |
| `reconcile.py` | Compare a board with git and the task records. Called by every build. |
| `task_actions.py` | Apply the owner's saved task actions through the tasks skill. Imported by `apply_verdicts.py` and `verdicts.py`. |
| `task_board.py` | Route task records to boards and draw them: `route`, `build [--for <task>]`, `check`. |
| `verdicts.py` | Apply one saved verdicts file to one board. |

Common options: `--root`, `--config`, `--no-fetch`, and `--board` where a command acts on one
board. Tests (fictional data only):

    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

## What the reconciliation checks

Numbered as in `reconcile.py`; checks 1 to 9 need `repo`.

1. A merge left in progress in the product checkout.
2. A main-branch head commit with a placeholder message.
3. The built product is not the committed version.
4. A branch pushed and not merged that no card is building and `abandoned` does not name.
5. A `building` or `rework` card with no branch, a merged branch, or a branch that exists
   nowhere after the grace period (unless the card says `writes: none`).
6. A worktree no card mentions.
7. A worktree whose branch is already merged.
8. A version merged into main with no card and not in `closed`.
9. `mainVersion` in `board.md` disagrees with the repository.
10. A track's task has no record, is missing from `/memory/tasks/STATE.md`, or still says
    `ready` while the track has landed work or a card in flight.

## Templates

| Template | Copied to |
|---|---|
| `templates/board.template.md` | `<node>/status/board.md`, when a board is made |

## Outputs

`status.html`, regenerated in place at the permanent path; card records under `cards/`;
`closed` entries in `board.md`; applied verdict files under `verdicts-applied/`;
`/memory/boards/index.html`, `/memory/boards/personal.html` and any automatic task boards,
refreshed on every regeneration.

## Failure behaviour

A card that cannot be parsed **raises** rather than being skipped: a card that vanishes quietly
is the exact failure this machinery exists to end. A reconciliation that cannot run is drawn on
the page as an error rather than as silence, and a missing product checkout is said, not
skipped. A verdict on a card that has changed is refused. A missing or invalid configuration
stops the command with one plain line and exit code 2.

## Logging and state, knowledge and task updates

Commit card changes with named paths (`git commit -- <paths>`); other sessions share the memory
repository. After a packet lands, update the parent task's status word and its row in
`/memory/tasks/STATE.md` on the same pass – see **A status word is written when work starts and
never when it finishes** in `/shared/skills/delegate-work/SKILL.md`.

## The five rules this was built out of

**1. A card is closed only by the owner.** A conductor that deletes cards on merge removes work
the owner has never seen at the moment it becomes theirs to look at. Merging moves a card to
`needs_review` and sets its version. Nothing else retires it.

**2. The board holds what the conductor is *not* doing, too.** Work in the owner's other
threads, work committed to main by another session, branches abandoned with the version that
superseded them. A version that landed and has no card is invisible to the owner however good
the rest of the board is.

**3. There is one truth, and it is the files.** A hand-kept status file beside task records
beside an index is three lists that must agree with nothing keeping them in step. **A generated
copy of the truth is still a second list**, so there is none. Cards are Markdown records so
`preflight.py` validates them like everything else.

**4. The check runs whether the conductor wants it or not.** Every build calls
`reconcile.py`, so reconciliation happens on every regeneration and its findings are drawn at
the top of the page where the owner sees them too. Each check exists because the owner, not a
conductor, was the one who had found that kind of drift.

**5. Say the correction in the same place as the claim.** When a diagnosis given to the owner
turns out to be wrong, the card that carried it says so – not a later message they have to
connect back. A board that only ever reports success teaches the owner to check everything
themselves, which is the cost the board exists to remove.

## Migrating a board, and the way a migration lies

A converter that compares the fields its author had in mind can report *round trip: clean*
while losing a field nobody listed – for example the page reference a card's link is built
from. Two rules come out of that, and they are cheap:

- **Compare the whole record, not the fields you thought of.** Diff the old structure against
  the new one key by key, and let anything unrecognised fail. When replacing a generator,
  render both on the same data and compare what the reader sees.
- **Write empty as empty.** An empty value written as `[]` reads back as the *string* `"[]"`,
  which nothing downstream recognises as empty. An empty field is written as a bare key.

And **a rule about a value must not depend on which field produced it**: whether a card's
address is copied rather than linked is decided by the address itself.

## Deferred by design

**Write-back without a message.** The board writes into a folder the owner chose (or hands the
browser a download), and nothing watches that folder. A local process could, and was not
built: the conductor only exists between the owner's messages, so a verdict saved silently
would sit unread and the owner would have *less* signal than when they pasted text. **One word
in the thread is the whole protocol**, and the file is what removes the need for that word to
carry the content.
