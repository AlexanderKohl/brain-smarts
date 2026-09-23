---
id: RULE-2026-0032
title: Context handoff checkpoint
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-12T13:50:00+10:00
updated: 2026-09-17T17:56:12+10:00
accepted_by: brain-owner
accepted_at: 2026-09-12T14:00:00+10:00
implemented_at: 2026-09-12T14:00:00+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
---

# Context handoff checkpoint

## Current problem

A session ends when its context runs out, not when the work reaches a natural stopping point.
Whatever the agent knew and had not yet written down is lost, and the next session restarts from
the repository alone.

Today's rules cover the *content* of durable records – `STATE.md` for what is true,
`KNOWLEDGE.md` for durable facts, `LOG.md` for events, `/tasks/` for outstanding work – and
`RULE-2026-0023` requires a Git exit check before every final response. None of them says
**when** to write a handoff, and the failure they leave open is specific: an agent that is still
mid-investigation when context expires leaves a repository that looks finished.

This session is the worked example. It established the whole GHL capture mechanism across many
turns – which token works in which frame, why a credentials flag killed every request, what the
archive index should contain – none of which is derivable from the code. Each finding was written
down only because the owner asked at the right moment.

## Current wording

None. This is a new root rule.

## Proposed wording or exact diff

Add to `/RULES.md`:

```markdown
## RULE-2026-0032 – Context handoff checkpoint

- Write a handoff checkpoint before context runs out, and prefer a **stage boundary** to a
  context threshold: the best moment is immediately after a validated, committed increment and
  **before** starting a new stage of work, because that is when the repository and the agent's
  understanding agree. Take the checkpoint at whichever comes first – the natural boundary, or
  roughly the last fifth of the context window.
- Never begin a new stage of work when the remaining context is unlikely to carry it to a
  committed, validated state. Checkpoint and say so instead.
- A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
  flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
  facts a later session could not re-derive cheaply – especially external-system behaviour
  established by experiment; `LOG.md` with what happened and why; and `/tasks/` for anything
  outstanding.
- Record **open questions with enough context to act on them**, not just their titles: what is
  unknown, what was already tried, and what would settle it.
- Record **negative findings**. What was ruled out, and the evidence that ruled it out, is as
  valuable as what worked and is never recoverable from code.
- Distinguish what is **verified** from what is **assumed or unverified**, and name where
  uncommitted work lives when it is outside this repository.
- A checkpoint must not present unfinished work as finished. Report the actual state, including
  failures, blocked steps and anything skipped.
- Finish with the Git exit check under `RULE-2026-0023`, so the handoff and the tree agree.
```

Append `0032` to the root ID list in `/RULES.md`.

## Reason

The cost of a lost session is not the tokens; it is re-deriving external behaviour by experiment.
Several facts established here took many turns and a live account to settle, and none of them
can be read off the code:

- the backend bearer token is never in browser storage, only an expired Firebase custom token is
- the shell and the automation service use **different** tokens
- a wildcard `Access-Control-Allow-Origin` cannot be paired with a credentialed request, which
  presents as `net::ERR_FAILED` and reads like an auth fault
- the workflow step graph exists only in request bodies, never in a response

The stage-boundary preference matters as much as the threshold. A checkpoint taken mid-edit
describes a repository that does not exist yet; one taken after a committed increment describes
exactly what the next session will find.

## Scope and behavioural consequences

Repository-wide, all agents. It adds an obligation near the end of a session and a restraint on
starting new work late in one. It does not change what the core files are for, and it overrides
nothing.

Consequence: sessions will sometimes stop earlier than they otherwise would, and say why. That
is the intent.

No `contract_version` change: a root rule, not contract behaviour.

## Risks and conflicts

- **Over-triggering.** An agent that checkpoints too eagerly wastes context on ceremony. Mitigated
  by preferring the stage boundary and giving a loose threshold rather than a hard percentage.
- **False precision.** An agent cannot always measure its remaining context accurately. The rule
  is written as a judgement with a preferred anchor, not an arithmetic trigger.
- Complements `RULE-2026-0023` (Git exit check) rather than competing: that rule governs every
  final response, this one governs the end of a session's useful life. No conflict with
  `RULE-2026-0018` on communication efficiency; a checkpoint is durable record-keeping, not
  narration.

