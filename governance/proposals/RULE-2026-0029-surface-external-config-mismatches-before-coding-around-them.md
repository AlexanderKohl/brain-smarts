---
id: RULE-2026-0029
title: Surface external-system configuration mismatches before coding around them
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0029
owner: brain-owner
created: 2026-09-09T12:20:00+10:00
updated: 2026-09-09T12:30:00+10:00
accepted_by: brain-owner
accepted_at: 2026-09-09T12:30:00+10:00
implemented_at: 2026-09-09T12:30:00+10:00
previous_contract_version: 0.8.0
new_contract_version: 0.8.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
supersedes: []
---

# RULE-2026-0029: Surface external-system configuration mismatches before coding around them

## Plain-language summary

When an agent finds that two things in an external system do not line up – mismatched picklist
options, a field that does not exist, incompatible types, a naming collision – it must tell the
owner **before** writing code to bridge the gap. Very often the cheaper fix is a two-minute change
in that system's own interface, and a translation layer written instead becomes permanent
complexity that hides the real inconsistency.

The agent should still do the investigation and come with the specifics: what disagrees, what the
options are, and what it would otherwise build. It just must not silently build the workaround.

## Current problem

Nothing in the root rules governs this, so the default behaviour is to treat an external-system
inconsistency as a coding problem. On 2026-09-09, building the Site Visit status webhook, the agent
found that `custom_objects.site_visits.status` offered `Required / Scheduled / Completed` while
`opportunity.site_visit_status` offered `Required / Scheduled / Submitted` – so `Completed`, the
value the webhook existed to propagate, had no valid target. The agent wrote a `STATUS_ALIASES`
mapping table, a validation path and three tests around it, then flagged the assumption afterwards.
The owner's actual fix was to edit the opportunity field's options in the HighLevel interface,
which took moments and made the entire mapping layer dead code.

The cost is not only the wasted work. A translation layer encodes a mismatch that no longer needs
to exist, and the next reader has to work out whether it is load-bearing.

## Current wording

There is no active repository-wide rule requiring an agent to raise an external-system
configuration mismatch before implementing a workaround for it. `RULE-2026-0018` covers
communication efficiency and permits a reversible default when the risk is low, which currently
reads as licence to build the workaround and mention it afterwards.

## Proposed wording

To be added to `/RULES.md` as a new numbered rule:

```markdown
## RULE-2026-0029 – Surface external-system configuration mismatches before coding around them

- When work against an external system reveals that its configuration is inconsistent with what
  the task needs – mismatched option sets, a missing or wrongly-typed field, a naming collision, a
  value that cannot be represented in the target – stop and put the finding to the owner before
  writing code that bridges it. State precisely what disagrees, what a fix in that system would
  be, and what the code workaround would otherwise cost.
- This overrides the "prefer a reversible default and proceed" guidance in `RULE-2026-0018` for
  configuration mismatches specifically. The reason is not risk but economy: a change in the
  external system's own interface is frequently far cheaper than a translation layer, and the
  layer outlives the mismatch it was written for.
- Continue with every part of the task that does not depend on the answer, so the question arrives
  with the rest of the work already done rather than blocking it.
- This does not apply to genuine API behaviour that cannot be configured away – an endpoint's
  response shape, a required header, a status code. Absorb those in code and record them under
  `RULE-2026-0022`.
```

## Reason for the change

The owner asked for it directly on 2026-09-09, after the Site Visit status mismatch above:
"When you find inconsistencies like that, check with me first before implementing a fix, as
sometimes this is an easy adjustment on the front end, instead of needing complicated code."

## Affected scope and expected consequences

Applies to every project in this repository that integrates with an external system – currently
HighLevel, Xero, Railway and Google Workspace work. Agents will ask more questions during
integration work, and will write fewer compatibility shims. Turnaround on such tasks may be
slightly slower where the owner is not immediately available; the trade is deliberate.

## Risks and conflicts

- Over-application could make an agent stop for trivial differences that genuinely belong in code.
  The rule's final bullet draws that line at configurable-versus-inherent.
- Partial tension with `RULE-2026-0018`'s reversible-default guidance, resolved explicitly in the
  wording rather than left to interpretation.

## Migration requirements

None. No existing record or code needs changing. The `STATUS_ALIASES` table in
a client API project's status module has already been emptied now that the owner aligned the
option sets, and is retained only as an extension point.

## Rollback method

Remove the `RULE-2026-0029` section from `/RULES.md`, remove its ID from the root ID list, and set
this proposal's `status` back to `proposed`.

## Planned validation

Run `shared/skills/repository-preflight/scripts/preflight.py` and confirm the error count is
unchanged from its pre-change baseline of 11 (all pre-existing, mostly `source_refs` anchors the
validator cannot resolve).

## Acceptance

Accepted by the owner on 2026-09-09T12:30:00+10:00 ("yes, accept"). The rule is active in root
`/RULES.md`; `accepted_proposal` there now reads `RULE-2026-0029` and `0029` was added to the root
ID list. `contract_version` is unchanged at 0.8.0 – this adds a root rule, not contract behaviour.
