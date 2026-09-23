---
id: RULE-2026-0014
title: Auto-stage after successful changes; commit and push on finish or hourly
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0014
target: /RULES.md
target_files:
  - /RULES.md
created: 2026-08-06T15:24:00+10:00
updated: 2026-08-06T15:24:00+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-08-06T15:24:00+10:00
implemented_at: 2026-08-06T15:24:00+10:00
previous_contract_version: 0.4.0
new_contract_version: 0.4.0
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0014: Auto-stage after successful changes; commit and push on finish or hourly

## Status

Accepted and implemented from the owner's explicit instruction to add this development rule. Applied to `/RULES.md` at 2026-08-06T15:24:00+10:00. No `contract_version` change.

## Reason

Keep durable work continuously staged and explained, and land commits/pushes without waiting for a separate commit request – at project completion or about once per hour of active work.

## Proposed wording

Add under `/RULES.md` Repository rules (Development / git workflow):

```markdown
- After every successful material change set in this repository, automatically `git add` only the files touched for that change (never secrets or unrelated dirty files) and briefly explain each change to the owner in the chat response.
- Automatically create a git commit and push to the tracked remote when either (a) the current project or defined unit of work is finished, or (b) about one hour of active work has passed since the last commit/push for that workstream while durable staged or unstaged project changes remain. Use a concise commit message; do not use `--no-verify` or force-push to `main`/`master` unless the owner explicitly directs it for that push.
- Still never commit secrets, credentials, vault ciphertext, or private tokens. If unsure whether a path is secret or unrelated, leave it unstaged and ask.
```

## Acceptance

Owner directed: “Add a rule about development to clarify that you should automatically stage to git after every successful change and explain each change. The final commit & push should happen automatically when a project is finished or once every hour.”
