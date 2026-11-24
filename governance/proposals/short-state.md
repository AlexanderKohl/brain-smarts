---
id: PROPOSAL-short-state
title: A state file holds the position, not its history
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T17:32:22+10:00
updated: 2026-11-24T17:32:22+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /CORE-RULES.md
  - /CORE.md
  - /RULES.md
  - /shared/skills/repository-preflight/SKILL.md
---

# A state file holds the position, not its history

Read `/CONTRACT.md` first. This proposal amends `SMART-RULE-0019` and the validator's *Failure behaviour*; every rule keeps its identifier
(CONTRACT §13.2). The contract is not changed. It is one of five proposals of 24 November 2026 that came out of
measuring what a session reads before it works; each can be accepted or refused alone.

## Plain-language summary

1. **One short entry per live thread.** Under `## Handover` in a node's state file, a new checkpoint replaces the thread's previous entry instead of being added above it, and an ended thread's entry leaves the file.
2. **Nothing is lost.** What is replaced moves, unchanged, to a history file beside the state file. No bootstrap names it; an agent opens it only when it needs what happened earlier.
3. **Detail goes to the thread that needs it.** What only the continuing thread needs goes in that thread's own handover file, named by a line in its entry.
4. **A limit keeps it that way.** A state file is at most 28,000 characters, the size a host shows whole. The preflight fails on a longer one in the memory.
5. **A compaction costs less.** After a compaction the thread re-reads the two core files, not the whole contract and rule file.

## Current problem

State files grow without limit because every checkpoint is added and none is removed. Measured on 24 November 2026 in the owner's brain: one node's state file was 286,268 characters, 280,027 of them in 41 handover entries kept over five weeks; another was 159,907. A thread that starts in such a node either reads about 70,000 tokens before it works or reads the start and misses the rest. CONTRACT §4 already says a state file replaces superseded state; no rule said where the old entries go and nothing checked the size. Separately, a compaction makes the thread re-read `/CONTRACT.md` and `/RULES.md` whole – 147,322 characters – although the two core files, 52,231 characters, are generated for exactly that reader.

## Current wording and exact diff

### 1. `/RULES.md` – `SMART-RULE-0019`, the compaction bullet

Current:

> - **An automatic compaction of the conductor's context is a missed checkpoint.** The host hook
>   marks it; dispatching stays closed until the conductor has re-read `/CONTRACT.md`,
>   `/RULES.md`, `/memory/RULES.md` and the owning node's `## Handover`, written the checkpoint,
>   committed, and cleared the marker (`delegation.py checkpoint-done`). The conductor tells the
>   owner in its next reply that a compaction happened.

Proposed:

> - **An automatic compaction of the conductor's context is a missed checkpoint.** The host hook
>   marks it; dispatching stays closed until the conductor has re-read `/CORE.md`,
>   `/CORE-RULES.md`, `/memory/RULES.md`, its own entry under the owning node's `## Handover` and
>   every rule its work in flight falls under (`Applies when`), written the checkpoint, committed,
>   and cleared the marker (`delegation.py checkpoint-done`). The conductor tells the owner in its
>   next reply that a compaction happened.

Why: The two core files exist so that a session can read what always applies without the full contract and rule file. After a compaction the thread needs exactly that, its own handover entry, and the rules of the work it is in the middle of. Measured: 147,322 characters become 52,231.

### 2. `/RULES.md` – `SMART-RULE-0019`, new bullet before the handover-prompt bullet

Current:

> (nothing: this is new text)

Proposed:

> - **A state file holds the position, not its history.** Under `## Handover` each live thread has one entry, and it is short: where things stand, what is in flight, what is uncommitted and where, and the next action. A new checkpoint replaces the thread's previous entry, and the entry of a thread that has ended leaves the section; what is replaced or removed moves, unchanged, to `STATE-HISTORY.md` beside the state file (`state.py history`). Detail that only the thread continuing the work needs goes in `HANDOVER-<thread>.md` beside the state file, named by a line in the entry (`state.py detail`). No bootstrap names either file: an agent reads the history only when it needs what happened earlier, and a handover file only when it continues that thread. What happened and why belongs in `LOG.md` and is not told again in the entry. A `STATE.md` is at most 28,000 characters, so that a host shows it whole: the repository preflight fails on a longer one in the memory and the mechanics, and `state.py check` names one in a project repository, whose own checks may adopt the limit.

Why: CONTRACT §4 says a state file replaces superseded state, but the checkpoint rule only ever said what to add. This bullet says where the old entry goes, where long detail goes, who reads each file, and sets the size a host shows whole as the limit.

### 3. `/RULES.md` – `SMART-RULE-0019`, the handover-prompt bullet (only the changed part is shown)

Current:

> – lives under `## Handover` in the owning node's `STATE.md` (and, for work spanning nodes,

Proposed:

> – lives in the thread's entry under `## Handover` in the owning node's `STATE.md`, or in the handover file that entry names (and, for work spanning nodes,

Why: The bullet said everything a successor needs lives in the state file. With the new bullet the long detail may live in the thread's handover file, so this sentence has to allow it.

### 4. `/shared/skills/repository-preflight/SKILL.md` – *Failure behaviour*, new line after "the core is current"

Current:

> (nothing: this is new text)

Proposed:

> - **state files are short enough to be read whole (`SMART-RULE-0019`):** fail when a node's `STATE.md` in the mechanics or the memory is longer than 28,000 characters; the error names the file, its size and `scripts/state.py history`, which moves superseded handover entries to the history file beside it. A task store's generated `STATE.md` and a template are not checked. A project repository's `brain/STATE.md` is not checked here; `scripts/state.py check` names it

Why: The limit is only kept if something checks it. The statement of what the validator refuses is protected governance, so it is shown here; the code that implements it changes with it.

## Measured

- `/CORE.md` and `/CORE-RULES.md` together, read first by every writing session: 52,231 characters today, 52,231 with this proposal alone, 43,068 with all five of 24 November.

## Reason

`SMART-RULE-0003`: read only what the task needs. The position is needed by every thread in the node; its history by almost none.

## Scope and consequences

Every thread that writes a checkpoint, in every host. A successor reads the short entry and, when it continues that thread, the handover file the entry names. The history file is read on demand. `state.py` does the moving, so no agent reads a long file to tidy it.

## Risks, conflicts and migration

- **A successor misses detail that used to be in the entry.** The entry names the handover file in one line, and the handover prompt already tells the successor to read the entry.
- **History is harder to find.** It is one file beside the state file, in time order, and `LOG.md` and Git still hold it.
- **The limit blocks a commit.** Only in the memory and the mechanics, and the error names the command that fixes it. One state file in the owner's memory is still over the limit; at acceptance its two long entries move to handover files (`state.py detail`), which brings it under.
- **A project repository is not checked by the brain's preflight.** `state.py check` names its file; its own checks may adopt the limit.

## Rollback

Restore the three passages of `SMART-RULE-0019` and remove the failure line and the check. History and handover files stay valid as ordinary files.

## Planned validation

`state.py` and its seven tests are on `main` and were used on 24 November to move 268,000 characters out of four state files, with every moved character present in the history file. After acceptance: the wording by script, the check wired into the preflight with a test, the compaction hook's text, the full preflight.
