---
id: RULE-2026-0013
title: Include repository-root cd in owner-facing shell commands
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0013
target: /RULES.md
target_files:
  - /RULES.md
created: 2026-08-06T14:38:00+10:00
updated: 2026-08-06T14:38:00+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T14:38:00+10:00
implemented_at: 2026-08-06T14:38:00+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0013: Include repository-root cd in owner-facing shell commands

## Status

Accepted and implemented from the owner's explicit instruction to add this as a rule and to include `cd` when giving commands to run. Applied to `/RULES.md` at 2026-08-06T14:38:00+10:00. No `contract_version` change.

## Reason

The owner should not have to search for the correct working directory when running agent-supplied shell commands.

## Proposed wording

Add to `/RULES.md` Repository rules:

```markdown
- Whenever giving the owner shell commands to run, always include an explicit `cd` (or equivalent) to the repository root `<brain_root>` (or the active absolute working directory if the command must run elsewhere) before the command, so the owner does not have to locate the correct folder.
```

## Acceptance

Owner directed: “whenever giving me code to run, include the cd command so I don't have to search for the correct folder. Do it now for the above commands and add it as a rule.”
