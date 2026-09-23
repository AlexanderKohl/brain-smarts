---
id: skill-delegate-work
title: Delegate Work
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/delegate-work/scripts/delegation.py
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T18:00:00+10:00
owner: brain-owner
project_refs:
  - /memory/projects/brain-development
---

# Delegate Work

Read `/CONTRACT.md` first. The behavioural rule for delegation is `RULE-2026-0037` in root
`/RULES.md`. This skill supplies the operating detail and may not
weaken that rule.

## Purpose

Let one agent (the **conductor**) hand bounded, independent pieces of work to one or more
**worker** agents that run in parallel, and get back compressed results it can route under the
contract, without copying its conversation into every worker and without any worker touching
canonical files or Git.

The design principle: share state through the brain, share work through packets, share large
outputs through artifacts, share only summaries through agent messages.

## What this skill is not

- Not a queue, scheduler or worker registry. The brain has no runtime. The host's own subagent
  facility is the dispatch mechanism; this skill standardises what is dispatched and returned.
- Not a task system. Packets and results are ephemeral instrumentation under `/temp/`. Work
  that must outlive the session is an ordinary `/memory/tasks/` record with `waiting_on` and
  `next_review` (CONTRACT section 9.1).
- Not cross-session or asynchronous. A run starts and ends inside one conductor session.

## The independence test

Delegate only when all four hold, and write the reason in one line in `--why-parallel`:

1. one clear outcome per packet
2. executable without talking to sibling workers
3. consumable by the conductor as a summary plus artifacts, not a transcript
4. parallel execution buys latency or quality that justifies the extra tokens
   (`RULE-2026-0004`)

Good candidates: independent research branches, alternative approaches, large-document
analysis split by section, codebase exploration by area, independent reviews. Keep with one
agent: tightly coupled reasoning, sequential implementation, anything needing constant shared
state.

## Allowed operations

- create a run folder and its manifest under `/temp/delegation/runs/`
- create work packets and pending result skeletons inside that run
- print the one-line dispatch prompt for a packet
- validate a worker's result record
- print a synthesis summary of a run
- close a run, recording the host and whether packets actually ran in parallel

The script writes only inside `/temp/delegation/runs/`. Workers write only their result file
and artifacts inside the run folder unless a packet explicitly widens `writes`.

## Required inputs

- repository root, discovered upward from the current directory by finding `CONTRACT.md`, or
  `--root`
- for a run: a title and the one-line reason parallel work beats sequential work
- for a packet: a title, an objective, context references as repository-root paths, and the
  four control fields with their defaults: `context_mode: isolated`, `writes: none`,
  `external: none`, `model: inherit`

## Data sources

- `/CONTRACT.md` section 1 (bootstrap tiers), 5 and 6 (routing), 9 (tasks), 10.4 and 10.5
  (external data and target confirmation)
- root `/RULES.md`: `RULE-2026-0004`, `RULE-2026-0010`, `RULE-2026-0023`, `RULE-2026-0028`,
  `RULE-2026-0032`, `RULE-2026-0034`
- the templates in `templates/`
- the host notes in `hosts/`

## Scripts or commands

```bash
cd <brain-root>   # the folder holding CONTRACT.md (brain_root in /memory/OWNER.md)

# 1. open a run (max four workers, depth one)
python shared/skills/delegate-work/scripts/delegation.py new-run \
  --title "Audit skills, tasks and transcripts" \
  --why-parallel "three read-only audits with no shared state" \
  --parent TASK-2026-0999

# 2. one packet per worker; defaults are isolated, read-only, no external access
python shared/skills/delegate-work/scripts/delegation.py new-packet \
  --run RUN-20990101-090000 --title "Audit SKILL.md sections" \
  --objective "Check every /shared/skills/*/SKILL.md for the CONTRACT section 10.2 headings." \
  --context /CONTRACT.md --context /shared/skills/README.md \
  --acceptance "one row per skill naming each missing section"

# 3. hand each packet to the host's subagent facility (see hosts/)
python shared/skills/delegate-work/scripts/delegation.py dispatch-prompt \
  --run RUN-20990101-090000 --packet W01

# 4. after the workers report
python shared/skills/delegate-work/scripts/delegation.py validate-result --run RUN-20990101-090000
python shared/skills/delegate-work/scripts/delegation.py summarise --run RUN-20990101-090000
python shared/skills/delegate-work/scripts/delegation.py close-run \
  --run RUN-20990101-090000 --status synthesised --host "Claude Code" --parallel yes

# tests
python -m unittest discover -s shared/skills/delegate-work/scripts/tests
```

