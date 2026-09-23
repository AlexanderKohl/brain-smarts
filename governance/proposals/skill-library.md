---
id: PROPOSAL-skill-library
title: Skill library – optional skills leave the mechanics for their own repository
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-23T17:12:00+10:00
updated: 2026-09-23T17:12:00+10:00
rule_id: SMART-RULE-0029 (amended, keeps its identifier)
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 1.1.0
new_contract_version: 2.0.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /ONBOARDING_AGENT.md
  - /README.md
  - /SETUP.md
  - /.gitignore
  - /shared/skills/README.md
  - /shared/skills/repository-preflight/
  - /shared/templates/memory-skeleton/
---

# Skill library – optional skills leave the mechanics for their own repository

## Summary

The mechanics repository ("the smarts") keeps only what the brain itself runs on. Every other
reusable skill – access to an outside system, or a way of working the owner may or may not want –
moves to a new repository, the **skill library**, checked out beneath the brain root at
`/library/` exactly as memory is checked out at `/memory/`. The library carries no personal data,
like the smarts, so it can be shared, forked and merged; each owner uses the skills listed in
`active_skills`, and can take in skills other people have written. The owner's own configuration
for every skill stays where it is, in `/memory/skills/<skill>/`.

The layers become four: mechanics, skill library, memory, project repositories.

## Current problem

- The smarts mixes two kinds of skill. Some are the brain's own machinery (the vault, tasks, the
  validator, raw-file ingestion, learning, delegation). Others are optional: access to one
  outside system, or one way of working. An owner who uses neither Xero nor HighLevel still
  carries, reads about and merges changes to both.
- A skill someone else wrote has no natural home: adding it to the smarts makes it part of
  "how the brain works" for everyone.
- CONTRACT §7.1 already says code with its own lifecycle belongs in its own repository; optional
  skills are the largest body of code in the smarts.

## Which skills go where

The test: a skill stays in the smarts when the brain depends on it – a `SMART-RULE` requires it,
or a core skill calls it. Everything else moves. Alphabetical within each list.

| Stays in the smarts (`/shared/skills/`) | Why |
|---|---|
| delegate-work | Required by `SMART-RULE-0024` |
| learning-maintenance | Required by `SMART-RULE-0028` |
| manage-credentials | The vault every credentialed skill uses |
| problem-recovery | Required by `SMART-RULE-0028` |
| product-development | Required by `SMART-RULE-0016` (the one change from "everything else moves") |
| raw-file-ingestion | Required by CONTRACT §11 |
| repository-preflight | The validator (CONTRACT §13.2, §15) |
| skill-exchange | Proposed; how skills move between brains and libraries |
| tasks | Required by CONTRACT §9 |

| Moves to the library (`/library/skills/`) | Kind |
|---|---|
| abr-access | Outside system |
| crm | Way of working |
| gohighlevel-access | Outside system |
| google-workspace-access | Outside system |
| owner-board | Way of working (`tasks` uses it when installed and degrades cleanly when not) |
| railway-access | Outside system |
| ui-implementation | Way of working |
| ui-mockup | Way of working |
| xero-access | Outside system |

## Proposed wording or exact diff

### `/CONTRACT.md`

§1, first paragraph – before:

> This file is the canonical operating contract for the entire brain: the mechanics repository that holds this file, the owner's memory repository checked out beneath it at `/memory/`, and every external project repository the memory points to (section 16).

After:

> This file is the canonical operating contract for the entire brain: the mechanics repository that holds this file, the skill library checked out beneath it at `/library/`, the owner's memory repository checked out beneath it at `/memory/`, and every external project repository the memory points to (section 16).

§3.4 – heading "The three layers" becomes "The four layers", the opening sentence reads "The brain is made of four layers, each with its own repository and its own audience.", item 1 is replaced and a new item 2 inserted; items 2 and 3 become 3 and 4 unchanged. Item 1 before:

> 1. **Mechanics (this repository).** The contract, generic rules, bootstrap and onboarding files, shared skills (instructions, scripts, tests and generic external-API knowledge), templates, schemas, the raw-file system node and governance proposals about the mechanics. It holds **no personal data**: no owner name, client, contact, company, account, location or tenant identifier, email address, phone number, machine path or owner project name. Anyone could adopt it unchanged.

After:

> 1. **Mechanics (this repository).** The contract, generic rules, bootstrap and onboarding files, the core skills the brain itself depends on (a skill a `SMART-RULE` or this contract requires, or that another core skill calls), templates, schemas, the raw-file system node and governance proposals about the mechanics. It holds **no personal data**: no owner name, client, contact, company, account, location or tenant identifier, email address, phone number, machine path or owner project name. Anyone could adopt it unchanged.
> 2. **Skill library (`/library/`).** Every other reusable skill: access to an outside system, or a way of working an owner may choose. Instructions, scripts, tests and generic external-API knowledge, under the same no-personal-data condition as the mechanics. An owner uses the skills listed in `active_skills` in `/memory/OWNER.md`, and may merge skills from other libraries into their own.

The last paragraph of §3.4 – before: "When an item could sit in either of the first two layers, it belongs in memory unless …". After: "When an item could sit in memory or in a shareable layer (the mechanics or the skill library), it belongs in memory unless …" (rest unchanged).

