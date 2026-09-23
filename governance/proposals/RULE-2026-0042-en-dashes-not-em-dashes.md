---
id: RULE-2026-0042
title: An en dash, never an em dash
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-16T08:23:12+10:00
updated: 2026-09-16T08:26:59+10:00
accepted_by: brain-owner
accepted_at: 2026-09-16T08:26:59+10:00
implemented_at: 2026-09-16T08:26:59+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# An en dash, never an em dash

## Current problem

The brain's writing mixes the two dashes with no rule behind the choice. The owner's browser extension
alone carried 109 em dashes across 23 files, in text a person reads and in the comments beside
it, and every document and reply in this repository has drifted the same way. The owner reads
the em dash as wrong and has asked for one answer everywhere.

## Current wording

None. `RULE-2026-0026` governs how text is written for a person, and nothing in it or elsewhere
says which dash to use.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0041` and before the contract-restatement list:

```markdown
## RULE-2026-0042 — An en dash, never an em dash

- Everything this repository writes uses the en dash (`–`). The em dash (`—`) is never used:
  not in a document, a record, a comment, a commit message, a string a person reads on screen,
  or a reply in the conversation.
- Where an em dash would have been, an en dash takes its place with a space each side, or the
  sentence is split in two, which is usually better.
- A hyphen stays a hyphen: this rule is about the long dash, and changes nothing in a
  hyphenated word, a command-line flag, or a range written with a hyphen.
- Existing text is corrected when its file is next touched for another reason, in the same
  commit, and never in a pass of its own that buries a change of substance.
```

Append `0042` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0042`.

## Reason

One mark, one rule, no judgement to make each time. The owner's preference is the reason that
matters; the secondary one is that a rule with no exceptions can be checked mechanically and
never argued about.

## Scope and behavioural consequences

Every file the brain writes and every reply it makes, from acceptance onward. The owner's
extension was corrected in full at `0.35.4` on the owner's instruction, which is the exception
to the fourth bullet rather than an example of it: one mechanical replacement of 109 marks
across 23 files, with nothing else in the commit.

Older brain documents keep their em dashes until their files are touched for another reason.
No sweep of the repository is proposed, because a commit that changes 2,700 files says nothing
about what changed.

No `contract_version` change: a root rule, not contract behaviour.

## Risks and conflicts

- **Quoted text.** A quotation of someone else's words is theirs, dash included. The rule is
  about what the brain writes, and a quote is not written by the brain.
- **Generated or vendored files.** A specification snapshot, a dependency, an export from
  another system is not the brain's writing and is left alone.
- Complements `RULE-2026-0026` (writing for a person) and `RULE-2026-0041` (one name for one
  thing). No conflict found.

## Migration

None. The extension is already corrected; everything else is corrected as it is touched.

## Rollback

Remove the `RULE-2026-0042` section from `/RULES.md`, drop `0042` from the root ID list,
restore `accepted_proposal`, and set this proposal to `reverted`.

## Validation

- Repository preflight before and after activation reports the same error count.
- `grep -rc "—" src/ test/` in the extension repository returns nothing.

## Acceptance

**Question to ask:** 1. Accept `RULE-2026-0042` as written (recommended); 2. accept, and add a
preflight check that fails on an em dash in a file the brain wrote; 3. reject.

**Accepted by the owner, 2026-09-16T08:26:59+10:00**, in the words "1. accepted" (option 1, without the preflight check).

## Implementation record

Implemented 2026-09-16T08:26:59+10:00. `RULE-2026-0042` added to `/RULES.md` after `RULE-2026-0041` with the accepted wording, its own heading written with the dash it requires; `0042` appended to the root ID list; `accepted_proposal` set to `RULE-2026-0042`. Contract version unchanged at 0.9.0. The owner's browser extension was already corrected in full at `0.35.4`.