The script uses only the Python standard library.

## Packet fields

| Field | Values | Meaning |
|---|---|---|
| `context_mode` | `isolated` (default), `fork` | Fresh context from the packet, or inherit the conductor's context. Fork needs `--fork-reason`. |
| `writes` | `none` (default), `worktree`, `paths` | No repository writes; writes only in an isolated worktree or branch; writes only to the listed `write_paths`. |
| `external` | `none` (default), `read`, `write` | No credentials or external systems; read-only with provenance; side effects only against `external_target`, which must be an owner-confirmed target under CONTRACT section 10.5. |
| `model` | `inherit` (default) or a name | Honoured only where the host allows a model choice. The result records what actually ran. |
| `max_tool_calls`, `max_output_words` | integers | Soft budgets the worker is told to respect. |
| `context_refs` | repository-root paths | What the worker reads. References, never copied prose. Each must exist. |
| `--fact LABEL=COMMAND` | repeatable | Runs the command at packet time and pastes its output into the packet. A packet quotes only facts the conductor verified by a command in the same session; a count typed from memory is a hint, and the packet says so. |

### Choosing a worker's model

**`inherit` is the default and stays the default**. Name a smaller model only for a packet whose objective
leaves no judgement, and decide that packet by packet, never as a standing rule for a class of
work.

A packet leaves no judgement when every decision is already made in it: the files are named,
the change is spelled out, the acceptance is a command that passes or fails, and nothing in it
asks the worker to weigh evidence, choose between two reasonable shapes, or decide whether
something could be verified. If the objective contains the words *decide*, *judge*, *check
whether*, *if you cannot verify*, or an option for the worker to choose between, it does not
qualify.

The reason for the caution is arithmetic, not taste: a worker that misreads a packet costs a
full re-run plus the conductor's merge time, which is more than the saving on the first run.
The result records what actually ran, so a packet that named one model and a worker that
reports another shows up at validation.

A read-only packet lets the worker use the scoped bootstrap tier from CONTRACT section 1. A
packet that allows writes tells the worker to complete the full bootstrap first.

## Outputs

- `RUN.md`: run manifest with the reason for parallel work and, after synthesis, what was
  routed where
- `WNN.md`: one packet per worker
- `WNN.result.md`: the worker's report with `status`, `host`, `model`, `changed_paths`,
  `validation`, `artifacts`, and the sections Summary, Conclusion, Verified, Assumed or
  unverified, Negative findings, Sources, Facts to route, Open questions, Suggested tasks
- artifacts the worker wrote inside the run folder
- the `summarise` output the conductor uses for synthesis

## Conductor obligations after the workers report

1. Run `validate-result`. Treat a failing result as a failed worker, not as data.
2. Treat every worker claim as unverified until checked against the file or system it cites
   (CONTRACT section 13.1). Spot-check at least one verified fact per worker.

   For a packet that produced a screen, the check is **against the artefact it was given**,
   not against its description: open the mockup and the built page together. A report that
   says it followed the spec is not evidence that it matches what the owner approved.
3. Route each durable outcome under CONTRACT sections 5 and 6: knowledge to the owning
   `KNOWLEDGE.md`, state to `STATE.md`, outstanding work to `/memory/tasks/`.
4. Write one `LOG.md` entry in the owning node naming the run, the host, whether the packets ran
   in parallel, which results were accepted or rejected, and where outcomes were routed.
5. Commit under `RULE-2026-0023` and `RULE-2026-0017`. Workers never commit.
6. **Update the parent task's status word, on the same pass.** A packet's parent task is named
   at `new-run --parent`. If that record still says `ready` after a packet against it has landed,
   the word is a lie and the next reader believes it. Set it to `in_progress`, write on the record
   what landed and at which version, and check the row in `/memory/tasks/STATE.md` says the same. See
   **A status word is written when work starts and never when it finishes** below.
7. Close the run with `close-run`. Delete the run folder when nothing in it is still referenced,
   or leave it; `/temp/` is gitignored and safe to delete.

## A packet that builds a screen names the artefact, never a description of it

Rationale: a page built from packets that describe the approved design in prose, instead of
naming it, is each worker's inference from sentences, and it can look nothing like the
design. The cause is in the packets, not the code.

