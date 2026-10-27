---
id: skill-owner-board
title: Owner Board
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 1.1.1
script_paths:
  - /shared/skills/owner-board/scripts/apply_events.py
  - /shared/skills/owner-board/scripts/board_config.py
  - /shared/skills/owner-board/scripts/build_boards.py
  - /shared/skills/owner-board/scripts/build_status.py
  - /shared/skills/owner-board/scripts/card.py
  - /shared/skills/owner-board/scripts/cards.py
  - /shared/skills/owner-board/scripts/events.py
  - /shared/skills/owner-board/scripts/migrate_board.py
  - /shared/skills/owner-board/scripts/page_html.py
  - /shared/skills/owner-board/scripts/page_js.py
  - /shared/skills/owner-board/scripts/page_notes.py
  - /shared/skills/owner-board/scripts/reconcile.py
  - /shared/skills/owner-board/scripts/task_actions.py
  - /shared/skills/owner-board/scripts/task_board.py
  - /shared/skills/owner-board/scripts/team_lanes.py
created: 2026-09-18T11:05:00+10:00
updated: 2026-10-22T16:47:15+10:00
owner: brain-owner
project_refs:
  - /memory/projects/brain-development
skill_refs:
  - /shared/skills/delegate-work
  - /shared/skills/tasks
  - /shared/skills/release-notes
---

# Owner Board

Read `/CONTRACT.md` first. This skill sits under `SMART-RULE-0024` (delegated parallel work)
and carries the operating detail for the one thing that rule does not cover: **how the owner
sees what is in play, and how the owner's decision gets back into the files.**

It is optional: an owner switches it on by listing `owner-board` in `active_skills` in
`/memory/OWNER.md` (see `/SETUP.md`, step C). The owner's own boards, configuration and history
are in `/memory/skills/owner-board/`. A board for a project that more than one brain works on
lives in that project's repository instead, in `brain/status/`, and every such brain is a peer
(CONTRACT section 16.2; **Two brains on one board** below).

## Purpose

Give the owner **one link that never changes**, showing every request they have made, what
state it is in, and what they have to look at – and let their verdict travel back as data
rather than as text they copy into a message and a conductor retypes. The same boards show the
owner's **tasks**: every open task record appears on exactly one board – its project's, or the
personal board – read from `/memory/tasks/` each time, never copied into a card.

The board is not a status report the conductor writes. **It is derived from the records**, and
a check runs on every regeneration comparing it against git. A board a conductor could keep by
hand is a board that can be quietly wrong, which is worse than a list.

## Where things live

