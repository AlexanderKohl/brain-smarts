---
name: tasks
description: Capture, process, review and close tasks in the owner's task store at /memory/tasks/ under CONTRACT §9 – including the task review that surfaces inbox items, reviews that have come due, near deadlines and blocked work. Use when work is implied but not finished in the turn, when the owner asks what is open or due, at session start, or when an external scheduler runs the task review.
metadata:
  id: skill-tasks
  title: Tasks
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  owner: brain-owner
  canonical_source: /shared/skills/tasks
  script_paths:
    - /shared/skills/tasks/scripts/tasks.py
  skill_refs:
    - /shared/skills/owner-board
    - /shared/skills/repository-preflight
  created: 2026-09-23T13:10:00+10:00
  updated: 2026-09-29T08:50:29+10:00
---

# Tasks

Read `/CONTRACT.md` first. CONTRACT §9 defines the task system and the rules in
`/memory/tasks/RULES.md` govern the store; this skill is the operating procedure and the
**task-review skill** that CONTRACT §9.1 refers to. It may not weaken either.

## Purpose

Give every agent the same concrete way to put work into the task store, move it through its
statuses, and find what needs attention, so a waiting item surfaces on its review date without
anyone holding it in their head.

## Allowed operations

- Create, update and move task records under `/memory/tasks/` (`inbox/`, `open/`,
  `completed/`, `recurring/`), and keep `/memory/tasks/STATE.md` in step.
- Update the state of a node a task references when its completion changes that node's reality.
- Run `scripts/tasks.py`: `review`, `check` and `next-id` only read; `new` writes one record,
  its `STATE.md` row and the generated board pages; `done`, `do-now` and `note` change one
  record, its `STATE.md` row and screenshots under `/memory/tasks/img/`.

Not allowed: deleting a task record (cancel it and move it to `completed/`), creating a task for
work finished in the same turn, or giving a task a second owner.

## Required inputs

- The task store, `/memory/tasks/` (the skeleton ships it; `--tasks` points elsewhere).
- For a new task: an outcome or next action, the one owner, and the projects it touches.

## Data sources

The task records, `/memory/tasks/STATE.md`, and the `STATE.md` of each referenced node.

## Procedures

### 1. Capture

1. Work that is implied and will not be finished this turn becomes a task; work finished now
   does not.
2. Create it with one command, which is the creation path:

   ```powershell
   python shared/skills/tasks/scripts/tasks.py new --title "<the outcome, in the owner's words>" `
       --status ready --priority high --project /memory/projects/<node> [--project ...] `
       [--due YYYY-MM-DD] [--next-review YYYY-MM-DD --waiting-on "<who or what>"] `
       [--outcome "..."] [--next-action "..."]
   ```

   It takes the next number across every folder, copies `/memory/tasks/templates/TASK_TEMPLATE.md`
   to `open/TASK-YYYY-NNNN-<slug>.md` (or `inbox/` for `--status inbox`, the default, when the
   task still needs clarifying) with title, status, owner, priority, timestamps and
   `project_refs` filled, adds the row to `/memory/tasks/STATE.md` for an open task (and sets
   the count in the `## Open tasks (N, ...)` heading above that table), and – when the owner
   board is set up – regenerates the one board the task lands on, so it is on that board at once
   (see **Boards** below).

   **Timestamps** are in the owner's timezone, the IANA name in `timezone` in
   `/memory/OWNER.md`, when Python has a zone database for it. Windows usually has none unless
   the `tzdata` package is installed (`python -m pip install tzdata`); without it `new` stamps
   the machine's zone, and says so in its output when that offset is not one of the offsets
   written after the zone name (for example `Australia/Brisbane (+10:00)`). `--now` overrides
   the stamp.

   **Git Bash on Windows** rewrites `/memory/...` into a Windows path before the script sees
   it; put `MSYS_NO_PATHCONV=1` in front of the command there. `new` refuses a `--project` value
   that is not a repository-root path under `/memory/` (or another existing `/` path in the
   brain), and names the fix.
