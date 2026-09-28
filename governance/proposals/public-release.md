---
id: PROPOSAL-public-release
title: Ready the smarts repository for public release
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
created: 2026-09-28T15:12:20+10:00
updated: 2026-09-28T15:12:20+10:00
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-09-28T15:12:20+10:00
implemented_at: 2026-09-28T15:12:20+10:00
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /shared/skills/repository-preflight/scripts/hooks.py
  - /README.md
---

# Ready the smarts repository for public release

Read `/CONTRACT.md` first. Accepted by the owner on 28 September 2026 with the decision to make
this repository public.

In the order they were done:

1. A `commit-msg` hook in the mechanics and the library (`hooks.py commit-msg`) runs the
   preflight's personal-data check on every commit message, which `SMART-RULE-0008` already
   covered in words but nothing checked. The Co-Authored-By trailer is skipped.
2. `/LICENSE` (MIT, "the brain-smarts authors"), `/SECURITY.md`, `/CONTRIBUTING.md`, and a
   paragraph at the top of `/README.md` saying what this is and who it is for.
3. The history is rewritten once before the repository becomes public: every author set to the
   owner's private GitHub address, and the owner's name in six commit messages replaced by "the
   owner". Local copies of the old history are rebased onto the new one.
4. GitHub settings after the change of visibility: branch protection on `main`, secret scanning
   with push protection, Dependabot alerts.

Rollback: revert the commits of parts 1 and 2; parts 3 and 4 are settings and history, restored
from the local backup mirror if ever needed.