## Migration

None. Applies to sessions from activation onward.

## Rollback

Remove the `RULE-2026-0032` section from `/RULES.md`, drop `0032` from the root ID list, and set
this proposal's status to `reverted`.

## Validation

Repository preflight before and after must report the same error count. Governance coverage is
satisfied by this proposal once accepted, `target_files` naming `/RULES.md`.

## Acceptance

**Question asked:** Do you accept proposal `RULE-2026-0032`, adding the context handoff
checkpoint rule to `/RULES.md` with exactly the wording set out above?

**Accepted by the owner, 2026-09-12T14:00:00+10:00**, in the exact words "I accept".

## Implementation record

Implemented 2026-09-12T14:00:00+10:00. `RULE-2026-0032` added to `/RULES.md` with the accepted
wording unchanged, placed after `RULE-2026-0030` and before the contract-restatement list.
`0032` appended to the root ID list; `accepted_proposal` now reads `RULE-2026-0032`.
`contract_version` unchanged at 0.9.0 – a root rule, not contract behaviour.

**Validation:** repository preflight reports **11 errors**, matching the documented pre-existing
baseline. No new error introduced.

## Amendment A1 (2026-09-15T14:45:00+10:00): a continuation prompt for the next thread

**Status of this amendment: accepted and implemented (2026-09-15T15:00:00+10:00).** Owner request of 2026-09-15: "when you as a conductor
are getting close to the token limit for this session (or at any other time that might be
relevant for efficient processing) prepare the status documents and create a prompt that I can
use to start a new thread that continues where you left off." A small additive change to a
live rule keeps its ID (CONTRACT §13.2).

### Exact diff

Add to `/RULES.md` under `## RULE-2026-0032 – Context handoff checkpoint`, as a new bullet
before the final "Finish with the Git exit check" bullet:

```markdown
- A checkpoint ends with a **continuation prompt** the owner can paste into a new thread. It
  names the bootstrap line to read first, the active node and task ids, the exact next
  action, the decisions still with the owner, and every piece of work in flight with where it
  is recorded: for each delegation run its id and folder, and for each worker its packet,
  what it is doing, its branch or worktree, and whether its result file is still pending,
  with the reminder that a worker's completion notice reaches only the thread that launched
  it, so the new thread must read the result files itself; for branches and builds, the
  commit and the folder the owner loaded; for owner steps, what is outstanding. Write it
  under `## Continuation prompt` in the owning node's `STATE.md` as the last checkpoint
  record, after every other record is updated and before the Git exit check, and repeat it
  verbatim as the last section of the final reply. Take the checkpoint whenever the
  remaining context is unlikely to carry the next stage, and at any natural handover where a
  fresh thread would work more efficiently than a long one.
```

### Reason

`RULE-2026-0032` already says what a checkpoint records and when to take it. What it lacks is
the artefact that lets the owner restart without re-deriving the position: a prompt that names
the node, the tasks, the in-flight work and the next action, ready to paste. Long conductor
sessions with several workers and branches make that the difference between a minute and an
hour of re-orientation.

### Scope, risks, rollback, validation

Repository-wide, all agents. Risk: a prompt written from a stale view; mitigated by requiring
the same checkpoint to update `STATE.md` first, so the prompt and the tree agree. Rollback:
remove the bullet. Validation: preflight unchanged; the first continuation prompt written under
the rule is reviewed by the owner.

### Acceptance

Reworded 2026-09-15T14:55:00+10:00 at the owner's request: the prompt lists each run and worker with its state and the notice-reaches-only-the-launching-thread reminder, and is written last before the Git exit check and repeated last in the reply.

**Question to ask:** 1. Accept amendment A1 to `RULE-2026-0032` as reworded (recommended);
2. accept with wording changes; 3. reject. **Accepted by the owner, 2026-09-15T15:00:00+10:00**, in the word "accept" (option 1). Implemented the same minute: bullet added to `/RULES.md` under `RULE-2026-0032` before its final Git-exit bullet, wording unchanged; `accepted_proposal` set to `RULE-2026-0032`. Contract version unchanged at 0.9.0.

## Amendment A2 (2026-09-15T19:30:00+10:00): one pointer prompt, the details in the state files

**Status of this amendment: accepted and implemented (2026-09-15T14:06:21+10:00).** Owner direction of 2026-09-15: "we want a single prompt
for the conductor, all other details need to be accessible in the state files. The prompt should
just point the conductor to the correct files, so it does not need to search for a long time."
A small change to a live rule keeps its ID (CONTRACT §13.2). It replaces the A1 bullet.

### Exact diff

In `/RULES.md` under `## RULE-2026-0032 – Context handoff checkpoint`, replace the A1 bullet
(beginning "A checkpoint ends with a **continuation prompt**") with:

