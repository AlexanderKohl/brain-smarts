---
id: PROPOSAL-client-systems-and-credentials
title: Client systems and credentials in every development project
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-28T09:49:19+10:00
updated: 2026-09-28T09:49:19+10:00
rule_id: SMART-RULE-0021
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.0.1
new_contract_version: 2.0.1
target_files:
  - /RULES.md
---

# Client systems and credentials in every development project

## Plain-language summary

Two bullets are added to `SMART-RULE-0021` (security designed into every implementation), so
every development project, and every collaborator whose brain inherits these mechanics, follows
them:

1. Credentials stay out of every tracked file, including application configuration, and a
   credential that ever reached Git history is rotated, not only deleted.
2. An agent gets the owner's explicit approval before it writes to a client's live external
   system, naming the system and the target.

The rule keeps its number. `/CONTRACT.md` does not change.

## Current problem

Rules of this kind were written for one owner's node and so reach only that owner's agents. A
collaborator who clones a project repository inherits the mechanics and the project's own
`brain/RULES.md`, never the owner's memory (CONTRACT §3.4, §16.2), so a rule that lives only in a
memory node does not reach them.

Two gaps remain in the mechanics:

- CONTRACT §10.3 keeps secrets out of Markdown and committed scripts, and `SMART-RULE-0021` keeps
  them out of logs and responses. Neither names application configuration, such as a per-company
  settings file, which is where a credential is most easily committed. Nor does either say what
  to do once one has been: deleting the line leaves the credential in Git history, readable by
  anyone who can clone the repository.
- CONTRACT §10.5 makes an agent confirm *which* account or location a write goes to. It does not
  require approval of the write itself, so a confirmed target can still be changed without the
  owner deciding that it should be.

Already covered, and not restated here: failing closed when identity, tenant or a mapping is
uncertain (`SMART-RULE-0021`), and naming the account, organisation or location on retrieved
data (CONTRACT §10.4).

## Current wording

`/RULES.md`, `SMART-RULE-0021`, the two bullets the new ones follow:

```markdown
- Scope every query, write and external call by the tenant, account or location it belongs to.
  Do not let a request for one tenant read or change another's data through a missing filter or
  an inferred identifier.
- Never log or return secrets, tokens, credentials or more personal data than the caller is
  entitled to. Treat a leaked identifier that grants access as a credential.
```

## Proposed wording or exact diff

```diff
 - Scope every query, write and external call by the tenant, account or location it belongs to.
   Do not let a request for one tenant read or change another's data through a missing filter or
   an inferred identifier.
+- Before an agent writes to a client's live external system – its records, configuration or
+  structure, directly or by running code that writes – get the owner's explicit approval for
+  that write, naming the system and the target account or location (CONTRACT §10.5). An account
+  the project's own rules name as a test or sandbox account is not live.
 - Never log or return secrets, tokens, credentials or more personal data than the caller is
   entitled to. Treat a leaked identifier that grants access as a credential.
+- Keep credentials out of every tracked file, including application configuration such as
+  settings, company or fixture files; load them from the environment or a secret manager at run
+  time. A credential that reaches Git history is rotated at its issuer, not only deleted from
+  the file.
```

The index row in `/RULES.md` is unchanged.

## Reason

A mechanism any owner could adopt belongs in `/RULES.md` (`SMART-RULE-0007`, CONTRACT §3.4), and
the mechanics is the one rule layer that a collaborator's own brain receives. Both bullets are
generic security practice and carry no personal data. They extend an existing rule rather than
add a new one (CONTRACT §13.2).

## Scope and behavioural consequences

- Applies to every software or development project, as `SMART-RULE-0021` already does.
- An agent asks before any write to a client's live system, including running a script or a test
  that writes there. Reads, and writes to accounts the project's rules name as test or sandbox
  accounts, need no approval.
- An agent that finds a credential in a tracked file, or in history, reports it to the owner and
  recommends rotation. Rotation itself is the owner's step, because it happens at the issuer.
- Owner-layer or node rules that say the same thing become redundant and can be removed in the
  owner's own memory, as a separate change there.

## Risks and conflicts

- More approval questions during integration work. A project that uses a sandbox avoids them by
  naming it in its rules.
- No conflict with CONTRACT §10.5, which still applies: the approval names the confirmed target.

## Migration

None. Existing tracked credentials are handled when found, under the new bullet.

## Rollback

Remove the two added bullets from `SMART-RULE-0021` in `/RULES.md`.

## Validation

Run the repository preflight validator, including the personal-data check, after applying.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence, adjacent approval or general agreement as acceptance.

## Implementation record
