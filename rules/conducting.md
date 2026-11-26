---
id: brain-rules-conducting
title: Rule pack: conducting
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-26T15:48:16+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: conducting

Generated from `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim, the rules of one
situation, so that they are read together. Each rule's canonical home stays `/RULES.md`.

Read the whole file before: before delegating work to another agent or running more than one session or worker; working cards between threads; a conductor thread starts or hands over; the owner raises another area's topic; before pushing merged code.

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0024` | Delegated parallel work | this file; `/shared/skills/delegate-work/` | before delegating work to another agent; as a conductor, before reading a source rather than a result |
| `SMART-RULE-0037` | Size parallel work to the machine and the merge | this file; the machine's hardware and session footprint in `/memory/OWNER.md` | before running more than one agent session or worker at once |
| `SMART-RULE-0043` | Work moves between threads through cards | this file; `/shared/skills/delegate-work/`; `/shared/skills/tasks/` | taking, working, releasing or handing over a card; running a scrum-master or team thread |
| `SMART-RULE-0048` | One conversation with the owner | this file; `team_sessions_max` in `/memory/OWNER.md`; `/shared/skills/product-feedback/` | a conductor thread starts or hands over, the owner raises another area's topic, before starting a team session, before pushing merged code |

## SMART-RULE-0024 – Delegated parallel work

- Delegate to another agent only work that is independent, bounded and consumable as a
  compressed result: one clear outcome, no back-and-forth with sibling workers, and a result
  the conductor can use without the worker's reasoning. Before dispatching, state in one line
  why parallel workers beat doing the work in sequence. Tightly coupled reasoning, sequential
  implementation and work that needs constant shared state stay with one agent.
- **The conductor's context is for coordination: it reads results, not sources.** A conductor
  writes packets, reads result records, routes them, reviews diffs, merges, and writes the
  shared files (state, log, tasks, indexes) and the commit. Any work that needs reading more
  than a packet and its result – a source file, a transcript, a log, a page, a tool's output –
  goes to a worker or a team thread, however small it looks: one such detour costs more context
  than ten dispatches. A conductor that reads a source says so in the run's log entry and why;
  the context size recorded on each run shows the cost.
- Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
  files rather than copying prose, and a result record the worker writes back. Packets and
  results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
  must outlive the session is an ordinary task record (CONTRACT §9) with `waiting_on` and
  `next_review`.
- A worker is an agent started with a work packet. An agent started without one – a host's
  subagent given a piece of the session's own work – is not a worker and does not take on the
  worker limits below: it does the whole job as the session would, including the state, log and
  task-list updates the work needs and the commit. A session that wants work done in parallel,
  or kept apart, uses a packet.
- Workers start isolated by default. A packet that forks the conductor's context states why.
- **A build that carries risk starts from an approved plan.** Before a worker builds anything
  that touches stored data, logins or permissions, money, or more than one module, a short plan
  is written: the data flow, what happens when each read or write fails, the tests, and the
  checks that will be run. The conductor approves the plan before the build starts. The plan is
  the result of its own packet, or written by the conductor, and the build packet names it in its
  context references; a build packet that needs a plan and names none is not dispatched. A
  worker that finds, while building, that its work reaches one of these areas and its packet
  names no approved plan stops with status `blocked`. The approved build plan of a run of more
  than four workers serves as this plan when it covers these four points for each packet.
- Workers do not commit, and do not write the files every task shares – logs, state, task lists,
  indexes, version fields, build output. A worker writes only the paths its packet names, in the
  conductor's copy and branch (`SMART-RULE-0038`), and returns findings, artifacts inside its run
  folder, and every changed path with its validation result. The conductor keeps the paths of one
  run disjoint, reviews each worker's diff before staging it, and commits and reports. A worker
  whose work cannot be kept apart – it builds code or runs tests that write outside its own
  paths, it must change a file another worker also changes, or it is one of several alternative
  attempts – works in its own worktree, branched from the conductor's branch; the conductor
  merges it back (`SMART-RULE-0014`). Unit tests that read and write only inside the worker's
  own paths (and their caches) run in the session copy (`SMART-RULE-0038`).
- Workers use no credentials and take no external side effect unless the packet names a target
  the owner confirmed for this operation under CONTRACT §10.5. The default is none. A worker
  that needs an owner decision stops with status `blocked` and the question; it does not guess.
- Budget: depth one (workers do not delegate) and at most four workers per run. A run may hold
  up to eight workers when an approved build plan splits the work first: the plan names each
  packet's write paths, no two packets share a path, and the plan fixes every interface between
  the packets (names, data shapes, identifiers), so no worker needs another's result to finish.
  The conductor approves the plan before the run opens and names it on the run. The machine
  limit of `SMART-RULE-0037` still applies, and the number is the lower of the two. A raise
  beyond eight needs another measured trial recorded under `/memory/projects/brain-development/`.
- The conductor routes each result under CONTRACT §5 and §6, treats worker claims as
  unverified until checked, writes one `LOG.md` entry per run in the owning node, and does the
  Git accounting under `SMART-RULE-0014`. Never claim parallel execution on a host that ran
  packets in sequence. Record the host and the model that actually ran each packet; never
  invent one.

## SMART-RULE-0037 – Size parallel work to the machine and the merge

