---
id: skill-owner-board
title: Owner Board
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
created: 2026-09-18T11:05:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
project_refs:
  - /memory/projects/brain-development
skill_refs:
  - /shared/skills/delegate-work
---

# Owner Board

Read `/CONTRACT.md` first. This skill sits under `RULE-2026-0037` (delegated parallel work)
and carries the operating detail for the one thing that rule does not cover: **how the owner
sees what is in play, and how the owner's decision gets back into the files.**

Built across 17–18 September 2026, after four pieces of work went quiet in a conductor's hands
in a single day and the owner found every one of them. The reference implementation and the
owner-specific history are named in `/memory/skills/owner-board/NOTES.md`.

## Purpose

Give the owner **one link that never changes**, showing every request they have made, what
state it is in, and what they have to look at – and let their verdict travel back as data
rather than as text they copy into a message and a conductor retypes.

The board is not a status report the conductor writes. **It is generated from the records**,
and a check runs on every regeneration comparing it against git. A board a conductor could
keep by hand is a board that can be quietly wrong, which is worse than a list.

## Where boards live

Project nodes, boards and tasks are owner data, so they all live under `/memory/`:

    /memory/projects/<node>/status/     one board per project node
    /memory/boards/                     the directory above every board
    /memory/tasks/                      the task records a board reconciles against

The scripts locate each other **relatively**, so the whole arrangement works wherever the
memory folder is checked out, provided these three stay siblings inside it:

- a board's `build-status.py` finds the directory at `../../../boards/build-boards.py`
  (from `<memory>/projects/<node>/status/`);
- `reconcile.py` finds tasks at `../../../tasks/open/` and `../../../tasks/STATE.md`;
- `build-boards.py` and `apply-verdicts.py` resolve every registry `status` path against the
  folder that holds `boards/` – the memory root – so a registry entry says
  `projects/<node>/status`, never `memory/projects/...` and never an absolute path.

A project that lives in its own repository keeps a pointer node under `/memory/projects/`;
its board stays in that pointer node's `status/` folder and `reconcile.py` reads the product
repository from the path named at its top (`REPO`), which should come from the owner's
configuration rather than a literal machine path.

## Invocation and required inputs

Invoked by any conductor working on a project node that has a `status/` folder. Requires the
node path and a working git checkout of the product repository the board reconciles against
(`REPO` at the top of `reconcile.py`).

## Data sources

- `<node>/status/cards/*.md` – **one card per owner request**. The truth.
- `<node>/status/board.md` – what belongs to the board and to no single card: tracks and
  their parent tasks, the target environment, closed versions, abandoned branches.
- The product repository, read by `reconcile.py`: branches, worktrees, merges, `dist`.
- `<node>/status/verdicts-in/*-verdicts-*.json` – what the owner saved from the board.
- `/memory/boards/registry.md` – every board that exists. **The directory above them all.**

## Allowed operations and permissions

Write under `<node>/status/` only. Never edit a card to record a verdict the owner has not
given. Never close a card on the owner's behalf – see **A card is closed only by the owner**.
No credentials, no live calls to the product's external systems.

## Procedure

### One board, one link, forever

The board is a file at a fixed path inside the node:

    <node>/status/status.html

**The owner bookmarks that path once and it never changes.** Every conductor regenerates that
same file; nobody hands the owner a new link. A different *project node* gets its own board at
its own `status/` path, because the reconciliation is against that project's repository – but
within a project, the link is permanent across every future conductor and every future thread.

If a conductor finds itself about to say *here is your new board*, it has made a second one.
Regenerate the existing file instead.

### A new board registers itself in the directory

The owner keeps **`/memory/boards/index.html`** bookmarked. It lists every board and how many
cards on each are waiting for them, so a project they have not opened in a fortnight cannot go
quiet without the count saying so.

**Creating a board is not finished until it is in `/memory/boards/registry.md`.** Add one entry:

```json
{
  "id": "<short-slug>",
  "label": "<what the owner calls the project>",
  "node": "/memory/projects/<node>",
  "status": "projects/<node>/status",
  "blurb": "<one line, in words the owner would use, not the project's own name>"
}
```

`status` is relative to the memory root (see **Where boards live**). Then make that board's
`build-status.py` run `/memory/boards/build-boards.py` at the end, the way the reference
implementation does. The directory then refreshes whenever any board does and nobody has to
remember it – **a page that is right only when somebody remembers is a page that will be
wrong**, which is the same reason `reconcile.py` is imported rather than invoked.

