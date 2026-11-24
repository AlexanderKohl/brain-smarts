---
id: PROPOSAL-history-in-commits
title: History lives in the commit: the log holds only what no commit holds
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T18:22:16+10:00
updated: 2026-11-24T18:22:16+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.4.0
target_files:
  - /CONTRACT.md
  - /CORE-RULES.md
  - /CORE.md
  - /RULES.md
---

# History lives in the commit: the log holds only what no commit holds

Read `/CONTRACT.md` first. This proposal amends `SMART-RULE-0009`, `SMART-RULE-0019`, `SMART-RULE-0046`, and CONTRACT §4, §5.3 and §15; every rule keeps its identifier
(CONTRACT §13.2). The contract changes and takes the next minor version at acceptance: 3.4.0, or the one after it if another contract change of the same day is accepted first (CONTRACT §13.3). It is one of six proposals of 24 November 2026 that came out of
measuring what a session reads before it works; each can be accepted or refused alone.

## Plain-language summary

1. **The commit is the record of a change.** Its subject says what changed; its body says why whenever the change does not show it.
2. **The log stops retelling commits.** It holds what no commit holds: a decision and the owner's words, what was ruled out, a measurement, an event outside the repository, a correction. Where an entry belongs to a commit it names the hash.
3. **A checkpoint lists no commits, versions or merges.** Git has them, and `state.py since` prints them when someone wants them.
4. **A release is recorded once.** The notes moved into `released/<version>/` are its record, and the production commit gets a tag. State files and logs name the version only.
5. **No GitHub release text.** The release-notes skill already publishes the team page from the same notes; a GitHub release would be a third copy of them, so this proposal adds only the tag.

## Current problem

The same change is written several times. Measured on 24 November 2026 in the owner's brain: in the busiest project repository, 323 of 596 commits in thirty days already explain themselves in a body and 392 name a release note, yet its log (219,862 characters) quotes 168 commit hashes and its handover history (126,890 characters) quotes 118 hashes and 467 version numbers, retelling what those commits and notes record. In the memory repository only 44 of 918 commits have a body, so there the log is the only place a reason is written, apart from the change.

## Current wording and exact diff

### 1. `/RULES.md` – `SMART-RULE-0009`, fifth bullet (only the changed part is shown)

Current:

> and commit with a concise message whose subject says what changed and never names the tool or the model. Two trailers of the same commit name them:

Proposed:

> and commit with a concise message whose subject says what changed and never names the tool or the model, and whose body says why whenever the change itself does not show it: the decision, the instruction or the finding behind it. The commit is the record of the change, and `LOG.md` does not tell it again (CONTRACT §4). Two trailers of the same commit name the tool and the model:

Why: A commit body is the cheapest place for the reason: it is written once, travels with the change and is read only when someone asks. "Name them" becomes "name the tool and the model" because the new sentences come between.

### 2. `/RULES.md` – `SMART-RULE-0019`, the bullet on what a checkpoint updates

Current:

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what happened and why; and the task's store
>   (CONTRACT §9) for anything outstanding.

Proposed:

> - A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
>   flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
>   facts a later session could not re-derive cheaply – especially external-system behaviour
>   established by experiment; `LOG.md` with what no commit holds (CONTRACT §4); and the task's
>   store (CONTRACT §9) for anything outstanding. It does not list the commits, versions and merges
>   since the last checkpoint: Git holds them, and `state.py since` prints them when they are wanted.

Why: "What happened and why" was the instruction that produced handover entries full of versions and hashes. The checkpoint now writes the position and what Git cannot know.

### 3. `/RULES.md` – `SMART-RULE-0046`, new bullet before the last

Current:

> (nothing: this is new text)

Proposed:

> - **A release is recorded once.** The notes moved into `released/<version>/`, with the `release.json` beside them, are the record of what a release contained and which environment it reached when. The commit released to production carries an annotated tag `v<version>`, so Git itself shows what is in production. `STATE.md`, `LOG.md` and a handover entry name the version and do not list what it contained.

Why: The release-notes skill already keeps the record of a release; this says so, adds the tag that makes Git show what is in production, and stops state files and logs from listing a release's content.

### 4. `/CONTRACT.md` – §4, `LOG.md`, new paragraph

Current:

> Begin each event group with an ISO 8601 timestamp heading. Append new entries. Do not rewrite historical entries except to correct an identified error, and record the correction.

Proposed:

> Begin each event group with an ISO 8601 timestamp heading. Append new entries. Do not rewrite historical entries except to correct an identified error, and record the correction.
>
> A change a commit made is recorded by the commit: its message says what changed and why (`SMART-RULE-0009`), and the log does not tell it again. The log holds what no commit holds: a decision and the owner's words behind it, what was ruled out and the evidence that ruled it out, a measurement, an event outside the repository such as a deployment or an approval, and a correction to what an earlier commit message said. An entry that belongs to a commit names it by its short hash.

Why: The contract defined the log as events, actions and decisions without saying what a commit already covers. This paragraph draws the line.

### 5. `/CONTRACT.md` – §5.3, when a state change gets a log entry

Current:

> Create a `LOG.md` entry when the change is significant, explains a decision or is needed for traceability.

Proposed:

> Create a `LOG.md` entry when the change is a decision, or when no commit records it and it is significant or needed for traceability (section 4).

Why: The old sentence asked for an entry for every significant change, which is what a commit now records.

### 6. `/CONTRACT.md` – §15, the integrity check on logging

Current:

> - significant changes are logged

Proposed:

> - significant changes are recorded: by their commit, and in the log what no commit holds (section 4)

Why: The check now matches the definition in §4.

### 7. `/CONTRACT.md` – front matter

Current:

> contract_version: 3.3.0

Proposed:

> contract_version: 3.4.0 (or the next minor version, if another contract change is accepted first)

Why: A minor version: behaviour is added and existing content stays valid (CONTRACT §13.3). The repository manifests of the three brain repositories record the new version.

## Measured

- `/CORE.md` and `/CORE-RULES.md` together, read first by every writing session: 52,231 characters today, 52,504 with this proposal alone, 43,341 with all six of 24 November.

## Reason

`SMART-RULE-0007`, one text per thing, applied to history; and `SMART-RULE-0003`: the largest saving is in what an agent writes at every checkpoint, where the same change now goes into a commit message, a log entry and a handover entry.

## Scope and consequences

Every agent that commits, in every repository. Logs become shorter and are about decisions. Reading history means `git log`, which is on demand. The contract changes in three places and takes a minor version; one of them, §5.3, is in the core. Nothing existing is rewritten: logs and histories written so far stay as they are.

## Risks, conflicts and migration

- **A reason is lost because nobody wrote the body.** Nothing checks that a body says why; a hook cannot judge it. The commit-message hook stays as it is.
- **A commit message cannot be corrected,** because commits are never amended. A correction is a log entry, which the new §4 text names.
- **A decision with no commit is forgotten.** It is exactly what the log is now for.
- **History is harder to read in one place.** `state.py since` prints a repository's commits with their release notes; a story across several repositories still needs one log entry that names them.
- **Tags need the production branch.** The tag is made when a version is released to production, by the thread that releases it; a project that has not released to production yet has no tag, and that is correct.

## Rollback

Restore the passages of the three rules and of the contract, and the version. Tags and commit bodies written meanwhile do no harm.

## Planned validation

`state.py since` and its test are on `main`. After acceptance: the wording by script, the tag line in the release command with the release-notes tests, `core.py build`, the manifests, the full preflight.