The failure is not that the workers are careless. **A description of a screen is lossy in
a way a description of a rule is not.** *One table, labels once* is true of a dozen layouts
and the owner approved exactly one of them. Handing a worker the sentence and not the file
is handing over the lossy copy and keeping the original. When several packets build one
page that way, what ships is several people's reading of a description of a picture, and
the first person to notice is the owner.

**So, for any packet whose output is something a person looks at:**

1. **Name the artefact by path, in the packet.** The mockup, the screenshot, the page it
   must match. `/shared/skills/ui-mockup/` builds these against the product's own
   stylesheet; they live under `temp/ui-mockup/` and are gitignored, so a path in a task
   record is not a path in a packet. **The packet must carry it.**
2. **Say the artefact is the target and the prose is the commentary.** Then say what
   happens when they disagree: the thing the owner approved wins, and the worker says so
   in its report rather than silently choosing.
3. **Ask for the difference list as the deliverable.** *Open the mockup, open the built
   page, list every way they differ* - that list is the work, and it is the part a worker
   cannot produce from prose.
4. **Require the check that would have caught it.** See below.

**A page with no harness goes unseen.** When every other page has something that opens it
in a real browser and measures what it drew, the one page without it is the one whose
defects survive. So a packet that builds or changes a screen **states which harness will
measure it**, and when none exists, writing it is part of the packet rather than a follow-up.
A page with no harness is a page whose only check is the owner.

## Permissions

- read access to the repository
- write access only under `/temp/delegation/runs/`
- no Git operations, no credentials, no external systems

## What a packet must ask for, when a fix has already failed once

Rationale: when fixes ship against a symptom before anybody has looked at the evidence, each
fix is one more theory, and the symptom can survive all of them.

- **Forbid the third theory.** When a symptom has survived a fix, the packet says so and requires
  **evidence before a change**: what the code saw, in the words it will print, in the place the owner
  can read it. A worker that refutes the conductor's diagnosis and stops has finished the job; say
  that in the packet, so refuting is not read as failing.
- **Require the cost, measured.** *A walk that cannot state its own cost is not finished.* Ask for
  the number on the user's own data or capture - latency in milliseconds, items processed, frame
  cost under load - and the packet says which capture. A design settled on a guess about scale is
  settled twice.
- **Name what the packet does not cover.** The worker reports what the change still cannot do, and
  whether anybody has seen it work on the real system. *Nobody has seen this on a real user's data* is a
  sentence a report should be able to contain.
- **Say what a report must contain that nobody hopes for.** The number that did not move, the
  expectation that did not hold, the defect the worker introduced and fixed on the way. A report of
  successes only is a report that has to be read twice.

## Failure behaviour

- `new-packet` refuses a fifth packet, a fork without a reason, a `paths` write mode without
  paths, an external write without a confirmed target, and a context reference that does not
  exist.
- `validate-result` fails on a pending status, a missing section, a missing `host` or `model`,
  changed paths under a `writes: none` packet, changed paths without validation results, a
  changed path that does not exist under a `writes: paths` packet, an artifact written as a path that does not exist (a branch,
  a commit or a URL is free text and is not checked), a `blocked` result with no question, and
  any secret-shaped content.
- A `writes: worktree` packet almost always works in **another repository**, so its changed
  paths belong to that repository and cannot be resolved here. The validator says so as a
  warning rather than an error: reporting real files as missing teaches the conductor to read
  past the validator, which is worse than the noise it was trying to prevent. A
  worker may list either form; absolute paths resolve and read plainly in a report.
- A worker that needs an owner decision stops with `status: blocked` and the question. The
  conductor asks the owner; workers never guess at targets, tenants or permissions
  (`RULE-2026-0034`).
- On a host with no parallel subagent facility, the conductor runs packets in sequence in its
  own session and records `parallel: no`. It never claims parallel execution that did not happen.

## Logging behaviour

The script does not edit activity logs. The conductor records the run in the owning node's
`LOG.md` as described above. Worker transcripts are captured by the host and, where the
session-log listener covers them, by `/shared/skills/ai-session-log/`.

## State, knowledge and task update behaviour

The script updates nothing outside the run folder. The conductor routes outcomes. A worker's
`Suggested tasks` become `/memory/tasks/` records only when the conductor decides they represent
outstanding work under CONTRACT section 9.3.

### A status word is written when work starts and never when it finishes