**A board that is not in the directory is one the owner never opens, which is the same as not
having one.** This is a step of making the board, not a follow-up to it.

The directory reads each board through that board's *own* `cards.py` and `reconcile.py`,
loaded by path. So a board may change how it stores things without the directory knowing,
and the count shown here is always the board's own answer rather than a second opinion that
could disagree with it.

### The lifecycle

    queued -> building -> needs_review -> (the owner accepts) -> closed
                              |
                              +-> rework -> building

A card is created when the owner asks for something. It moves to `needs_review` when the work
merges, carrying the version the owner can refresh to. **Only the owner's verdict retires it.**

### Writing a card

Always through `card.py`, never by editing the file by hand and never by editing a second
copy somewhere else:

    python card.py new <id> --track <track> --version 0.170.0 --branch fix/x \
                            --title "<the owner's words>" --landed "..." --review "..." \
                            --where-text "Product - Page" --where-href "<link>"
    python card.py set <id> --state needs_review --version 0.170.0 --branch -
    python card.py list

It writes the card, regenerates the page and runs the reconciliation in one act, so a card
cannot be changed without the check seeing it.

**What goes in each field:**

- **`title`** is *the owner's words*, as close to verbatim as they will fit. A card titled
  *Improve page readability* is the conductor's summary of a complaint; a card titled
  *still not readable* is the complaint. People recognise their own sentence and do not
  recognise a paraphrase of it.
- **`landed`** is what actually changed, **with the numbers**. Not *fixed the overlap* but
  *1,400 overlapping text pairs before, 0 at every zoom now*. If a diagnosis the conductor
  gave earlier turned out to be wrong, the card says so in the same breath.
- **`review`** is what *the owner* does next: which page to open, what to look at, what would
  prove it. Not a restatement of `landed`.
- **`where`** is a real link to the place in the product, not a description of it.

### Taking the verdict back

The owner decides on the card face and presses **Save my verdicts**, which hands the browser
one JSON file and clears the cards decided. **It saves into `<node>/status/verdicts-in/`** -
beside the cards the verdict applies to, inside the repository, so a decision never sits in
a user profile the conductor has no business reading. The browser asks once and remembers
the folder. Downloads is read as a fallback, because that is where a browser puts a file
when nobody tells it otherwise and a verdict that landed in the ordinary place must be
found rather than silently ignored.

The owner then sends one short message. Apply it:

    python verdicts.py              # newest file in Downloads
    python verdicts.py --dry-run    # say what would happen, change nothing

- *accepted* retires the card: version and title into `board.md` under `closed`, card file
  deleted.
- *rework* sets the card to `rework` and keeps **the owner's words verbatim**, under their own
  heading above the conductor's line. A reason folded into the conductor's text stops being
  the owner's.
- A verdict whose signature no longer matches the card is **refused and reported**, not applied.

### Then act on it

A card in `rework` with no branch is work nobody is doing. Dispatch it (see
`/shared/skills/delegate-work`) or move it, and let `reconcile.py` be the thing that notices –
not the owner.

## Four are running, or there is nothing ready

Adopted 21 September 2026 (the owner's instruction is recorded in
`/memory/skills/owner-board/NOTES.md`): **if there is ready work, up to four workers run
without waiting to be asked.**

**Reporting is not a stopping point.** The moment a worker finishes, the next piece of ready
work starts, without being asked.

Four is `RULE-2026-0037`'s ceiling, not a number to seek permission for. So the queued column
is a **queue to pull from**, not a list of things awaiting approval - and keeping it stocked is
part of the job, because an empty queue is what turns a finished worker into an idle conductor.

**A decision the owner owes is not a reason to idle.** Take the recommended option, build it,
and say on the card that it was the conductor's judgement and is cheap to change. A wrong guess
the owner can send back costs far less than an afternoon in which nothing ran.

**Two things are not waiting, and both stay stopped:**

- work the owner has explicitly **paused** - building it anyway is deciding to unpause it;
- anything needing the owner's written authorisation in a live external system (`CONTRACT` 10.5).

Say which of those applies on the card, so a stopped card never reads as a forgotten one.

## Scripts or commands

| Script | Job |
| --- | --- |
| `cards.py` | Read and write card records; owns the signature. |
| `card.py` | Create or change one card, then rebuild and reconcile. |
| `build-status.py` | Generate `status.html` from the cards. |
| `reconcile.py` | Compare the board against git. Imported by the generator, so it always runs. |
| `verdicts.py` | Apply a saved verdicts file back onto the cards. |
| `/memory/boards/build-boards.py` | Generate the directory page from the registry. |
| `/memory/boards/apply-verdicts.py` | Route a verdicts file to the board it belongs to. |

