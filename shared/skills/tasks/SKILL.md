---
name: tasks
description: Capture, process, review and close tasks in every task store of the brain under CONTRACT §9 – /memory/tasks/ for tasks with no project, each node's tasks/, and a project repository's brain/tasks/ – including the task review that surfaces inbox items, reviews that have come due, near deadlines and blocked work, and the migration into node stores. Use when work is implied but not finished in the turn, when the owner asks what is open or due, at session start, or when an external scheduler runs the task review.
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
    - /shared/skills/join-project
    - /shared/skills/owner-board
    - /shared/skills/repository-preflight
  created: 2026-09-23T13:10:00+10:00
  updated: 2026-10-23T07:47:06+10:00
---

# Tasks

Read `/CONTRACT.md` first. CONTRACT §9 defines the task system and the tasks `RULES.md` govern
every store; this skill is the operating procedure and the **task-review skill** that CONTRACT
§9.1 refers to. It may not weaken either.

## Purpose

Give every agent the same concrete way to put work into the right task store, move it through
its statuses, and find what needs attention across every store, so a waiting item surfaces on its
review date without anyone holding it in their head, and a task about a shared project is where
every brain that works on it can see it.

## Stores

Every task lives in exactly one store, and the scripts find it there (`scripts/task_stores.py`):

| Store | Folder | Holds |
|---|---|---|
| owner | `/memory/tasks/` | tasks with no project reference |
| memory node | `<node>/tasks/` | tasks whose first project reference names that node (the deepest node a reference is in) |
| pointer-private | `<pointer node>/tasks/` | the owner's private tasks about a project in its own repository (`--private`) |
| repository | `<checkout>/brain/tasks/` | tasks about a project in its own repository, readable by everyone who can read it |

A node is a folder under `/memory/` with a `node_readme` README, other than `/memory/projects/`,
anything below a `tasks`, `skills`, `data`, `sources`, `raw` or `status` folder, and collections
and libraries. A pointer is a node whose README carries `repo_url`; its repository's store branch
is `working_branch` in `brain/JOINING.md`, else the pointer's `default_branch`. A repository not
checked out here is listed and never read or written. Every store has `inbox/`, `open/`,
`completed/` and, when needed, `recurring/`, and a `STATE.md` generated from its records.

## Allowed operations

- Create, update and move task records in every store through `scripts/tasks.py`; regenerate each
  store's `STATE.md` (never edit it by hand).
- Write the companion file `/memory/tasks/private/<task id>.md` for private notes about a task in
  a repository.
- Update the state of a node a task references when its completion changes that node's reality.
- `review`, `check` and `next-id` only read.

Not allowed: deleting a task record (cancel it and move it to `completed/`), creating a task for
work finished in the same turn, giving a task a second owner, writing a `/memory/` path into a
repository store, or committing (the conductor commits; in a repository, by that repository's Git
rules, CONTRACT §16.3).

## Required inputs

- The owner profile `/memory/OWNER.md` with `owner_short_name`: it is the brain's **author
  name** (lower case, every run of other characters one hyphen). Without it every write refuses.
- For a new task: an outcome or next action, the one owner, and the projects it touches.

## Procedures

### 1. Capture

1. Work that is implied and will not be finished this turn becomes a task; work finished now
   does not.
