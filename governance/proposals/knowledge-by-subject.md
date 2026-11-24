---
id: PROPOSAL-knowledge-by-subject
title: Knowledge by subject: a node's knowledge file becomes an index when it outgrows one file
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T17:32:22+10:00
updated: 2026-11-24T17:32:22+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.4.0
target_files:
  - /CONTRACT.md
  - /CORE-RULES.md
  - /CORE.md
  - /shared/skills/repository-preflight/SKILL.md
---

# Knowledge by subject: a node's knowledge file becomes an index when it outgrows one file

Read `/CONTRACT.md` first. This proposal amends CONTRACT §3.1 and §4, and the validator's *Failure behaviour*; every rule keeps its identifier
(CONTRACT §13.2). The contract changes and takes the next minor version at acceptance: 3.4.0, or the one after it if another contract change of the same day is accepted first (CONTRACT §13.3). It is one of five proposals of 24 November 2026 that came out of
measuring what a session reads before it works; each can be accepted or refused alone.

## Plain-language summary

1. **A place for knowledge that has outgrown one file.** A node may keep its knowledge in subject files under `knowledge/`; `KNOWLEDGE.md` then lists them, one line each, and keeps the facts that fit no subject.
2. **The same rules apply to a subject file** as to `KNOWLEDGE.md`: dated claims, superseded claims kept and marked, a source and an evidence status for outside content. The validator checks them there too.
3. **A limit.** `KNOWLEDGE.md` is at most 28,000 characters. No knowledge file in the owner's memory is over it today, so nothing has to move at acceptance.
4. **The large files are in project repositories,** which run their own checks. This proposal gives them the place and the script that names them; splitting each by subject is work for the thread that knows the project.

## Current problem

A knowledge file is read whole when anything in it is needed. Measured on 24 November 2026: one project's knowledge file is 210,455 characters, about 53,000 tokens, and four others are between 40,000 and 85,000. The contract offers a "dedicated knowledge node" for such a case, which is a heavier thing than a file per subject, and no project has used it.

## Current wording and exact diff

### 1. `/CONTRACT.md` – §4, `KNOWLEDGE.md`, new paragraph after "Do not use it for …"

Current:

> (nothing: this is new text)

Proposed:

> A node whose knowledge outgrows one readable file keeps it by subject: each subject has a file under `knowledge/`, and `KNOWLEDGE.md` becomes the index – one line per subject file, saying what it holds – together with the facts that fit no subject. A subject file is knowledge like `KNOWLEDGE.md` itself: everything this section and section 11.6 say of `KNOWLEDGE.md` holds for it, and an agent reads it when its subject is the work's. `KNOWLEDGE.md` is at most 28,000 characters, so that a host shows it whole.

Why: Says when a node splits its knowledge, what the index holds, that a subject file is knowledge in every respect, and sets the size a host shows whole as the limit.

### 2. `/CONTRACT.md` – §3.1, the layout of a complete node (only the changed part is shown)

Current:

> KNOWLEDGE.md
> tasks/
> skills/

Proposed:

> KNOWLEDGE.md
> knowledge/
> tasks/
> skills/

Why: The layout lists what a node may contain; the folder joins it. Empty folders stay optional.

### 3. `/CONTRACT.md` – front matter

Current:

> contract_version: 3.3.0

Proposed:

> contract_version: 3.4.0 (or the next minor version, if another contract change is accepted first)

Why: A minor version: behaviour is added and existing content stays valid (CONTRACT §13.3). The repository manifests of the three brain repositories record the new version.

### 4. `/shared/skills/repository-preflight/SKILL.md` – *Failure behaviour*, new line after "the core is current"

Current:

> (nothing: this is new text)

Proposed:

> - **knowledge by subject (CONTRACT §4):** the checks on a `KNOWLEDGE.md` – a claim past its review date, new knowledge that cites a source without an evidence status – cover every Markdown file in a `knowledge/` folder beside one; fail when a `KNOWLEDGE.md` in the mechanics or the memory is longer than 28,000 characters. A project repository's `brain/KNOWLEDGE.md` is not checked here; `scripts/state.py check --knowledge` names it

Why: The knowledge checks follow the knowledge into its subject files, and the limit is checked.

## Measured

- `/CORE.md` and `/CORE-RULES.md` together, read first by every writing session: 52,231 characters today, 52,231 with this proposal alone, 43,068 with all five of 24 November.

## Reason

`SMART-RULE-0003`: related content readable in small, targeted pieces.

## Scope and consequences

Every node. Nothing changes for a node whose knowledge fits one file. The contract takes a minor version.

## Risks, conflicts and migration

- **Knowledge is split badly and a fact is not found.** The index line of each subject file says what it holds, and a fact that fits no subject stays in `KNOWLEDGE.md`.
- **A subject file escapes the checks.** The validator covers every Markdown file in a `knowledge/` folder beside a `KNOWLEDGE.md`.
- **The name `knowledge/` is also used inside access skills** for API quirk entries (`SMART-RULE-0013`). Those are in skill folders, not in nodes; the two do not meet.

## Rollback

Restore the two contract passages and the version, and remove the failure line and the check. Subject files stay valid Markdown and can be folded back.

## Planned validation

After acceptance: the wording by script, the validator change with tests for a past review date and a missing evidence status in a subject file, the manifests, the full preflight.
