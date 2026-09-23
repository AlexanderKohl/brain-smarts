---
id: rule-0044-destination-skills-readme
title: Destination Skill Drafts for RULE-2026-0043 and RULE-2026-0044
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: draft
created: 2026-09-17T16:30:00+10:00
updated: 2026-09-17T17:30:00+10:00
owner: brain-owner
---

# Destination Skill Drafts

Draft skill text for review beside `RULE-2026-0043` and `RULE-2026-0044`. These files hold the
procedure those proposals move **out** of root `/RULES.md`, so the owner can see what the rules
would point at before accepting the rules that point at it.

**Nothing here is active.** These are drafts in the proposals store, deliberately outside
`/shared/skills/`, because an unaccepted obligation sitting in an active instruction path would be
picked up by an agent as though it were policy, and would contradict the live rules it is meant to
replace. On acceptance they move to `/shared/skills/` and these drafts are deleted.

The `.draft.md` suffix marks them as text under review, not a skill. None carries `type: skill`,
so nothing loads them as one.

#### Files

`RULE-2026-0043` and amendment A3 were accepted and implemented on 2026-09-17, so the two drafts
that fed them are gone: their text is live at `/shared/skills/learning-maintenance/SKILL.md` and
`/shared/skills/problem-recovery/SKILL.md`, which are now the only versions that matter.

What remains belongs to `RULE-2026-0044`, which is still `proposed`:

- `change-discipline.SKILL.draft.md` – new shared skill that would receive the git-checkpoint and
  versioning procedure from `RULE-2026-0017` and `RULE-2026-0039`.
- `existing-skill-additions.draft.md` – the sections that would be added to
  `/shared/skills/delegate-work/` and `/shared/skills/product-development/`.

#### Removed

The `prototype/` folder is gone, and this is deliberate rather than tidying. It implemented an
expiring-lease, fencing-token, write-ahead-journal store with versioned record files, and the
accepted design uses none of it: `RULE-2026-0043` names no lock, and the live skill says in two
places to keep the prototype inactive and not to use it as the integration mechanism. Keeping 59
passing tests for machinery that will never be built is worse than keeping nothing, because a later
agent would read it as the design.

Its one durable output, four filesystem primitives measured on this host, is captured as a pending
learning artifact under `/projects/brain-development/data/learning/inbox/`. The code is in Git
history at `1f71fe3` if it is ever wanted.

#### Folders

No immediate child folders exist.