2. Create it with one command:

   ```powershell
   python shared/skills/tasks/scripts/tasks.py new --title "<the outcome, in the owner's words>" `
       --status ready --priority high --project /memory/projects/<node> [--project ...] [--private] `
       [--due YYYY-MM-DD] [--next-review YYYY-MM-DD --waiting-on "<who or what>"] `
       [--schedule "<app> | <job> | <cadence>"] [--outcome "..."] [--next-action "..."]
   ```

   - The identifier is `TASK-<author>-YYYY-NNNN`, the next number in this author's one sequence
     across every store and the claims folder `/memory/tasks/.claims/` (claimed atomically). A
     legacy `TASK-YYYY-NNNN` keeps its form; this brain's legacy numbers count toward its
     sequence, so a short number never means two tasks.
   - The record goes into `store_for(first project)`: `inbox/` for `--status inbox` (the
     default), else `open/`. It carries `author`, `schedule` and `related_tasks`, and a first
     History entry naming the author.
   - **Several projects** make one task per project, each in its own store, titled
     `<title> (<node title>)`, each listing the others in `related_tasks` and each with the
     History entry `split: part of work for several projects (...)`.
   - **A repository record** names `<repository>:brain` first; `/memory/` references go to the
     companion file; a `/memory/` path in the title, outcome or next action is refused. A public
     repository, or one whose pointer has no `repo_visibility`, is named in the output. The
     checkout must be on its store branch and not behind (procedure 6).
   - `--private` on a pointer puts the task in the pointer node's own `tasks/`.
   - Each store's `STATE.md` is regenerated and the board that shows the task refreshed.
3. **Timestamps** are in the owner's timezone (`timezone` in `/memory/OWNER.md`) when Python has
   a zone database for it (`python -m pip install tzdata` on Windows); otherwise the machine's
   zone, said in the output. `--now` overrides the stamp.
4. **Git Bash on Windows** rewrites `/memory/...` into a Windows path; put `MSYS_NO_PATHCONV=1` in
   front of the command there. `new` refuses such a value and names the fix.
5. Set `due` only for a real deadline. Waiting or scheduled work gets `--next-review`, and
   waiting work names what it waits on in `--waiting-on`.

### 2. Process the inbox

For each inbox record: give it an outcome, one owner and project references, then set a status
(`do-now`, `edit --set status=...` within its folder); or complete it now; or cancel it. Nothing
stays in `inbox/` across a review without a reason in its body.

### 3. Review

```powershell
python shared/skills/tasks/scripts/tasks.py review [--all]
```

Every reachable store, once each: blocked tasks, inbox items, tasks past `due`, tasks whose
`next_review` has come, tasks due within the horizon (`--horizon N`, default 7), conflicted or
unreadable records, earliest first, each with its store. In a repository store only tasks whose
`owner` is this brain are listed unless `--all`; every task in memory is this brain's. Stores
that could not be read are named under the table. Act on each row as before: check the awaited
party, tell the owner about deadlines, name what would unblock, process the inbox. Report a short
table; do not paste the full output when nothing changed.

### 4. Update and close

Every change goes through one writer (`task_history.apply_change`): the fields, `updated` and
one History entry `- <timestamp> – <author>: <what changed>` with the same timestamp.

```powershell
python shared/skills/tasks/scripts/tasks.py done TASK-... [--note "..."]
python shared/skills/tasks/scripts/tasks.py do-now TASK-... [--note "..."]
python shared/skills/tasks/scripts/tasks.py note TASK-... --note "..." [--run <job> | --private]
python shared/skills/tasks/scripts/tasks.py edit TASK-... --set key=value [--set ...] --note "<why>"
python shared/skills/tasks/scripts/tasks.py claim TASK-... --by "SESSION NAME" [--team LABEL]
python shared/skills/tasks/scripts/tasks.py release TASK-... [--note "..."]
```

- `done`: status `completed`, a claim cleared, the record moved to its store's `completed/`.
- `do-now`: priority `high`, status `ready` unless `in_progress`; an inbox task moves to `open/`.
- `note`: the note verbatim. `--run <job>` records a scheduled run as `run of `<job>`: <outcome>`
  and warns when the record's `schedule` names another job (P11). `--private` appends to the
  companion file and leaves a repository record untouched.
- `edit`: `owner`, `priority`, `due`, `next_review`, `waiting_on`, `schedule`, `team`,
  `related_tasks`, `depends_on`, `skill_refs`, and `status` within the record's folder; the
  entry lists each `key: old -> new` with the reason. `id`, `author`, `created` and
  `project_refs` are refused (a change of project is a migration).
- On completion, update the state of each referenced node when reality changed. A task that
  gains several dependent actions, contributors or real risks becomes a project (CONTRACT §9.4)
  and moves into the new node's `tasks/`.
- The owner board applies the owner's saved actions through the same functions (`complete`,
  `do_now`, `add_note`), attributed to this brain. Screenshots go to `<store>/img/`.

### 5. Check and STATE.md

```powershell
python shared/skills/tasks/scripts/tasks.py check [--store LABEL]
python shared/skills/tasks/scripts/tasks.py state [--store LABEL]
python shared/skills/repository-preflight/scripts/preflight.py
```

`check` fails on: missing required fields or `author`, a status its folder does not hold, a bad
identifier, file name, date or `schedule`, an identifier used twice across stores, a first
project reference that does not name the store's node (in `/memory/tasks/`, any reference to a
node), references to several nodes outside `completed/`, a `/memory/` path in a repository store,
a conflict marker, an `updated` later than the newest attributed History entry, and a `STATE.md`
that differs from the generated one. It warns on waiting without `waiting_on`, no priority,
claims that do not fit the status, and stores it could not read. `state` regenerates `STATE.md`;
a Git conflict in `STATE.md` is resolved by running it.

### 6. Repository stores and conflicts

Before writing a repository store the script checks the checkout is on the store branch, runs
`git fetch origin <branch>`, and refuses when the checkout is behind, the fetch failed, or a path
in `brain/tasks/` is unmerged, naming the command that fixes it. `--offline` skips the fetch and
is passed only after the owner agrees (`SMART-RULE-0034`). Every store refuses a record with a
conflict marker: resolve it by hand, keeping the History entries of both sides in time order,
add an entry naming the resolver, then `tasks.py state`.

### 7. Migration

`tasks.py migrate` moves existing records into node and repository stores (the plan of
`PROPOSAL-shared-project-tasks-in-the-repository`). Each dry run writes
`/temp/migration/<kind>-<target>.md` for the owner and `.json` with a fingerprint; the owner's
answers are recorded with `--decide FILE --all move --private 3,9 --hold 12 --private-lines
15:2,4`; a move takes `--list FILE` and refuses a stale list or an undecided item.

| Command | Does |
|---|---|
| `migrate --split --dry-run`, then `--list FILE` | open tasks naming several nodes become one part per node |
| `migrate --node NODE [--dry-run]` | the tasks of a memory node into its `tasks/` |
| `migrate --owner-store [--dry-run]` | `author` and an attributed entry on tasks with no project |
| `migrate --repo REPOSITORY --dry-run`, then `--list FILE` | move, private (pointer node) or hold; private lines and `/memory/` references to the companion file |
| `migrate --reverse LEDGER` | a node or repository move back, from `/memory/tasks/migrations/` |

Each move keeps identifier and file name, adds `author`, an attributed entry and regenerates both
`STATE.md` files. A split is not joined again.

## Scripts or commands

| Command | Role |
|---|---|
| `tasks.py review [--today] [--horizon N] [--all]` | What needs attention, across every store |
| `tasks.py check [--store LABEL]` | Record and store checks; exit code 1 on errors |
| `tasks.py state [--store LABEL]` | Regenerate `STATE.md` |
| `tasks.py next-id [--year] [--author]` | The next free number of an author |
| `tasks.py new ...` | Procedure 1 |
| `tasks.py done`, `do-now`, `note`, `edit`, `claim`, `release` | Procedure 4 |
| `tasks.py migrate ...` | Procedure 7 |
| `scheduled_review.py [--register \| --status \| --unregister] [--no-notify] [--no-jobs]` | Read-only review with no model: writes the ignored `/temp/due.md` (each repository compared with origin, the weekly learning digest when due, tasks due in every store through `tasks.py review`, skill exchange, preflight), then runs the owner's **morning jobs** (below) and reports one line per job, and shows a desktop notification when something needs attention, a failed or timed-out job included. `--register` runs it daily at 07:00 from the operating system's scheduler – Windows Task Scheduler, a launchd agent on macOS, a systemd user timer on Linux (cron without systemd) – catching up after the computer was off except under cron, always from the shared checkout named in `/memory/OWNER.md`; `--status` shows it and `--unregister` removes it. Set up per computer in `/SETUP.md` G.2. Once registered, follow-up is real under CONTRACT §14. `--no-jobs` writes the report without the jobs |

Common options: `--tasks <path>` (the owner store; default `/memory/tasks`), `--json`,
`--offline`, and on changing commands `--now` and `--no-board`. Standard library only.

Modules (each one job, `SMART-RULE-0018`): `task_records.py` (identifiers `ID_RE`, `ID_IN_TEXT`,
records, atomic writes), `task_history.py` (author name, entries, `apply_change`),
`task_stores.py`, `task_state.py`, `task_git.py`, `task_write.py` (the change pipeline),
`task_new.py`, `task_private.py` (companion file, `flags`), `task_check.py`, `task_claims.py`,
`state_table.py` (review), `task_migrate.py` and `task_migrate_lists.py`.

**Morning jobs.** Anything that should refresh once a day – a generated page, a snapshot, a
digest – is a job on the scheduled review, never a second scheduled task (`SMART-RULE-0018`).
The owner lists the jobs in `/memory/skills/tasks/config/morning-jobs.json`:

```json
{"jobs": [{"name": "example-page", "command": ["python", "library/skills/example/scripts/daily.py", "--account", "example-gmail"],
           "timeout_s": 300, "needs": "the example service reachable; until then the page keeps yesterday's state"}]}