3. Order `--project` deliberately: **the first project that has a board decides which board
   shows the task**; a task with no project, or whose projects have no board, is shown on the
   owner's personal board.
4. Set `due` only for a real deadline. Waiting or scheduled work gets `--next-review`, and
   waiting work names what it waits on in `--waiting-on`; the command refuses either without
   them.
5. Fill the rest of the body (current position, completion criteria) in the record. Creating a
   record by hand is still allowed: copy the template, take `tasks.py next-id`, add the
   `STATE.md` row, then run the board rebuild below.

### 2. Process the inbox

For each record in `inbox/`: give it an outcome, one owner and project references, then set a
status and move it to `open/`; or complete it now and record that; or cancel it. Nothing stays
in `inbox/` across a review without a reason in its body.

### 3. Review

Run at session start when the owner asks what is open, when a task view is requested, and when
an external scheduler invokes this skill:

```powershell
python shared/skills/tasks/scripts/tasks.py review
```

It lists, once each: blocked tasks, inbox items, tasks past `due`, tasks whose `next_review`
has come, and tasks due within the horizon (seven days by default; `--horizon N`), earliest
first. For each row:

1. **Review due, waiting:** check whether the awaited party or event has moved (with the
   relevant skill when it is reachable); then advance the status, or set a new `next_review`
   and add a dated line to the task's history.
2. **Overdue or due soon:** tell the owner, with a suggested next action.
3. **Blocked:** name what would unblock it and ask the owner if that is theirs to decide.
4. **Inbox:** procedure 2.

Report the result to the owner as a short table; do not paste the full output when nothing
changed.

### 4. Update and close

1. Every status change updates the record's `status`, `updated` and history, and the row in
   `STATE.md`.
2. On `completed` or `cancelled`, move the record to `completed/`, remove its `STATE.md` row,
   and update the state of each referenced node when reality changed.
3. A task that gains several dependent actions, contributors or real risks becomes a project
   (CONTRACT §9.4); link the task to the new node and close or narrow it.