- The number of agent sessions or workers run at once is worked out for each batch, never fixed: the lower of what the machine can carry and what the conductor can merge back.
- **What the machine can carry:** measure free memory before any worker starts (the baseline), keep back 20 % of it for the owner's own work (at least 300 MB), and divide the rest by the measured memory one session actually costs, taken as the drop in free memory per running session including its child processes. Allow at most one session per two logical processors, and always at least one, with a warning when even one is tight. Before starting each further session, start it only when free memory stays above the kept-back margin plus one session's cost and the system memory load is below 90 %; otherwise wait for a running one to finish. Record the measured cost with the machine's hardware in `/memory/OWNER.md` and re-measure it after each batch.
- **What the conductor can merge back:**
  - Workers that only return results (read-only research, isolated test runs) add nothing to merge, so only the machine limits them.
  - Workers that change files count against the conductor's integration budget in `SMART-RULE-0024`, which is raised only by a measured trial.
- When the owner asks for more than this allows, the agent says so before starting, with the figures and the number it would use, and proceeds only on the owner's answer.
- When the hardware or the footprint is not recorded for the computer in use, the agent reads and records it before any parallel work.

## SMART-RULE-0043 – Work moves between threads through cards

- A body of work that several threads share runs as a **scrum**: one **scrum-master thread**
  and one **team thread** per project or area. The scrum master owns the boards, the
  priorities and the owner's questions, assigns cards to teams and watches work in progress;
  it never reads code, dispatches workers or reviews work, so its context stays small for
  weeks. A team thread is a conductor under `SMART-RULE-0024` for the cards of its team: it
  pulls a card, dispatches the workers it needs, reviews, merges to its project's branch and
  closes the card.
- A **card** is a task record in a task store (CONTRACT §9) with a `team`. A team thread takes a
  card by setting `claimed_by` to its session name, `claimed_at` from the clock and
  `status: in_progress`, and committing that record on its own, in the repository that holds it
  (`tasks.py claim`); a conflict on that commit means another thread took it first, and the
  loser moves on. A card leaving `in_progress` loses its claim (`tasks.py release`, or
  completion). The task record stays the only record: who holds a card lives nowhere else.
- **Work in progress is limited.** A team holds at most `tasks.wip_limit` cards in
  `in_progress` (two, until a measured trial says otherwise), and the scrum master assigns no
  card past it. A card that waits on another team's card says so in `waiting_on`; finishing
  the first clears the second, and the board shows it.
- A team thread acts only on a turn. It is woken by a message from the scrum master when a
  card of its team becomes ready, or by its own slow check of the board (one short turn every
  twenty to thirty minutes), never faster. A thread that finds nothing ready writes nothing.
- A team thread hands over under `SMART-RULE-0019` when its own context fills. Its cards are
  its handover: the successor claims them again under its own session name. The `## Handover`
  of `/memory/projects/brain-development/STATE.md` names the scrum master and the live team
  threads with their teams.
- Start with two teams. The trial – cards closed per day, context sizes at open and close,
  merge conflicts, owner interruptions – and its decision are recorded under
  `/memory/projects/brain-development/` before a third team is added.

## SMART-RULE-0048 – One conversation with the owner

- The owner's work is divided into areas, each with its own lifecycle, node and data: for example
  strategy and finance, a product, and operations in external systems. `/memory/OWNER.md` names
  the areas in `conductor_areas`; without that field there is one area. Each area has one
  conductor thread, the owner's one conversation for that area: it answers the owner, puts every
  question of its area to the owner, and gets work done through workers (`SMART-RULE-0024`). At
  most one live conductor per area, and no more areas than `conductor_areas` names. The
  `## Handover` of `/memory/projects/brain-development/STATE.md` names every live conductor with
  its area and the time it took over; a new thread that finds a live conductor for its area asks
  the owner which thread continues before dispatching anything. A fact one area learns that
  another needs is written to the brain's files (the node that owns it), never passed from one
  thread's context to another.
- Within an area, for a task that will take more than a day and passes several of the owner's
  gates, the conductor may start a team session: a separate agent session that conducts that one
  body of work with its own workers (a team thread, `SMART-RULE-0043`). At most `team_sessions_max`
  in `/memory/OWNER.md` run at once across all areas, two when it is not set. A team session never
  puts a question to the owner and never starts another session; it sends its questions and
  results to its area's conductor, who asks the owner in the conversation. The conductor archives
  a team session the day it hands back. No other session is started unless the owner asks for one
  in words, or a rule names it.
- The conductor routes; the owner does not have to. When the owner raises a topic that belongs to
  another area, the conductor says so in its first reply, names the area, and offers to start or
  hand to that area's session (the host's offer, where it has one) before doing anything beyond
  answering a quick question. It never carries another area's work on because the owner happened
  to raise it here, and it never leaves the owner to work out which lane a topic belongs to.
- Every packet that changes code carries the pre-merge checklist. The conductor runs it again on
  the merged tree before every push: the full unit suite, the code map check, the build, the
  version and release-note checks, unique migration names, and a safe fallback when a read fails.
  A push goes only after the checks pass, and CI results are read after each push, before the next
  merge.
- When the conductor's context reaches its checkpoint (`SMART-RULE-0019`), it hands over to one
  successor conductor and stops. The successor is the only thread the owner talks to.