Rationale: records go stale in bulk, and **one stale word can make a second thread report a
track as never picked up when nearly all of its increments have shipped**. What an audit of
stale records typically finds:

- a task says `ready` after many increments have landed across several versions
- a task says `ready` after its first items have shipped
- a task says `ready` with increments landed and a packet in flight
- open tasks exist that are in no index, so nobody reading the index can see them

These are not four mistakes; they are one habit. **Dispatching is vivid and closing is not**, so
the record gets written at the moment attention is highest and never again. A rule saying
*remember to update it* would be the same habit with a sentence attached.

**So it is checked mechanically, not remembered.** A `reconcile.py` beside a board's generator
(see `/shared/skills/owner-board/`) reads every board track's parent task and says so when a track has landed work or a card in
flight while its record still says `ready`, or when a track's task is missing from the index. It
runs on every board regeneration, so the conductor cannot choose not to run it.

**The general form, for any node:** where work is tracked in two places – a task record and
whatever shows progress – something must compare them on a schedule nobody sets. It is the
familiar shape of *two lists that must agree with nothing keeping them in step*, one of the most
reliable defects any codebase produces.

### What the audit also fixed, and what it says about handovers

A design thread that writes records – a specification, a task record – without contract front
matter leaves them failing `preflight.py`, and the same break tends to recur on other records
it touches. **A thread that writes records and never runs the
validator hands its errors to whoever runs it next.** Run `preflight.py --write-manifest` before
handing work over, not only before committing.

## Lessons from trial runs

- **Git Bash rewrites leading-slash arguments** (`/CONTRACT.md` becomes a path under the Git
  installation). Prefix the command with `MSYS_NO_PATHCONV=1` or run the script from
  PowerShell.
- **Do not put counts in acceptance criteria unless verified at packet time.** An expected
  count typed from memory is often stale. Workers can handle it, but a stale number invites a
  worker to force the data to fit.
- **Acceptance criteria drive result size.** A packet that demands quoted evidence for every
  finding will exceed an 800-word soft budget. Raise `--max-output-words` when the acceptance
  criteria require quotation, or ask for an artifact file plus a short result.
- **Workers cannot see the model name reliably.** Record the host's completion report.
- **Measure from the host's completion report** where the session-log listener does not yet
  attribute subagent turns for that host (`/shared/skills/ai-session-log/` does for Claude
  Code).

## Lessons for the conductor role

- **Facts are computed, not remembered.** Use `--fact` for every count or identifier the
  objective relies on. A stale number in a packet is the conductor's error, not the worker's.
- **The word budget is advice.** `validate-result` warns when a body exceeds it and never
  fails on it; acceptance criteria that demand evidence per item decide the size.
- **Prefer a script file over inline shell arguments.** Long objectives with apostrophes and
  leading-slash paths break Git Bash on Windows; a small Python script that calls
  `delegation.main([...])` does not.
- **Write product files with their own line endings.** A patch that rewrites a whole file
  with the platform default produces a merge conflict on every line for the next session.
  Open with `newline=''` or patch line by line.
- **Resolve a `package.json` conflict by merging the `scripts` object, never by taking a
  side.** The conflict is almost always the one `version` line, and every way of taking a
  whole side - `--ours`, `--theirs`, a regex that keeps one half - takes the whole file with
  it. **Taking a side silently deletes a worker's script entry**, and it is found only when
  someone runs a command that no longer exists. After
  resolving, assert that every script every parent of the merge had is still present.
- **Merge a worker branch into the trunk with `--no-ff`, always.** A worker merges the
  trunk before pushing, so its tip is often a merge commit; merging that fast-forward makes
  **the branch's line the trunk's first-parent line**, and every version the trunk carried
  between the branch point and now falls off it. That silently rewrites what the trunk is
  recorded as having shipped: real builds become versions the trunk never carried, and a
  guard that checks cited versions then forces a worker to reword comments that were
  **true**. A check reading a corrupted
  history is worse than no check, because it argues. `--no-ff` costs one commit and keeps
  the trunk's line the trunk's.
- **Name the build a live run depends on.** A worker cannot see what the owner loaded; the
  packet for a live run states the `dist` path and commit the owner is to load.
- **Never remove a worktree that holds a junction with `--force`.** A junction to the main checkout's `node_modules` is followed by the removal and empties the main checkout (recoverable only by reinstalling, for example with `npm ci`). Delete the junction first, then remove the worktree; better, have workers use `npm ci` in their worktree instead of a junction.
- **Code can go to a worker in an isolated worktree** (`writes: worktree`). The conductor
  stays responsive when it dispatches and merges rather than implements; keep its own turns
  short.

