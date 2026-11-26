---
id: PROPOSAL-core-names
title: The generated core files are named after their sources
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-26T15:55:00+10:00
updated: 2026-11-26T15:55:00+10:00
previous_contract_version: 3.7.0
new_contract_version: 3.8.0
target_files:
  - /AGENTS.md
  - /BOOTSTRAP.md
  - /CLAUDE.md
  - /CONTRACT.md
  - /CORE-RULES.md
  - /CORE.md
  - /RULES.md
  - /rules/node-files.md
  - /shared/skills/delegate-work/SKILL.md
  - /shared/skills/repository-preflight/SKILL.md
---

# The generated core files are named after their sources

Read `/CONTRACT.md` first. The two files this proposal creates, `/CONTRACT-CORE.md` and `/RULES-CORE.md`, are targets too;
they are not listed in `target_files` because they do not exist until it is applied. This proposal renames the two
generated core files in every file that names them, and brings three summaries of "read by situation" up to the rule
packs. No rule and no contract section changes its meaning or its identifier (CONTRACT §13.2). The contract takes the
next minor version at acceptance: 3.8.0 (CONTRACT §13.3).

## Plain-language summary

The brain starts from two files that people write: `/CONTRACT.md` and `/RULES.md`. What a thread reads first is two
short files generated from them, called `/CORE.md` and `/CORE-RULES.md`. Those names do not say that one is cut from
the contract and the other from the rules, so "core" reads like a second set of files beside the contract.

After this change the two generated files are `/CONTRACT-CORE.md` and `/RULES-CORE.md`. Their content is the same,
word for word. The old names stay for one contract version as two short files that say where to read instead, so a
pointer file written before the rename still leads to the right place. Three sentences that still tell a thread to
read "a section or a rule" by situation now name the rule pack, as CONTRACT §1 already does.

## Current problem

- The owner, 26 November 2026: the core files look like a new naming convention beside the contract and the rules,
  and the names should be consistent everywhere.
- CONTRACT §14 item 4, `/BOOTSTRAP.md` item 4 and `/CLAUDE.md` still describe reading by situation as it was before
  rule packs held contract sections (`PROPOSAL-contract-in-packs`, accepted the same day).

## Current wording and exact diff

### 1. The rename

In every file listed here, each `CORE-RULES.md` becomes `RULES-CORE.md` and each `CORE.md` becomes
`CONTRACT-CORE.md`, including where the name is a link's target. Nothing else in those lines changes, except the
three sentences under 2. The number in brackets is how many names the line holds.

| File | Line | Names | The line begins |
|---|---|---|---|
| `/CONTRACT.md` | 28 | 4 | §1, **Full bootstrap** (required before the first creation, change or deletion ... |
| `/CONTRACT.md` | 917 | 2 | §14: 1. choose the bootstrap tier; for full bootstrap read `/CORE.md` and `/CORE-RULES.md` (section 1) |
| `/CONTRACT.md` | 952 | 2 | §15: `/CORE.md`, `/CORE-RULES.md` and the rule packs under `/rules/` are current with this contract ... |
| `/RULES.md` | 76 | 1 | `Applies when` says when an agent reads a rule's full text: `always` rules are in `/CORE-RULES.md`, |
| `/RULES.md` | 77 | 1 | which every writing session reads first with `/CORE.md` (CONTRACT §1); any other rule is read before |
| `/RULES.md` | 87 | 1 | in more than one pack; `/CORE-RULES.md` lists a rule's own row only when its text is in neither the |
| `/RULES.md` | 89 | 1 | `/CORE-RULES.md` names the pack. |
| `/RULES.md` | 286 | 1 | `SMART-RULE-0019`: marks it; dispatching stays closed until the conductor has re-read `/CORE.md`, |
| `/RULES.md` | 287 | 1 | `SMART-RULE-0019`: `/CORE-RULES.md`, `/memory/RULES.md`, its own entry under the owning node's ... |
| `/BOOTSTRAP.md` | 20 | 3 | 4. Full bootstrap: read `/CORE.md` and `/CORE-RULES.md`, then the owner profile ... |
| `/AGENTS.md` | 15 | 4 | **Start here:** ... reads [`/CORE.md`](./CORE.md) and [`/CORE-RULES.md`](./CORE-RULES.md), with the host's ... |
| `/AGENTS.md` | 17 | 2 | The canonical rules are ... `/CORE.md` and `/CORE-RULES.md` are generated from them. |
| `/CLAUDE.md` | 19 | 4 | ... read [`/CORE.md`](CORE.md) and [`/CORE-RULES.md`](CORE-RULES.md)**, generated from the contract ... |
| `/CLAUDE.md` | 27 | 2 | 1. Read `/CORE.md`, then `/CORE-RULES.md`, each with the Read tool |
| `/shared/skills/repository-preflight/SKILL.md` | 371 | 2 | *Failure behaviour*, **the core is current**: ... when `/CORE.md`, `/CORE-RULES.md` or a rule pack ... |
| `/shared/skills/delegate-work/SKILL.md` | 590 | 2 | 1. Read `/CORE.md`, `/CORE-RULES.md`, `/memory/OWNER.md`, `/memory/RULES.md`, then the `## Handover` of |

The same two names change in the validator's code and tests: `core.py` (which writes the files), `hooks.py` (the text
a thread is given after a compaction, and the list of protected files, which gains the new names and keeps the old
while their pointers exist), `session.py` (the line printed at the start of a session) and three test files.