§3.5, the layout block gains one line after the mechanics line:

```text
<brain_root>/library/          skill library repository; listed in the mechanics repository's .gitignore
```

and one bullet after the repository-root-path bullet:

> - A library skill is addressed as `/library/skills/<skill>/`. A core skill stays `/shared/skills/<skill>/`. Owner configuration, data and notes for either live at `/memory/skills/<skill>/`. A script that needs another skill finds it from the brain root, never by a path relative to its own folder, so a skill works whichever repository holds it.

and the last bullet – before: "The mechanics repository never commits anything under `/memory/`, and the memory repository never carries a copy of a mechanics file." After: "The mechanics repository never commits anything under `/memory/` or `/library/`; the memory repository never carries a copy of a mechanics or library file; the library never carries a copy of a mechanics file." (rest unchanged).

The §3.5 bullet on owner configuration keeps its wording with `/shared/skills/<skill>/` replaced by "a shared or library skill".

§10.1 – before: "Place it in `/shared/skills/` when multiple nodes can use the general capability." After: "Place it in the skill library (`/library/skills/`) when multiple nodes can use the general capability, and in `/shared/skills/` only when the brain itself depends on it (section 3.4)."

§12 – before: "Store reusable capabilities and schemas under `/shared/`." After: "Store schemas, templates and core skills under `/shared/`, and every other reusable skill in the skill library." And "the general skill remains canonical under `/shared/skills/`" becomes "the general skill remains canonical under `/shared/skills/` or `/library/skills/`". The §12 example path `/shared/skills/xero-access` and the §8.3 examples become `/library/skills/xero-access`.

§15 – "no personal data has entered the mechanics repository (section 3.4)" becomes "no personal data has entered the mechanics repository or the skill library (section 3.4)"; the manifest check lists `/library/repository-manifest.json` beside the other two.

§16.3 – "validates the mechanics repository and, when present, `/memory/`" becomes "validates the mechanics repository and, when present, `/library/` and `/memory/`".

### `/RULES.md`

`SMART-RULE-0029` keeps its identifier; its index row becomes "Four layers: mechanics, skill library, memory and project repositories | `/CONTRACT.md` §3.4–§3.6".

`SMART-RULE-0013`, first bullet – before: "Every shared `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, …". After: "Every `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, …" (rest unchanged).

### Other files

`/ONBOARDING_AGENT.md`, `/README.md`, `/SETUP.md`, `/shared/skills/README.md`: the skill tables split into core and library; SETUP clones the library beside memory and offers its skills in the existing menu. `/.gitignore` gains `library/`. The memory skeleton's starter contact node moves with `crm` and is installed when `crm` is chosen. The validator learns the library layer.

## Reason

- The smarts becomes small and stable: what every brain needs, and nothing an owner must ignore.
- Optional skills become shareable on their own terms, and other people's skills have a place to
  land without becoming governance for everyone.
- The owner's own data never moves: it is in memory today and stays there.

## Scope and behavioural consequences

- **Agents:** read the same contract; resolve library skills at `/library/skills/`.
- **The owner:** one more repository to clone (SETUP does it) and one more to push; nothing else
  changes in daily use.
- **Other owners of these mechanics:** a breaking change to paths – hence contract `2.0.0` – with
  the migration below.

## Risks and conflicts

- **Broken paths.** About 190 memory files, 47 mechanics files and six cross-skill imports name
  `/shared/skills/<moving skill>/`. Mitigated by a mechanical rename in one commit per
  repository, the validator's reference check, and every skill's test suite run from its new home.
- **A library without the smarts.** Library skills depend on core skills (the vault above all);
  the library README states that it needs a brain around it.
- **History.** Moving files to a new repository loses `git log` for them unless extracted with
  history. Mitigated: extract with `git filter-repo` when available, otherwise record the source
  commit in the library's first commit.
- **Conflicts with open proposals.** `PROPOSAL-skill-exchange` speaks of "shared skills"; if both
  are accepted, its wording is updated to "core or library skills" in the same change.

## Migration

1. Create the library repository on GitHub under the owner's account, with the same visibility as
   the smarts (owner confirms the name and visibility at acceptance; suggested
   `brain-skills`), and check it out at `<brain_root>/library/`.
2. Move the nine skills, with history where possible; add a README, manifest and `.gitignore`.
3. Rewrite the cross-skill imports to resolve from the brain root (six places), and every
   `/shared/skills/<moved skill>` reference in the smarts and memory to `/library/skills/<skill>`.
4. Apply the contract and rule diffs above; set `contract_version: 2.0.0` in every manifest.
5. Update SETUP, README, onboarding and the skeleton; run every moved skill's tests, the
   validator and the personal-data check on both shareable repositories.

## Rollback

Revert the commits in each repository; delete or archive the library repository. No owner data
moves, so none is at risk.

## Validation

- The validator passes on all three repositories, with no broken references.
- Every moved skill's test suite passes from `/library/skills/`.
- The personal-data check reports no hits in the smarts or the library.
- A fresh SETUP dry run in a sandbox clones the library and installs one chosen skill.

## Acceptance

Not yet requested. Ask one direct question that identifies `PROPOSAL-skill-library`, including
the repository name and visibility. Do not treat silence, adjacent approval or general agreement
as acceptance.

## Implementation record

None.
