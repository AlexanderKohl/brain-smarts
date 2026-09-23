---
id: RULE-2026-0034
title: Security designed into every implementation
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0034
owner: brain-owner
created: 2026-09-14T21:26:19+10:00
updated: 2026-09-15T00:45:46+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T00:45:46+10:00
implemented_at: 2026-09-15T00:45:46+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
related_rules:
  - RULE-2026-0028
supersedes: []
---

# RULE-2026-0034: Security designed into every implementation

## Plain-language summary

In every development project, security, privacy and access control are part of writing the
change, not a review step afterwards. For each relevant change the agent considers who is
authenticated, what they are authorised to do, whether tenant and account data stay separated,
whether inputs are validated, how secrets are handled, whether sensitive data reaches logs or
responses, and what happens on failure. It applies least privilege, enforces important rules on
the server side rather than in the UI, and fails closed when identity or scope is uncertain.

This lifts "fail closed" from a client development node to the root and gives every
product repository the same baseline. It does not change `/CONTRACT.md`.

## Current problem

No root rule addresses security in code. `/CONTRACT.md` §10.3 covers secrets in the repository
and §10.5 covers confirming an external target before a write. Security appears otherwise only in
node rules: "fail closed when client identity, tenant identity or required mappings are
uncertain" in a client development node's `RULES.md`, tenant scoping in
a CRM documentation project's `RULES.md`, and vault handling in
`/projects/credential-management/RULES.md`. A new product node starts with none of that.

The product-development skill names security at standard and high-assurance depth, but the
light path does not, and a light-path change can still add an endpoint, a log line or a query
that crosses a tenant boundary. Security therefore depends on which node the work happens to sit
in and which depth was chosen, rather than on the change itself.

## Current wording

None at root. The node wording being generalised is:

```markdown
- Fail closed when client identity, tenant identity or required mappings are uncertain.
```

That node bullet stays in place; it is not removed by this proposal.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0033` (or after `RULE-2026-0032` if 0033 is not accepted)
and before the contract-restatement list:

```markdown
## RULE-2026-0034 – Security designed into every implementation

- In every software or development project, treat security, privacy and access control as part
  of the implementation, not a later review step. For each change that touches an endpoint,
  a query, a permission, stored or transmitted data, an integration or a log, consider:
  authentication, authorisation, tenant and account isolation, input validation and output
  encoding, secrets and credential handling, sensitive data in responses and logs, API
  permissions and scopes, and what the code does when a check fails.
- Apply least privilege. Request, store, transmit and expose the minimum sensitive data and the
  narrowest scopes the requirement needs.
- Do not rely on UI restrictions for security. Enforce important rules server-side at the
  trust boundary that owns them.
- Fail closed. When identity, tenant, scope or a required mapping is uncertain, stop the
  operation and report, rather than proceeding with a guess or a default.
- Scope every query, write and external call by the tenant, account or location it belongs to.
  Do not let a request for one tenant read or change another's data through a missing filter or
  an inferred identifier.
- Never log or return secrets, tokens, credentials or more personal data than the caller is
  entitled to. Treat a leaked identifier that grants access as a credential.
- When a change materially widens an externally reachable surface, adds an authentication or
  payment path, or handles sensitive data for the first time, escalate to at least standard depth
  under `RULE-2026-0028` and say so in the change.
```

At implementation time only, update `/RULES.md` metadata and add `0034` to the root-ID inventory
in the same manner as `RULE-2026-0033`.

No existing rule is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

The owner's supplied development principles include "design security into every
implementation" with an explicit checklist. On review, none of that exists at root. The
highest-value part is the one already proven in a node: fail closed on uncertain identity or
tenant. The rest is the minimum a multi-tenant product built against HighLevel, Xero and Google
needs on every change, regardless of node or depth.

## Scope and behavioural consequences

- Applies to all software and development projects governed by this brain, including external
  app repositories worked from this brain.
- Agents will state, for a relevant change, how authentication, authorisation, tenant isolation
  and failure behaviour are handled. This is a sentence or two in the completion report, not a
  security document.
- A change that widens the attack surface triggers the existing product-development depth
  escalation rather than a new process.
- Node rules that already say more (the client development node, the CRM documentation project, Credential
  Management) remain in force and are unaffected.

## Risks and conflicts

- "Fail closed" can make a system less available when configuration is incomplete. That is the
  intended trade: the client development node has run on it since 2026-08-04 without a recorded
  objection.
- The consideration list could be read as a mandatory written checklist on every edit. The first
  bullet bounds it to changes that touch the named surfaces, and the scope section makes clear
  that the output is a brief statement, not a document.
- No conflict with `RULE-2026-0028`; the last bullet uses its depth ladder rather than defining
  a new one.

## Migration

None. Existing code is not retroactively audited because this rule becomes active. Apply it to
new work and to any change that already touches the affected surface. Where a security review of
an existing product is wanted, open a task under `/tasks/`.

## Rollback

Remove the `RULE-2026-0034` section from `/RULES.md`, remove `0034` from its root-ID inventory,
restore the prior `accepted_proposal` metadata, and mark this proposal `reverted`.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require the same error count as before the change.
3. Confirm the live root rule exactly matches the accepted wording and no other rule changed.
4. Confirm the root-ID inventory contains `0034` once.

## Acceptance

**Question asked:** Do you accept `RULE-2026-0034` with exactly the wording in its proposal?

**Accepted by the owner, 2026-09-15T00:45:46+10:00**, in the words "I accept RULE-2026-0033 and 0034 and 0035",
answering the three per-proposal acceptance questions by ID.

## Implementation record

Implemented 2026-09-15T00:45:46+10:00. `RULE-2026-0034` added to `/RULES.md` with the accepted wording
unchanged, placed after `RULE-2026-0032` in numeric order and before the contract-restatement
list. `0034` appended to the root ID list; `accepted_proposal` now reads `RULE-2026-0035`
(the last of the three rules accepted together). `contract_version` unchanged at 0.9.0 – a root
rule, not contract behaviour.

**Validation:** see the brain-development log entry for 2026-09-15T00:45:46+10:00.