```

`name` is the job's log file name (letters, digits, dot, dash, underscore); `command` is the
argument list, run from the brain root (a first word of `python` means the interpreter running
the review); `timeout_s` kills the job after that many seconds; `needs` is optional text shown
with the job's line when it fails, written for the person who reads the notification. After its
report the review runs the jobs in the order listed (`morning_jobs.py`), captures each one's
output to `/temp/morning/<name>.log`, and adds a `## Morning jobs` section to `due.md` with one
line per job: whether it ran, its exit code, its seconds and the last line it printed. A job that
fails, times out or cannot start is named in the notification and never stops the review or the
jobs after it. A missing or invalid config means no jobs and one line in `due.md` that says so.
The jobs' timeouts together stay under the scheduler's limit on Windows (`EXECUTION_LIMIT_MINUTES`,
30 minutes; after changing it run `--register` again).

Tests: `python -m unittest discover -s shared/skills/tasks/scripts/tests -v` (fictional brains
`sam` and `bob`; the Git tests need `git`).

## Outputs

Task records and generated `STATE.md` files in every store; companion files in
`/memory/tasks/private/`; migration lists in the ignored `/temp/migration/` and ledgers in
`/memory/tasks/migrations/`; review tables in the reply; through the owner-board script, the
regenerated board pages.