There is **one implementation**, in this skill's `scripts/` folder, and it serves every board
(`SMART-RULE-0018`). Boards hold data only.

    /shared/skills/owner-board/scripts/          the scripts (this skill)
    /memory/skills/owner-board/config/boards.json the owner's registry and per-board settings
    /memory/<node>/status/                        a memory board: board.json, cards/, events/, the pages
    <repository>:brain/status/                    a shared board, the same layout, in the project repository
    /memory/boards/index.html                     the directory above every board (generated)
    /memory/boards/personal.html                  the personal task board (generated)
    /memory/boards/projects/<slug>.html           task pages: automatic boards, and the tasks of each shared board (generated)
    /memory/tasks/                                the task records boards show and reconcile against
    /memory/skills/owner-board/applied/           saved verdict files once their events are written (this brain's own)

The scripts find the brain root by moving upwards to `CONTRACT.md` from the current folder (or
from their own folder), then read `memory/skills/owner-board/config/boards.json` beneath it
(CONTRACT section 3.5). Every command also takes `--root <brain root>` and
`--config <file>`. No script names a machine path.

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
      "status": "example-garden:brain/status",
      "node": "/memory/projects/example-garden",
      "blurb": "The planting app, in the words the owner would use",
      "repo": "{project_repos_root}/example-garden",
      "production": "origin/main",
      "release_notes": ["garden-app"],
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
| `node` | from `status` | Repository-root path of the owning memory node: where this owner's tasks about the project route. A memory board derives it from `status`; a shared board names its pointer node here, and its cards carry the repository's own node (`<repository>:brain`) as `parent`. |
| `placeholder_pattern` | `temp`, `wip`, `fixup`, `squash` | Check 2: a main head commit message that was never written. |
| `production` | `origin/main` | The branch releases go to. After a hotfix it is ahead of `main`; check 4 never reports it as pushed and unmerged, and check 6 never calls its checkout a stray. |
| `release_notes` | `[]` | Project ids from `/memory/skills/release-notes/config/release-notes.json` or, for a shared board, the repository's `brain/status/release-notes.json`, whose notes this board draws, in the order drawn (**Release notes on the board**). |
| `remote` | `origin` | The product remote. |
| `repo` | none | Product checkout. `{project_repos_root}` and `{brain_root}` are filled from `/memory/OWNER.md`; a relative path is taken under `project_repos_root`. Without it only the task checks run. |
| `status` | required | The board folder: relative to the memory root (`projects/<node>/status`), or `<repository>:brain/status` for a board shared through a project repository found under `project_repos_root`. |
| `storage_prefix` | `<id>-status` | Browser storage keys; keep it stable or saved but unapplied verdicts in the browser are lost. |
| `title` | `<label>: where we are` | Page title. |
| `verdict_prefix` | `<id>-verdicts-` | Saved verdict file names. |
| `verdict_schema` | `owner-board/verdicts/v1` | The `schema` value inside a verdict file. |
| `where_view_href` | none | Builds a card's link from its `where_view`. `{view}` is the card's value; any other `{name}` is a top-level field of `board.json`; a part in `[...]` is dropped when a field it uses is empty. |

`directory` keys, alphabetical: `favicon` (the tab icon of every generated page – an SVG string,
a `data:` URI, or a file path relative to the directory folder; default a neutral three-column
board glyph, inlined so a `file://` page needs no second file; a named file that is missing
stops the build), `folder` (default `boards`, under the memory root) and `title` (default
`Boards`).

`tasks` keys, alphabetical, all optional (see **Tasks on the boards**):

| Key | Default | Meaning |
|---|---|---|
| `auto_boards` | `false` | Off: a task whose projects have no registered board goes to the personal board. On: its first project under `auto_roots` gets a generated task-only board. |
| `auto_folder` | `projects` | Where automatic boards and the task pages of shared boards are written, under the directory folder. |
| `auto_roots` | `["/memory/projects/"]` | Which references may get an automatic board. |
| `board_declined` | `[]` | Projects the owner said need no board of their own; the build stops suggesting one for them or any folder beneath them (`SMART-RULE-0035`). |
| `completed_days` | `14` | How long a completed or cancelled task stays in *Completed recently*. |
| `enabled` | `true` | `false` draws no tasks anywhere. |
| `personal` | see the example | The personal board: `id` (must not be a registered board id), `label`, `page` (relative to the directory folder), `blurb`. |
| `store` | `tasks` | The task store, relative to the memory root. |
| `wip_limit` | `2` | How many cards one team may hold *in progress* at once. Each board page lists every team present above the columns as `team · in progress n / limit`, in the warning colour when n exceeds it. |

## Invocation and required inputs

Invoked by any conductor working on a node that has a board. Requires the configuration file
and, for the git checks, a working checkout of the product repository the board names.

## Data sources

- `<board>/cards/*.md` – **one card per owner request**, named `<author>-<UTC stamp>`. The
  truth of what was asked and what landed. `<board>/cards/closed/` holds retired cards.
- `<board>/events/*.json` – **one file per decision**, append-only: what each person decided
  about a card, and which versions a release retired (**The events**).
- `<board>/board.json` – what a person keeps by hand and rarely: `tracks` (each with `label`,
  `task`, `done`, `of`), `production`, `release_notes`, `abandoned` (branch -> a one-line
  reason; a named branch is silenced by checks 4 and 6), `elsewhere`, and any identifiers
  `where_view_href` uses. Nothing derived lives here: the product's version comes from git on
  every build, and the `closed` register is folded from the events.
- `<board>/state.json` and `<board>/status.html` – **derived** on every build, never kept by
  hand, never merged; on a shared board both are ignored by Git and rebuilt after every pull.
- The product repository, read by `reconcile.py`: branches, worktrees, merges, built output.
- The owner's Downloads folder and every folder directly inside it – what the owner saved
  from a board, until `apply_events.py` turns it into events.
- `/memory/skills/owner-board/config/boards.json` – every board that exists.

## Allowed operations and permissions

Write under a board's folder and the directory folder only. A card's body is written only by
its author; an event is written once and never edited, moved or deleted. Never close a card on
the owner's behalf – see **A verdict or a release retires a card**. No credentials. The only
product-repository operations are reads, `git fetch`, and `git mv` of a card into
`cards/closed/` by the author whose event retired it. A shared board's folder never receives a
`/memory/` path or a task; the build refuses to write a page that would carry one.

## Procedure

### Making a board

1. Copy `/shared/skills/owner-board/templates/board.template.json` to `<board>/board.json`,
   set `id` and `label` to the board's registry values, add the tracks, and create empty
   `cards/` and `events/` folders beside it. A memory board lives at `<node>/status/` and
   `status/` is added to the node's `README.md` (CONTRACT section 4). A shared board lives at
   `<repository>:brain/status/`, `status/` is added to `brain/README.md`, and
   `brain/status/status.html` and `brain/status/state.json` are added to the repository's
   `.gitignore`.
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

    queued -> building -> needs_review -> (a verdict, or the production release) -> closed
                              |
                              +-> rework -> building

A card is created when the owner asks for something. It moves to `needs_review` when the work
merges, carrying the version the owner can load. **A verdict or a release retires it.** A
`yours` card is something the owner does elsewhere; `waiting_on_you` is drawn with
`needs_review`. Two folds sit above the columns: **Conflict**, for a card two people decided
differently, and **Released**, for a card whose version reached testing and that nobody has
judged yet.

### Writing a card

Always through `card.py`, never by editing the file by hand:

    python shared/skills/owner-board/scripts/card.py --board <id> new --track <track> \
        --branch fix/x --title "<the owner's words>" --landed "..." --review "..." \
        --where-text "Product - Page" --where-href "<link>" [--note <release-note slug>]
    python shared/skills/owner-board/scripts/card.py --board <id> set <card-id> \
        --state needs_review --version 1.4.0 --branch -
    python shared/skills/owner-board/scripts/card.py --board <id> list

It names the card `<author>-<UTC stamp>` from this brain's `owner_short_name`, writes it,
regenerates the page, `state.json` and the directory, and runs the reconciliation in one act, so
a card cannot change without the check seeing it. `--branch -` clears the branch, which is what
merging means. `--note` names the release note the change belongs to. `--board` may be left out
inside a board's folder or when only one board is registered. `set` and `drop` refuse a card
another author wrote: that author's brain changes it, or you save an `amend` event.

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

The owner decides on the card face – *Accepted*, *Send back*, *Not now* – and presses **Save my
verdicts**, which hands the browser one JSON file naming its board, as a download, and says in
the bar which file it was. Any folder inside Downloads will do: `apply_events.py` reads Downloads
and every folder directly inside it, so whichever folder the save dialog offers is fine. A
folder remembered through the File System Access API was tried on 26 September 2026 and failed
twice on a real owner's Chrome for a page opened from disk; it was removed rather than kept as a
second path.

A screenshot pasted into a card's reason box travels with the verdict. The page shrinks it to at
most 1600px wide, shows it as a thumbnail with a remove button, and puts it in the saved file.
Applying writes it to `<board>/img/<event-id>-<n>.<ext>`, named by the event so two brains never
write one name, and the board draws it under the owner's words. Only `data:image/` PNG, JPEG,
WebP or GIF is kept.

The owner then sends one short message, and the conductor runs:

    python shared/skills/owner-board/scripts/apply_events.py            # every saved file, then settle
    python shared/skills/owner-board/scripts/apply_events.py --dry-run  # say, change nothing
    python shared/skills/owner-board/scripts/apply_events.py --settle   # effects only, after a pull

Each verdict becomes **one event file** under `<board>/events/`, after three fences: the card
still exists; its signature is the one the verdict was given against; and the page had seen the
card's latest event (`seen_through`). A verdict that fails a fence is **refused and reported** –
"pull, rebuild, decide again" for a stale page – and a file from another board is refused: card
ids are only unique within a board. Then the fold runs and this brain does its share of the
effects (**Two brains on one board**). The saved file moves to
`/memory/skills/owner-board/applied/`, this brain's own record of what it handed over.

- *accepted* retires the card: its version and title enter the derived `closed` register and the
  card file moves to `cards/closed/`.
- *sent back* sets the card to `rework` and keeps **the owner's words verbatim**: on the page
  from the event, and in the card under its own heading (`## <owner> sent it back`) once the
  card's own brain has run `apply_events.py`.
- *not now* leaves the card where it is, tagged with who deferred it and why.

### Two brains on one board

Two brains, no hierarchy, one shared truth: the board folder in the project repository. Each
conductor **pulls, builds its own page, saves verdicts and adds cards, applies what it saved,
commits and pushes**; the other side pulls, and its next build derives the same state
(CONTRACT 16.3).

**Records that never clash.** Every card and every event is one file named
`<author>-<UTC stamp>`, the author being `owner_short_name` from that brain's `/memory/OWNER.md`,
lowercased; two saves by one author in one second get `-2`, `-3`. Two authors cannot produce
one name, so Git never sees two versions of a new file. A card's body is edited only by its
author; another author who wants a change saves an `amend` event with the text, drawn on the
card. An event is written once and never edited, moved or deleted: "applied" is not a place a
file is moved to, it is a fact each brain derives.

**The events.** Kinds: `accept`, `reject`, `defer`, `amend`, `released`, `resolve`. Each names
`card`, `by`, `saved_at`, the card signature it was decided against and `seen_through`, the id
of the last event on that card the page had seen. Events sort by `(saved_at, author, id)` and
cards by `(created, author)`, the same on both machines; the fold (`events.fold`) is recomputed
from the whole log on every build, so it gives one answer whatever order the files arrived in.
An outcome overlays the card while the card still carries the signature it was decided against;
once its author acts on it (sets it building again after a reject), the old event no longer
applies.

**When both act on one card.** Both events are kept. **The earliest event decides**; a later
event with a different outcome does not change the state but marks the card `conflict`. The page
draws it in the *Conflict* fold on both sides, showing both verdicts with author and time, until
either person saves a `resolve` naming every conflicting event id and the outcome; a `resolve`
that does not name every one is refused (the resolver must have seen them). A same-outcome
duplicate is not a conflict; the second is drawn as "also accepted by <author>".

**Catching a brain that has not pulled.** Three fences, in the order they bite: at save, the
page embeds `seen_through` on every card and the commit it was built from; at apply,
`apply_events.py` refuses an event whose `seen_through` is not the card's current last event, or
whose signature no longer matches; at push, `session.py finish`
(`/shared/skills/repository-preflight/`) fetches first, rebuilds, reruns the apply, and only
then pushes.

**Applying is each brain's own share.** After the fold, `apply_events.py` does only the side
effects that belong to the brain running it, each idempotent: a card retired by an event of
*this* author is moved (`git mv`) to `cards/closed/`, and the other brain receives the move by
pull; the words of a reject are written into the card when *this* brain is the card's author;
task actions change this brain's own task records. A card already in `cards/closed/` is left
alone. If both authors save the same outcome before either pulls, both move the same file to the
same name with the same content, which Git merges clean.

**What never enters the repository.** Each owner's tasks about the project stay in that owner's
`/memory/tasks/`, drawn on a page of their own at `/memory/boards/projects/<board id>.html`,
never on the shared page; `build_status.py` refuses to write a shared page that carries a
`/memory/` path or a task section. The generated `status.html` and `state.json` are ignored by
Git and rebuilt after every pull.

### Release notes on the board

A board whose entry carries `release_notes: ["<project id>", ...]` draws, below its cards, a
**Release notes** section for those projects (`/shared/skills/release-notes/`): every
unreleased note with its visibility choice and in-place editing, the commits no note claims
(**New note**, **Add to an existing note**, **Not user-visible**), and a lane per environment
of what has been released to testing and to production. The choices save with the verdicts
(`releaseNotes` in the same file) and `apply_events.py` hands them to
`release_choices.apply_choices`, which writes one append-only choice event each. A card names
its note with `--note <slug>`; check 11 asks for one when a version raised the first or middle
number. The library skill is imported from the brain root only when a board names projects, so
owner-board stays a core skill with an optional dependency.

A shared board also draws the projects its repository defines in `brain/status/release-notes.json`
(the release-notes skill, *Projects, boards and team pages*), so a brain without the owner's
release-notes configuration still shows the section; an entry with the same id in the owner's
memory configuration wins. The board loads it through the skill's `load_config`, the same
function `release_notes.py --repo` uses. A missing library skill, an unknown project, an unreadable
repository file or a folder that leaves the repository (through `..` or a link) is a short
visible line in the section as well as a line of the build's report.

**The release retires cards.** `release_notes.py release <version> --env testing|production`
writes one `released` event per open card at or below that version on every board that draws
the project: a testing release puts the card in the *Released* fold, where **Accept all
released** saves an accept for each; a production release retires it on both brains at the
next build. A card nobody judged before the production release is retired by the release, not
by a verdict; the note is what remains of it.

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

**Where they are drawn.** A memory board shows its tasks in a *Tasks* section below the cards
on its own `status.html` – still one link. A shared board's tasks are this owner's own and are
drawn on `/memory/boards/projects/<board id>.html`, linked from the directory beside the board.
The personal and automatic boards are pages of their own beside the directory, rewritten by
`build_boards.py` on every regeneration of any board. The directory lists the personal board
first, then the registered boards (each with an open-task count), then automatic boards by
label; tasks past due or due for review are counted in the warning colour.

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

Only a task with an action chosen is sent. A note with no action means the owner is still
deciding: it stays on its card and in the browser, tagged *Note only · stays until you choose*,
and no save, copy or clear takes it away until **Do now** or **Done** is picked (the owner's
rule, 26 September 2026).

Saving hands them to the agent. On a board, **Save my verdicts** adds a `tasks` array
(`{id, action, note, shots, title}`) to the verdicts file, and the tally and *Copy instead*
include them. The personal and automatic pages have the same bar and save
`task-actions-<savedAt>.json` (schema `owner-board/task-actions/v1`, board `tasks`). Whatever was
saved or copied leaves the browser's storage. `apply_events.py` finds both kinds of file in the
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
`apply_events.py` ends with a **Do now** list: act on it first. Applied task-actions files move
to `/memory/tasks/actions-applied/`.

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
| `apply_events.py` | Turn every saved verdicts file into events after the fences, hand release-note choices and task actions on, settle this brain's effects, print the Do now list, rebuild. `--settle` after a pull. |
| `board_config.py` | Find the brain root and memory, read and validate `boards.json`, resolve a `<repository>:brain/status` board. Imported by the others. |
| `build_boards.py` | Generate `/memory/boards/index.html` from the registry. |
| `build_status.py` | Fold the events and generate a board's `status.html` and `state.json` (`--all` for every board), then the directory. |
| `card.py` | Create, change, show, list or drop one card, then rebuild and reconcile. |
| `cards.py` | Read and write card records and `board.json`; owns the signature; writes `state.json`. Imported by the others. |
| `events.py` | Ids, the append-only event files, the fold and the fences. Imported by the others and by the release-notes skill. |
| `migrate_board.py` | Convert a board from `board.md` and verdict folders to `board.json` and events, in place or into a repository; `--dry-run` first (**Migrating a board**). |
| `page_html.py` | The status page: HTML, CSS and the board's own browser code, including the folds. Imported by `build_status.py`. |
| `page_js.py` | The browser code every board page shares: screenshots, lightbox, download, task controls, the task pages' save bar. Imported by the builders. |
| `page_notes.py` | The release-notes section of a board page. Imported by `build_status.py`. |
| `reconcile.py` | Compare a board with git and the task records. Called by every build. |
| `task_actions.py` | Apply the owner's saved task actions through the tasks skill. Imported by `apply_events.py`. |
| `task_board.py` | Route task records to boards and draw them: `route`, `build [--for <task>]`, `check`. |
| `team_lanes.py` | The per-team work-in-progress line above a board's task columns. Imported by `task_board.py`. |

Common options: `--root`, `--config`, `--no-fetch`, and `--board` where a command acts on one
board. Tests (fictional data only, authors `sam` and `bob`):

    python -m unittest discover -s shared/skills/owner-board/scripts/tests -v

## What the reconciliation checks

Numbered as in `reconcile.py`; checks 1 to 8 need `repo`.

1. A merge left in progress in the product checkout.
2. A main-branch head commit with a placeholder message.
3. The built product is not the committed version.
4. A branch pushed and not merged that no card is building, `abandoned` does not name and is
   not the board's `production` branch.
5. A `building` or `rework` card with no branch, a merged branch, or a branch that exists
   nowhere after the grace period (unless the card says `writes: none`).
6. A worktree no card mentions.
7. A worktree whose branch is already merged.
8. A version merged into main with no card, not in `closed`, and whose merge subject names no
   task that exists under `/memory/tasks/` (open or completed): a merge such as
   `Merge 1.4.0: paths (TASK-2026-0903)` is the task flow's own record and counts as seen.
9. A derived key (`closed`, `mainVersion`, `generated`) kept by hand in `board.json`: the
   version is read from git and the register is folded from the events on every build, so a
   kept copy can only go stale and is reported until the key is removed.
10. A track's task has no record, is missing from `/memory/tasks/STATE.md`, or still says
    `ready` while the track has landed work or a card in flight. Memory boards only: a shared
    board's tracks may name a task the other brain does not have.
11. On a board that draws release notes: a card ready for review whose version raised the
    first or middle number above every closed version and that names no release note.

## Templates

| Template | Copied to |
|---|---|
| `templates/board.template.json` | `<board>/board.json`, when a board is made |

## Outputs

`status.html` and `state.json`, regenerated in place at the permanent path; card records under
`cards/` and `cards/closed/`; event records under `events/`; screenshots under `img/`;
`/memory/boards/index.html`, `/memory/boards/personal.html`, the task pages of shared boards
and any automatic task boards, refreshed on every regeneration; saved verdict files filed under
`/memory/skills/owner-board/applied/`.

## Failure behaviour

A card or an event that cannot be parsed **raises** rather than being skipped: a record that
vanishes quietly is the exact failure this machinery exists to end. A reconciliation that
cannot run is drawn on the page as an error rather than as silence, and a missing product
checkout is said, not skipped. A verdict on a card that has changed, or decided on a page that
had not seen the card's latest event, is refused and says so. A shared page that would carry a
`/memory/` path or a task is refused, not written. A missing or invalid configuration stops the
command with one plain line and exit code 2.

## Logging and state, knowledge and task updates

Commit card and event changes with named paths (`git commit -- <paths>`); other sessions share
the memory repository, and the other brain shares the project repository. After a packet lands,
update the parent task's status word and its row in `/memory/tasks/STATE.md` on the same pass –
see **A status word is written when work starts and never when it finishes** in
`/shared/skills/delegate-work/SKILL.md`.

## The five rules this was built out of

**1. A verdict or a release retires a card.** A conductor that deletes cards on merge removes
work the owner has never seen at the moment it becomes theirs to look at. Merging moves a card
to `needs_review` and sets its version. Only a person's verdict, or the production release that
carries the version to everyone, retires it – and either is an event in the log, never a
deletion.

**2. The board holds what the conductor is *not* doing, too.** Work in the owner's other
threads, work committed to main by another session, branches abandoned with the version that
superseded them. A version that landed and has no card is invisible to the owner however good
the rest of the board is.

**3. There is one truth, and it is the files.** A hand-kept status file beside task records
beside an index is three lists that must agree with nothing keeping them in step. **A generated
copy of the truth is still a second list**, so the state is derived from the cards and the
events on every build and never kept. Cards are Markdown records so `preflight.py` validates
them like everything else.

**4. The check runs whether the conductor wants it or not.** Every build calls
`reconcile.py`, so reconciliation happens on every regeneration and its findings are drawn at
the top of the page where the owner sees them too. Each check exists because the owner, not a
conductor, was the one who had found that kind of drift.

**5. Say the correction in the same place as the claim.** When a diagnosis given to the owner
turns out to be wrong, the card that carried it says so – not a later message they have to
connect back. A board that only ever reports success teaches the owner to check everything
themselves, which is the cost the board exists to remove.

## Migrating a board, and the way a migration lies

`migrate_board.py --board <id> [--to <repository>:brain/status] [--dry-run]` converts a board
from the hand-kept layout (`board.md`, slug-named cards, `verdicts-in/`, `verdicts-applied/`) to
this one: `board.json` with only the hand-kept keys, cards renamed `<author>-<UTC created>`, one
event per applied verdict, and one `accept` event without a card per version of the old `closed`
register, so the register stays honest and derived. With `--to` it writes into the repository,
adds the generated files to its `.gitignore`, repoints the board's `status` in `boards.json`, and
leaves the old folder for the conductor to `git mv` out of memory with its removed-files note;
it then lists any file that still says `/memory/`. Run it with `--dry-run` first and read the
plan.

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