## Research and design threads: clarify, then hand back

A thread that researches or designs something is **not** a
conductor and does not dispatch. Its job ends with a **decided** specification, and it hands
that to the conductor. Whether it then also builds the thing is a separate instruction the
owner gives; what it must never do is hand over an undecided one.

**Every open decision is settled with the owner before the handover, not after it.** A
conductor that has to stop and ask has either already dispatched work against a guess, or is
sitting idle waiting on an answer the design thread could have had an hour earlier. Worse, the
owner ends up answering the same question twice, to two agents, from two framings, which is how
a decision drifts without anybody noticing.

**Asking.** Put the decisions as one numbered set, each with a concrete recommendation, so the
owner can answer with numbers (`RULE-2026-0018`). Ask them all at once, at the end, rather than
one at a time through the design: a decision made early against a half-drawn design is often
re-opened by the finished one.

**Recording.** The answers go in the canonical specification, in its own decisions section,
with the date and the word *accepted*. The proposal or artifact is updated to match, so the
drawing and the spec cannot disagree. The conversation is not the record.

**Say what the answers changed.** Some answers confirm the proposal and some replace it. The
conductor will read the spec's own tables and prose, which may still describe the superseded
plan unless it is corrected in the same pass - so correct it, and then say out loud, in the
handover, which decisions changed the design rather than confirming it. This is the part that
is easiest to skip and most expensive to miss.

**A decision the owner deliberately leaves open is flagged, never implicit.** Name it in the
handover, say who decides it and when it has to be decided by. "Raise it if it reads wrong once
built" is a legitimate answer; silence is not.

**The task record is the machine-readable signal**, and a conductor should be able to tell from
`/memory/tasks/` alone whether something is dispatchable:

| The design thread is | `status` | `waiting_on` |
| --- | --- | --- |
| still designing | `in_progress` | `null` |
| waiting on the owner | `waiting` | the decisions, named, with the section that holds them |
| done, and it is the conductor's | `ready` | `null` |

**The handover prompt** names the files and not their contents (the same rule as *Handover
between conductor threads* below): the bootstrap, the specification, the task, the proposal
link, the decided answers in one block so they are not re-asked, the order of increments, the
constraints specific to this work, and what done looks like. It also carries whatever
housekeeping the next thread would otherwise discover the hard way - stale worktrees, merged
branches, the current version.

## Handover between conductor threads

The prompt is a pointer; the files are the substance. Ten minutes, not an hour.

**Leaving a thread (the conductor):**

1. Read the clock with `date`; every stamp comes from it.
2. Update the owning node's `STATE.md` under `## Handover`: active conductor and other live
   sessions, method in one line, what is in flight (runs and packets, pending result files,
   branches, builds and the folder the owner loaded), owner steps outstanding, open
   decisions, and one line per other node pointing at its own `## Handover`.
3. Regenerate `/memory/tasks/STATE.md` if a task changed; run preflight; commit; push.
4. Write the three-line prompt under `## Handover prompt` in
   `/memory/projects/brain-development/STATE.md` and repeat it last in the reply. It names files and
   the next action, nothing else.

**Arriving in a thread (the successor):**

1. Read `/CONTRACT.md`, `/RULES.md`, `/ONBOARDING_AGENT.md`, then the `## Handover` of
   `/memory/projects/brain-development/STATE.md` and the `## Handover` sections it points to. That is
   the whole bootstrap; do not re-derive the position from logs, transcripts or git.
2. Check the live facts the Handover cannot promise: `git log -1` on the branches it names,
   `grep -l "status: open" /temp/delegation/runs/*/RUN.md`, and the session list for a running
   conductor. Ten commands at most.
3. If an active conductor is named for the work you were given, ask the owner which thread
   continues before dispatching anything. Otherwise write yourself into `## Handover` as the
   active conductor and start on the next action.

## Deferred by design

Recorded so the next reader does not re-propose them without new evidence: a durable queue with
leases and claims, a model and worker registry with cost and health, a scheduler, cost-based
routing, recursion beyond depth one, write-enabled workers outside isolated worktrees, and any
alignment with external agent-to-agent protocols. Each needs a runtime the brain does not have
or a measured trial that has not yet been run. The governing rule is `RULE-2026-0037` in
`/RULES.md`.