### 2. Three sentences brought up to the rule packs

CONTRACT §14, item 4, current:

> 4. read inherited rules (`/memory/RULES.md`, then node rules; a section of this contract or a `/RULES.md` rule when its `Applies when` fits the work) and active state

Proposed:

> 4. read inherited rules (`/memory/RULES.md`, then node rules; the rule pack whose `Applies when` fits the work, or a section of this contract or a `/RULES.md` rule that no pack holds) and active state

`/BOOTSTRAP.md`, item 4, the second sentence, current (with the new file name):

> Read any other contract section or rule in full when its `Applies when` in `/RULES-CORE.md` fits the work.

Proposed:

> Read the rule pack whose `Applies when` in `/RULES-CORE.md` fits the work, in full, and any contract section or rule that no pack holds.

`/CLAUDE.md`, the end of the sentence that names the two files, current:

> generated from the contract and `/RULES.md`, and any section or rule whose `Applies when` fits the work.

Proposed:

> generated from the contract and `/RULES.md`, and the rule pack whose `Applies when` fits the work.

### 3. The generated files

`core.py build` writes `/CONTRACT-CORE.md` and `/RULES-CORE.md` with the content `/CORE.md` and `/CORE-RULES.md` have
today. Their titles become *Contract core* and *Rules core* (they were *Brain Core* and *Brain Core: Rules*), and
their identifiers `contract-core` and `rules-core`.

`/CORE.md` and `/CORE-RULES.md` stay for one contract version, each as a generated pointer of this form:

> # Moved to `/CONTRACT-CORE.md`
>
> Read `/CONTRACT-CORE.md` instead, with the file-reading tool. This file was renamed in contract 3.8.0, so that its
> name says which file it is generated from. This pointer is for pointer files written before the rename,
> and goes with the next contract version.

The two pointers are deleted by the next accepted change that raises the contract version, as part of it and without
a proposal of their own.

## Measured

Applied on a copy on 26 November 2026 and rebuilt: `/CONTRACT-CORE.md` 19,013 characters and `/RULES-CORE.md` 24,916,
against 18,943 and 24,927 under the old names; each pointer about 630. The rule packs change only where
`SMART-RULE-0019` names the two files. The generator's and the compaction hook's tests pass (41), and the preflight
reports nothing but the protected files waiting for this acceptance.

## Reason

A name means one thing, everywhere (`SMART-RULE-0033`), and should say what the thing is. The two files are the core
of the contract and the core of the rules; their names now say so, and the contract stays visibly the starting point.

## Scope and consequences

- Every agent in every host reads `/CONTRACT-CORE.md` and `/RULES-CORE.md` first where it read `/CORE.md` and
  `/CORE-RULES.md`. What it reads there is unchanged.
- The words "the core" and "the two core files" keep their meaning.

## Risks, conflicts and migration

- **A host's user-level pointer file** (outside the repositories, one per computer and host) still names the old
  files until it is rewritten. The pointers at the old names keep it working for one contract version. On
  acceptance the agent rewrites the owner's own on this computer; on another computer, and in another person's
  brain, the first session after the merge does the same when it meets a pointer at an old name.
- **Handover prompts already written into state files** name the old files. They lead to the pointers; each thread
  writes the new names at its next checkpoint. Historical records are not rewritten (CONTRACT §13.2).
- **A project that checks what an agent read** by the old file names (an evaluation harness, for example) must learn
  the new names; a task records it at acceptance.
- **Another brain that follows the mechanics** receives the rename with its next merge; its preflight builds the new
  files and the pointers.

## Rollback

Revert the commits that apply this proposal in the mechanics repository and run `core.py build`. The contract returns
to 3.7.0. A user-level pointer file already rewritten is rewritten back, or left: the old names exist again.

## Planned validation

- The validator's tests, with the cases already adjusted in the rehearsal: the generator writes four files (the two
  parts and the two pointers), the preflight fails when any of them is out of date, and the text after a compaction
  names the new files.
- `core.py check` and the full preflight on the result; every generated file under 28,000 characters.
- After the pointers are deleted with the next contract version: a search of the three brain repositories and of the
  host's user-level pointer file for the old names, outside historical records, finds none.
