---
id: RULE-2026-0016
title: No real data in mock or sample data
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0016
target: /RULES.md
target_files:
  - /RULES.md
created: 2026-08-06T17:41:33+10:00
updated: 2026-08-06T17:45:18+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T17:45:18+10:00
implemented_at: 2026-08-06T17:45:18+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
---

# RULE-2026-0016: No real data in mock or sample data

## Status

Accepted and implemented from the owner's explicit acceptance ("accept RULE-2026-0016") at 2026-08-06T17:45:18+10:00. Applied to `/RULES.md` at the same time. No `contract_version` change (root operating rule, not contract behaviour).

Proposed. Awaiting owner acceptance.

## Reason

While building a design prototype in an external project repository,
the agent explored a sibling project repository to check whether it was
the tool the owner meant. That listing surfaced real customer
smart-meter data filenames, including two real customers'
names tied to real meter numbers. When later inventing three sample
customers for the new prototype's mock data, the agent reused two of
those real names (pairing them with fabricated addresses – arguably
worse than a plain placeholder, since it falsely associates a real
person with fictional data) and a third name that echoed another sibling
project's folder name. This was not a deliberate choice; the
names were simply still in context and read as plausible-sounding
placeholders. The owner caught it and asked for both a fix and a durable
rule so it does not recur in this or future projects.

## Current wording

`/RULES.md` has no rule addressing the source of mock, sample, seed,
fixture or placeholder data used in prototypes, demos or tests.

## Proposed wording

Add this bullet to the `## Repository rules` section of `/RULES.md`
(insert near the other data-hygiene bullets, e.g. after "Preserve raw
files unchanged."):

```markdown
- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data – including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
```

## Scope and behavioural consequences

- Applies repository-wide, to every project and to any external code
  repository built or maintained through this brain, not only to Markdown content.
- Applies to names, addresses, phone numbers, emails, ABNs/company
  numbers, meter numbers, and any other identifier that could plausibly
  trace back to a real person or business.
- Does not restrict use of real reference data that is *supposed* to be
  real and owner-approved (e.g. a business's actual product catalogues,
  real API responses in "google" imagery mode) – only data explicitly
  built or labelled as mock/sample/seed/fixture/placeholder.
- No `contract_version` change (root `/RULES.md` operating rule, not a
  contract-behaviour change).

## Risks and conflicts

- Low: this is an additive constraint with no conflict with existing
  rules. The main risk is an agent overlooking it under time pressure
  when generating "realistic" demo data quickly – mitigated by making the
  rule explicit and citing this incident as the reason.

## Migration

The two real customer names and the sibling-project-echoing company name
already found their way into the prototype's sample data,
README, and one Playwright test. These are being replaced with clearly
fictional names as part of the same change that introduces this
proposal – tracked in the owning project node's `LOG.md` in the owner's
memory, not as part of this protected change set itself.

## Rollback

Remove the added bullet from `/RULES.md` and mark this proposal
`reverted` or `superseded`.

## Validation

After acceptance, confirm `/RULES.md` includes the new bullet and run
`/shared/skills/repository-preflight/`.

## Acceptance question

Do you accept proposal `RULE-2026-0016` as written for `/RULES.md`?