## Permissions

Writes only inside task stores, `/memory/tasks/private/` and `/memory/tasks/migrations/`, the
ignored `/temp/migration/`, `/temp/due.md` and `/temp/morning/`, the state of nodes a task
references, and (through the owner-board script) generated board pages. Reads Git state and
fetches a repository's store branch; never commits, pushes or uses a credential of its own.
Checking an awaited external party uses that system's skill and its permissions; a write there
still needs the target confirmed (CONTRACT §10.5).

## Failure behaviour

- No `owner_short_name` in the owner profile: every write refuses, naming the file.
- A store or task that cannot be resolved, a repository store not ready (wrong branch, behind,
  fetch failed, unmerged) or a conflicted record: nothing is written, exit 1, the reason and the
  fixing command are printed.
- A `/memory/` path bound for a repository record: refused before anything is written.
- `STATE.md` cannot be regenerated: the record stands and the output names
  `tasks.py state --store <label>`; `check` and the preflight fail until it is run.
- A move that fails after the target is written and before the source is removed leaves two
  copies; `find` and `check` name both, and the extra one is removed by hand.
- An unclear owner or outcome: keep the task in `inbox/` and ask the owner, with a suggestion.
- A review that cannot reach the awaited system: leave the status, set a near `next_review`, and
  say so.
- The board cannot be refreshed: the record stands, and the output names the command to run.

## Logging behaviour

Each task carries its own attributed History. A structural change to a store (a migration, a
renumbering, a change of rules) gets one entry in that store's `LOG.md` or the node's, and the
migration writes a ledger for every move.

## State, knowledge and task update behaviour

Each store's `STATE.md` is generated from its records on every change. Durable lessons about
running tasks go to `/memory/tasks/KNOWLEDGE.md`. Node `STATE.md` files change when a completed
task changes their reality.