## Outputs

`status.html`, regenerated in place at the permanent path; card records under `cards/`;
`closed` entries in `board.md`; applied verdict files filed under `status/verdicts-applied/`;
and `/memory/boards/index.html`, refreshed on every regeneration.

## Failure behaviour

A card that cannot be parsed **raises** rather than being skipped: a card that vanishes quietly
is the exact failure this machinery exists to end. A reconciliation that cannot run is drawn on
the page as an error rather than as silence. A verdict on a card that has changed is refused.

## Logging and state, knowledge and task updates

Commit card changes with named paths (`git commit -- <paths>`); other sessions share the memory
repository. After a packet lands, update the parent task's status word and its row in
`/memory/tasks/STATE.md` on the same pass – see **A status word is written when work starts and never
when it finishes** in `/shared/skills/delegate-work/SKILL.md`.

## The five rules this was built out of, and what each one cost

Every one of these was paid for. They are here so the next conductor does not pay again.

**1. A card is closed only by the owner.** A conductor was deleting cards on merge, so work the
owner had never seen left the board at the moment it became theirs to look at. Merging moves a
card to `needs_review` and sets its version. Nothing else retires it.

**2. The board holds what the conductor is *not* doing, too.** Work in the owner's other
threads, work committed to `main` by another session, branches abandoned with the version that
superseded them. A *Yours elsewhere* column exists for the first of those. A version that landed
and has no card is invisible to the owner however good the rest of the board is – and it has
happened twice, both times found by the check rather than by a person.

**3. There is one truth, and it is the files.** The board lived in a hand-kept `status.json`
beside task records beside an index: three lists that must agree with nothing keeping them in
step, sitting in the conductor's own tooling. `status.json` was deleted rather than regenerated
– **a generated copy of the truth is still a second list.** Cards are Markdown records so
`preflight.py` validates them like everything else.

**4. The check runs whether the conductor wants it or not.** `build-status.py` imports
`reconcile.py`, so reconciliation happens on every regeneration and its findings are drawn at
the top of the page where the owner sees them too. It has caught, on its own: a branch pushed
and never merged, three dispatched packets with no cards, a whole track removed from the board,
two versions landing with no card, a task still marked `ready` after ten increments shipped,
and another thread's worktree the conductor did not know existed. **Every one of those had
previously been found by the owner.**

**5. Say the correction in the same place as the claim.** When a diagnosis given to the owner
turns out to be wrong, the card that carried it says so – not a later message they have to
connect back. Two on one day: *your records carry a broken character* (they did not; the
conductor's console was reading the file as the wrong encoding) and *acknowledgements are never
read back* (they are; the real fault was a two-second timing window). A board that only ever
reports success teaches the owner to check everything themselves, which is the cost the board
exists to remove.

## Migrating the board, and the way a migration lies

When `status.json` became one file per card, the converter handled the fields its author
had in mind and wrote `round trip: clean`. **It compared eight fields and the cards had
ten.** `where.view` - the product page a card points at, from which the board builds the
link - was in neither the converter nor the check, so seven cards lost their link, the
verification passed, and the owner found it two hours later.

Two rules come out of that, and they are cheap:

- **Compare the whole record, not the fields you thought of.** A migration check that
  enumerates fields can only ever confirm what its author already knew. Diff the old
  structure against the new one key by key, and let anything unrecognised fail.
- **Write empty as empty.** The same converter wrote an empty value as the two characters
  `[]` and read them back as the *string* `"[]"`, which is not empty and which nothing
  downstream could recognise as empty - the page drew `<a href="[]">`. An empty field is
  written as a bare key.

And the fix that mattered more than either: **a rule about a value must not depend on
which field produced it.** The copy-instead-of-link behaviour was set only on the branch
that *built* the address from `where.view`, so a card written with a ready-made
`where.href` got a plain link that the browser refuses. It now keys off the address itself.

## Deferred by design

**Write-back without a message.** The board hands the browser a download because a `file://`
page is not a secure context and cannot write to disk. A local process could, and was not
built: the conductor only exists between the owner's messages, so a verdict saved silently
would sit unread and the owner would have *less* signal than when they pasted text. **One word
in the thread is the whole protocol**, and the file is what removes the need for that word to
carry the content.
