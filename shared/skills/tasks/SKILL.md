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
    - /shared/skills/repository-preflight
  created: 2026-09-23T13:10:00+10:00
  updated: 2026-09-23T13:10:00+10:00
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
- Run `scripts/tasks.py` (read-only).

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
2. Find the next number: `tasks.py next-id`.
3. Copy `/memory/tasks/templates/TASK_TEMPLATE.md` to
   `open/TASK-YYYY-NNNN-<short-slug>.md` (or `inbox/` when it still needs clarifying), set `id`
   to `TASK-YYYY-NNNN`, and fill title, status, owner, priority, timestamps and `project_refs`.
4. Set `due` only for a real deadline. Waiting or scheduled work gets `next_review`, and waiting
   work names what it waits on in `waiting_on`.
5. Add the row to `/memory/tasks/STATE.md` with the status word.

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
| `tasks.py next-id [--year YYYY]` | The next free task number across all folders |

Common options: `--tasks <path>` (repository-root or absolute; default `/memory/tasks`) and
`--json`. Standard library only; nothing is written.

Tests: `python -m unittest discover -s shared/skills/tasks/scripts/tests -v`.

## Outputs

Task records and `STATE.md` rows in `/memory/tasks/`; review tables in the reply. The script
prints only.

## Permissions

Writes only inside `/memory/tasks/` and to the state of nodes a task references. Checking an
awaited external party uses that system's skill and its permissions; a write there still needs
the target confirmed (CONTRACT §10.5).

## Failure behaviour

- A record the script cannot parse is reported by `check`; fix it before relying on the review.
- An unclear owner or outcome: keep the task in `inbox/` and ask the owner, with a suggestion.
- A review that cannot reach the awaited system: leave the status, set a near `next_review`, and
  say so.

## Logging behaviour

Each task carries its own history. A structural change to the store (a bulk move, a
renumbering, a change of rules) gets one entry in `/memory/tasks/LOG.md`.

## State, knowledge and task update behaviour

`/memory/tasks/STATE.md` changes with every open-task change (its operating rule). Durable
lessons about running tasks go to `/memory/tasks/KNOWLEDGE.md`. Node `STATE.md` files change
when a completed task changes their reality.
