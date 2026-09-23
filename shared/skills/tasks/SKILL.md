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
  updated: 2026-09-23T15:00:00+10:00
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
  its `STATE.md` row and the generated board pages.

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
   `project_refs` filled, adds the row to `/memory/tasks/STATE.md` for an open task, and – when
   the owner board is set up – regenerates the one board the task lands on, so it is on that
   board at once (see **Boards** below).
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

### Boards

When `owner-board` is active, every open task is shown on exactly one board, drawn from its
record – never copied – with columns by status (inbox, ready, in progress, waiting with what it
waits on and its review date, scheduled, blocked, completed recently). The routing and the
pages belong to `/shared/skills/owner-board/SKILL.md` (**Tasks on the boards**). Tasks carry no
verdict: a status changes in the record. `tasks.py new` refreshes the board itself; after
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
| `tasks.py new --title ... [--status] [--priority] [--project ...] [--due] [--next-review] [--waiting-on] [--no-board]` | Create a record from the template with the next number, add its `STATE.md` row, refresh its board |
| `tasks.py next-id [--year YYYY]` | The next free task number across all folders |

Common options: `--tasks <path>` (repository-root or absolute; default `/memory/tasks`) and
`--json`. Standard library only; only `new` writes.

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