4. Three changes have one command each, and the owner board applies the owner's saved task
   actions through the same functions (`complete`, `do_now`, `add_note`), so a task changes one
   way only:

   ```powershell
   python shared/skills/tasks/scripts/tasks.py done TASK-YYYY-NNNN [--note "..."]
   python shared/skills/tasks/scripts/tasks.py do-now TASK-YYYY-NNNN [--note "..."]
   python shared/skills/tasks/scripts/tasks.py note TASK-YYYY-NNNN --note "..."
   ```

   - `done`: status `completed`, `updated` stamped (owner's timezone), a History entry with the
     note, the record moved to `completed/`, its `STATE.md` row removed and the open-task count
     corrected, and a line at the top of `STATE.md`'s *Recently completed* when that section
     exists. A completed task is refused.
   - `do-now`: priority `high`, status `ready` unless it is `in_progress`, a History entry
     *Asked for now* with the note; an inbox task moves to `open/` and gains its row. A completed
     task is refused: reopen it by hand.
   - `note`: a History entry with the owner's words, nothing else.

   The note is kept verbatim. Screenshots (only through the owner board) are written to
   `/memory/tasks/img/<task>-<stamp>-<n>.<ext>` and linked from the entry; only PNG, JPEG, WebP
   and GIF data is kept. An unknown id is an error. Each command refreshes the board unless
   `--no-board`.

### Boards

When `owner-board` is active, every open task is shown on exactly one board, drawn from its
record – never copied – with columns by status (inbox, ready, in progress, waiting with what it
waits on and its review date, scheduled, blocked, completed recently). The routing and the
pages belong to `/shared/skills/owner-board/SKILL.md` (**Tasks on the boards**). An open task
card carries *Do now*, *Done* and a note box for the owner; the page changes nothing itself, and
`apply_verdicts.py` applies what the owner saved through procedure 4.4, then prints the owner's
*Do now* list. `tasks.py new`, `done`, `do-now` and `note` refresh the board themselves; after
changing a record by hand (a status, `project_refs`, a move to `completed/`), run

```powershell
python shared/skills/owner-board/scripts/task_board.py --no-fetch build
```

### 5. Check

```powershell
python shared/skills/tasks/scripts/tasks.py check
python shared/skills/repository-preflight/scripts/preflight.py
```

`check` covers required fields, whether each status belongs in its folder, the identifier and
file name, date formats, and warns on waiting tasks without `waiting_on`. The preflight
validator separately enforces valid statuses, `next_review` on waiting and scheduled tasks, and
that `STATE.md` lists every open task with its status word.

## Scripts or commands

| Command | Role |
|---|---|
| `tasks.py review [--today YYYY-MM-DD] [--horizon N]` | What needs attention, as a Markdown table |
| `tasks.py check` | Record validation; exit code 1 on errors |
| `tasks.py new --title ... [--status] [--priority] [--project ...] [--due] [--next-review] [--waiting-on] [--no-board]` | Create a record from the template with the next number, claimed atomically under `.claims/` so concurrent sessions never share one, add its `STATE.md` row, refresh its board |
| `tasks.py done <id> [--note] [--now] [--no-board]` | Complete a task: History, move to `completed/`, `STATE.md` row out |
| `tasks.py do-now <id> [--note] [--now] [--no-board]` | Priority high, status ready unless in progress, History |
| `tasks.py note <id> --note ... [--now] [--no-board]` | A History entry with the owner's note |
| `tasks.py next-id [--year YYYY]` | The next free task number across all folders and live claims |
| `scheduled_review.py [--register \| --status \| --unregister] [--no-notify]` | Read-only review with no model: writes the ignored `/temp/due.md` (each repository compared with origin, the weekly learning digest when due, tasks due, skill exchange, preflight) and shows a desktop notification when something needs attention. `--register` runs it daily at 07:00 from the operating system's scheduler – Windows Task Scheduler, a launchd agent on macOS, a systemd user timer on Linux (cron without systemd) – catching up after the computer was off except under cron, always from the shared checkout named in `/memory/OWNER.md`; `--status` shows it and `--unregister` removes it. Set up per computer in `/SETUP.md` G.2. Once registered, follow-up is real under CONTRACT §14 |

Common options: `--tasks <path>` (repository-root or absolute; default `/memory/tasks`) and
`--json`. Standard library only; `new`, `done`, `do-now` and `note` write.

Tests: `python -m unittest discover -s shared/skills/tasks/scripts/tests -v`.

## Outputs

Task records and `STATE.md` rows in `/memory/tasks/`; review tables in the reply; through
`new`, the regenerated board page that shows the task and `/memory/boards/index.html`.

## Permissions

Writes only inside `/memory/tasks/`, to the state of nodes a task references, and (through the
owner-board script) to generated board pages. Checking an
awaited external party uses that system's skill and its permissions; a write there still needs
the target confirmed (CONTRACT §10.5).

## Failure behaviour

- A record the script cannot parse is reported by `check`; fix it before relying on the review.
- An unclear owner or outcome: keep the task in `inbox/` and ask the owner, with a suggestion.
- A review that cannot reach the awaited system: leave the status, set a near `next_review`, and
  say so.
- `new` cannot refresh the board (owner board not set up, or its build failed): the record and
  its `STATE.md` row stay created, and the output names the command to run once it is fixed.

## Logging behaviour

Each task carries its own history. A structural change to the store (a bulk move, a
renumbering, a change of rules) gets one entry in `/memory/tasks/LOG.md`.

## State, knowledge and task update behaviour

`/memory/tasks/STATE.md` changes with every open-task change (its operating rule). Durable
lessons about running tasks go to `/memory/tasks/KNOWLEDGE.md`. Node `STATE.md` files change
when a completed task changes their reality.