```markdown
- A checkpoint ends with **one handover prompt** for the next thread, and it is a pointer,
  not a summary: the bootstrap files to read, the owning node's `STATE.md` whose `## Handover`
  section holds the position, and the single next action. Ten lines at most; nothing in it
  that a file already says. Everything the successor needs – runs and workers with their
  packets, branches and pending results, builds and where the owner loaded them, owner steps
  outstanding, decisions still open, the reminder that a worker's completion notice reaches
  only the thread that launched it – lives under `## Handover` in the owning node's `STATE.md`
  (and, for work spanning nodes, one line per other node pointing at its own `## Handover`),
  written before the prompt and kept current at every checkpoint. Write the prompt under
  `## Handover prompt` in the same `STATE.md` and repeat it as the last section of the final
  reply. The `## Handover` of `/projects/brain-development/STATE.md` also names the **active
  conductor** (session title and the time it took over) and the other live sessions it knows
  of; a new thread that finds an active conductor asks the owner which thread continues
  before dispatching anything. Take the checkpoint whenever the remaining context is unlikely
  to carry the next stage, and at any natural handover where a fresh thread would work more
  efficiently.
```

### Reason

The A1 prompts were faithful and long, three of them, and each repeated facts the state files
already held; the next change made them wrong. The first thread started from one spent about
sixty commands re-deriving the position and then found a second conductor already at work. A pointer cannot go stale, and a `## Handover`
section is one place to keep current. The successor reads three files and starts.

### Rollback and validation

Restore the A1 bullet. Preflight unchanged. The first handover under A2 is reviewed by the
owner.

### Acceptance

**Question to ask:** 1. Accept amendment A2 to `RULE-2026-0032` as written (recommended);
2. accept with wording changes; 3. reject. **Accepted by the owner, 2026-09-15T14:06:21+10:00**, in the words "all accepted" (option 1). Implemented the same minute: the A1 bullet replaced in `/RULES.md` verbatim; `accepted_proposal` set to `RULE-2026-0032`. Contract version unchanged at 0.9.0.

## Amendment A3: accepted single-writer learning exception

Accepted by the owner at 2026-09-17T17:14:19+10:00 (acceptance recorded time), in the same exact displayed change set as RULE-2026-0043. Owner response: "Accept both as written." Earlier A3 drafts are retained in Git history and were not activated.

Current wording: the active-conductor question previously applied before dispatching anything.

Exact accepted addition, immediately before the final Git exit-check bullet in RULE-2026-0032:

```markdown
- The active-conductor question is not required for at most one bounded, read-only learning or public-research worker per thread under RULE-2026-0043, within RULE-2026-0037’s delegation budget. Workers use no credentials, take no external side effects and write only their separate result artifacts. This exception grants no product-editing, merging or canonical-integration authority.
```

Reason and scope: permit bounded background learning without an owner interruption. No product or canonical-write authority is granted to the worker. Supporting skill and single-writer state are provided by RULE-2026-0043. Risk: uncertain writer ownership leaves integration pending. Rollback removes this bullet; the original conductor question then applies. Validation compares the live bullet verbatim and runs repository preflight. All earlier amendments remain unchanged.

Implementation of the accepted publication revision completed at 2026-09-17T17:56:12+10:00. Supporting skills and state use the single designated writer; no concurrency prototype activated. Structural checks pending before commit; fresh-agent trials tracked explicitly as unrun in TASK-2026-0051.

Validation at 2026-09-17T17:57:06+10:00: repository preflight PASS, 0 errors and the four existing README warnings. Exact accepted 0043 and A3 wording verified in live RULES; other rule bodies preserved except the existing dash convention. Fresh-agent behavioural trials remain unrun under TASK-2026-0051. No prototype or 0044 activation.
