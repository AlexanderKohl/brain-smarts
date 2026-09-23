---
id: RULE-2026-0040
title: Every list has a deliberate order
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-15T16:51:56+10:00
updated: 2026-09-15T18:23:55+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T18:23:55+10:00
implemented_at: 2026-09-15T18:23:55+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# Every list has a deliberate order

## Current problem

Lists reach the owner in whatever order the code or the source data happened to produce
them: the order of a capture, of a map's insertion, of a file listing, of an API response.
The Journey view's workflow dropdown was raised today: the owner asked for it to be sorted and
to drop drafts. The dropdown was in fact sorted, but the ask stands for every list the brain
produces, and nothing in the rules says an agent must decide the order at all. Random order
costs the reader a scan every time; a chosen order tells them where to look.

## Current wording

None. `RULE-2026-0018` governs how questions are asked; `RULE-2026-0028` governs the
development process. Neither says anything about the order of items in a list, a table, a
dropdown or a report.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0039` and before the contract-restatement list:

```markdown
## RULE-2026-0040 – Every list has a deliberate order

- Every list a person reads is put in an order chosen for that reader, never left in the
  order it was produced: the options of a dropdown, the rows of a table, the sections of a
  report, the findings of a check, the bullets of a reply, the entries of an index. Insertion
  order, capture order, map order and API order are not orders; they are accidents.
- The default is alphabetical by the label the reader sees, with numbers inside labels
  compared as numbers, so `1.2` precedes `1.10`. Another order replaces it only when the
  reader is better served by it, and the code or the document says so in a comment or a
  line: by time when the reader follows a sequence, by severity or priority when they act
  on the worst first, by frequency or size when the largest matters most, by a fixed
  domain order when one exists, such as the stages of a pipeline. The chosen order holds
  across renders and captures, so two views of the same data list it the same way.
- A list shows what the reader can use. Items that cannot be used from that list, such as a
  draft where only published items act, are left out or set apart under their own label,
  and the code says which.
- Reviews of a deliverable check its lists: an unordered list is a defect, not a style
  choice.
```

Append `0040` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0040`.

## Reason

Order is a cheap, silent form of help: a reader who knows the order finds the item without
reading the list. Making the choice explicit in code or text stops the accidental order from
returning on the next refactor and lets a reviewer ask "why this order" instead of "is there
one".

## Scope and behavioural consequences

Every deliverable the brain produces, from the next change onward: extension views,
documents, exports, reports, task tables, replies. The owner's browser extension is the first case: the
Journey picker lists published workflows alphabetically at `0.8.2`, and the other twenty or
so sorted lists in its UI script already comply. Lists produced before activation are fixed
when their producer is next changed.

No `contract_version` change: a root rule, not contract behaviour.

## Risks and conflicts

- **A fixed domain order versus alphabetical.** Where both are reasonable the rule prefers
  the one that serves the reader and asks that it be stated; disagreement is settled by the
  owner.
- **Cost of sorting large lists.** Negligible at the sizes the brain handles.
- Complements `RULE-2026-0018` (numbered options in questions are themselves an ordered
  list). No conflict found.

## Migration

None required. Existing lists are brought into order when their producer is next touched.

## Rollback

Remove the `RULE-2026-0040` section from `/RULES.md`, drop `0040` from the root ID list,
restore `accepted_proposal`, and set this proposal to `reverted`.

## Validation

- Repository preflight before and after activation reports the same error count.
- The Journey picker test in the owner's browser extension shows the options alphabetical and drafts
  absent.

## Acceptance

**Question to ask:** 1. Accept `RULE-2026-0040` as written (recommended); 2. accept with
alphabetical as the only order, no exceptions; 3. reject.

**Accepted by the owner, 2026-09-15T18:23:55+10:00**, in the words "accept rule" (option 1).

## Implementation record

Implemented 2026-09-15T18:23:55+10:00. `RULE-2026-0040` added to `/RULES.md` after `RULE-2026-0039` with the accepted wording unchanged; `0040` appended to the root ID list; `accepted_proposal` set to `RULE-2026-0040`. Contract version unchanged at 0.9.0. The owner's browser extension's Journey picker at 0.8.2 is the first list under the rule. Preflight run after the change.
