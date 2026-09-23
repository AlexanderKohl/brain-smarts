---
id: RULE-2026-0041
title: A name means one thing, everywhere, and a bad name is raised before it is built on
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-15T21:04:09+10:00
updated: 2026-09-15T21:04:09+10:00
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# A name means one thing, everywhere, and a bad name is raised before it is built on

## Current problem

A CRM custom object's record-type field was created as `Kind`. The owner asked for it to be called
`Type`, and the first change renamed only what a person sees, leaving the key `kind`, the
constants `KIND_EXTERNAL_SYSTEM` and friends, the type `RecordKind` and a dozen helpers
speaking the older word. The result was a field with two names, one for people and one for
code, and every future reader would have had to learn both. The owner's instruction on seeing
it was to finish the rename while an object exists in only one sub-account and the cost is a
delete and a recapture.

That is the general case. A name that drifts costs every later reader a translation step, and
the cost is paid forever while the fix is cheap only at the start. Nothing in the rules says a
name must be one word for one thing, or that an agent should say so when it is handed a name
that will not hold.

## Current wording

None. `RULE-2026-0028` governs the development process and `RULE-2026-0035` governs tests.
Neither mentions naming.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0040` and before the contract-restatement list:

```markdown
## RULE-2026-0041 – A name means one thing, everywhere

- One thing has one name, and that name is the same in the interface, the code, the stored
  data, the specification and the conversation. A field called `Type` on screen is `type` in
  its key, its constants and its helpers. Where a name must differ, because something outside
  the brain fixes it, the code says in one line why and where the translation happens.
- A name says what the thing is, in the domain's own words, at the length that makes it
  unambiguous. Names in one set are built the same way, so a reader who learns one can guess
  the rest.
- A name is corrected while it is cheap. The moment a rename costs only a delete and a rebuild
  is the moment to do it; once data, integrations or habits carry the old name, the same fix
  needs a migration. Renaming is not deferred to a tidy-up that never comes.
- An agent given a name that will not hold – one that means something else in the same system,
  one that will read as wrong to the next person, one inconsistent with the names around it –
  says so before building on it, proposes the better name and the reason, and proceeds on the
  owner's answer. This is not a veto: the owner may keep their word, and the agent then uses it
  consistently everywhere.
```

Append `0041` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0041`.

## Reason

Naming is the part of a system every reader touches and no test catches. Making the standard
explicit turns "I would have called it something else" into a question asked at the right
moment, which is before the name reaches stored data.

## Scope and behavioural consequences

Every project the brain works on, and the brain's own records. The first application is the
custom object's record-type field, whose key becomes `type` at extension `0.19.0`, with the object in
the one sub-account that holds it deleted and recreated rather than migrated. Agents raise a
naming concern in the same reply that reports the work, with a suggested better name, under
the question form of `RULE-2026-0018` A1.

No `contract_version` change: a root rule, not contract behaviour.

## Risks and conflicts

- **Bikeshedding.** The rule asks for one sentence naming a better option, not a debate; the
  owner's answer ends it.
- **A rename that is no longer cheap.** The third bullet is about the moment, not about
  renaming at any price; where data already carries the name, the change becomes an ordinary
  breaking change under `RULE-2026-0039` and is weighed as one.
- Complements `RULE-2026-0040` (a list's order is chosen deliberately) and `RULE-2026-0018` A1
  (a question carries its suggestion). No conflict found.

## Migration

None. Existing names are corrected when their owner next touches them, or when the cost is
still only a delete and a rebuild.

## Rollback

Remove the `RULE-2026-0041` section from `/RULES.md`, drop `0041` from the root ID list,
restore `accepted_proposal`, and set this proposal to `reverted`.

## Validation

- Repository preflight before and after activation reports the same error count.
- The custom object field's key reads `custom_objects.example.type` and nothing in the extension reads
  the old key.

## Acceptance

**Question to ask:** 1. Accept `RULE-2026-0041` as written (recommended); 2. accept without the
third bullet, so renaming while cheap stays a judgement call rather than a rule; 3. reject.
Not yet accepted.
