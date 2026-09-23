---
id: RULE-2026-0046
title: Three-layer brain – mechanics, memory and project repositories
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-09-23T12:00:00+10:00
updated: 2026-09-23T12:00:00+10:00
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 0.9.0
new_contract_version: 1.0.0
target_files:
  - /CONTRACT.md
  - /RULES.md
  - /BOOTSTRAP.md
  - /AGENTS.md
  - /README.md
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
  - /shared/templates/memory-skeleton/RULES.md
  - /shared/templates/memory-skeleton/governance/README.md
  - /shared/templates/memory-skeleton/governance/proposals/README.md
  - /shared/templates/memory-skeleton/projects/brain-development/RULES.md
  - /shared/templates/memory-skeleton/tasks/RULES.md
  - /governance/README.md
  - /memory/RULES.md
  - /SETUP.md
  - /SEED_PROMPT.md
  - /shared/templates/host-pointers/
  - /shared/templates/memory-skeleton/OWNER.md
---

# RULE-2026-0046 – Three-layer brain

Status `draft` until it is presented to the owner; set `proposed` at that moment. Nothing in
this proposal is active, and the single-repository brain on contract `0.9.0` stays live until
the owner accepts it and the cutover below is complete.

## Summary

What will be different, in plain language:

- **One brain becomes three kinds of repository.** The mechanics – the contract, generic
  rules, bootstrap and onboarding, shared skills, templates, schemas, the raw-file system node
  and the mechanics proposals – move to a new private repository, `brain-smarts`. Everything
  about the owner – tasks, projects, contacts, raw files, sources, outbox, boards, the
  brain-wide state, log and knowledge – moves to a second private repository, `brain-memory`.
  Large bodies of work with their own lifecycle live in their own project repositories.
- **Agents see one tree.** `brain-smarts` is checked out at the brain root and `brain-memory`
  inside it at `memory/`, ignored by the mechanics repository. Owner content is addressed as
  `/memory/...`; the path rule is simply "what was at `/X` and belongs to the owner is now at
  `/memory/X`".
- **The mechanics carry no personal data.** They say "the owner" and set `owner: brain-owner`;
  concrete values (name, timezone, local paths, GitHub account, usual host) are read from a new
  owner profile, `/memory/OWNER.md`.
- **A new rule layer.** Rules inherit `/CONTRACT.md` -> `/RULES.md` (generic) ->
  `/memory/RULES.md` (the owner's own preferences, always read) -> node rules. One root rule
  moves to the owner layer: `RULE-2026-0042` (en dash, never em dash), because it is a
  preference rather than a mechanism. `RULE-2026-0013` stops naming a machine path and reads
  `brain_root` from the owner profile; `RULE-2026-0028` says "the owner decides" instead of a
  name. No rule is weakened or dropped.
- **A test for where new work lives.** Start in memory; give work its own repository when it
  has code that is built, run or deployed, other people, its own releases, more than a few
  hundred files or large binaries, different confidentiality, or independent value. The
  memory then keeps a small pointer node, and the project's own node files live in the
  repository's `brain/` folder so collaborators receive them.
- **Proposals move.** Mechanics proposals move from `/projects/brain-development/proposals/`
  to `/governance/proposals/`; owner-layer proposals go to `/memory/governance/proposals/`.
- **The validator understands both repositories.** Preflight validates the mechanics and,
  when present, the memory checkout; `/memory/` references resolve into it; a missing memory
  is a warning; each repository gets its own manifest, and the mechanics manifest never names
  a memory path.
- **A skeleton for a new owner.** `/shared/templates/memory-skeleton/` is the minimal memory
  another person starts from.

## Current problem

1. The brain mixes two things with different audiences in one repository: mechanisms any owner
   could reuse, and one owner's private records. The mechanics cannot be shared, published or
   reused by anyone else without first scrubbing thousands of files by hand, and every
   improvement to them is buried among personal commits.
2. Large bodies of work – software products, campaigns – live as project nodes inside the
   brain or as sibling repositories with no rule saying which. There is no test for when work
   deserves its own repository and no defined link between such a repository and the brain,
   so collaborators cannot receive a project's state, rules and knowledge without the whole
   brain.
3. Machine paths and the owner's name are written into governance (`RULE-2026-0013` names the
   repository path; `RULE-2026-0028` names the owner), so the governance itself is not portable.
4. The brain's size and history make every agent search wider and every commit riskier than
   the task needs; the pre-commit hook already exists because sweeps cross unrelated territory.

## Current wording

The live files at snapshot commit `2ee38c4` of the single-repository brain: `/CONTRACT.md`
(`0.9.0`), `/RULES.md`, `/BOOTSTRAP.md`, `/AGENTS.md`, `/README.md`, `/ONBOARDING_AGENT.md`,
`/shared/skills/repository-preflight/`, `/shared/templates/`, `/shared/schemas/`, `/tasks/RULES.md`.

## Proposed wording or exact diff

The proposed wording is the complete candidate files in the `brain-smarts` candidate tree at
the paths in `target_files`, plus the unprotected files built beside them. Present the exact
diff to the owner with, from the brain root of each checkout:

```bash
git diff --no-index --stat <old-brain>/CONTRACT.md <candidate>/CONTRACT.md
git diff --no-index <old-brain>/CONTRACT.md <candidate>/CONTRACT.md
```

and the same for each protected path. The changes by file:

| File | Change |
|---|---|
| `/AGENTS.md`, `/BOOTSTRAP.md`, `/CLAUDE.md` | Bootstrap reads `/memory/OWNER.md` and `/memory/RULES.md` after `/RULES.md`; a path inside `/memory/` finds the contract one level up; missing memory means mechanics-only work; project repositories bootstrap from the brain root and read `brain/` as the active node |
| `/CONTRACT.md` | `contract_version` `0.9.0` -> `1.0.0` (major: breaking layout change) and a candidate banner. §1: the contract governs all three layers; full bootstrap adds the owner profile and owner layer; step 6 for an absent memory; rule inheritance order. New §3.4 (three layers, and the rule that owner specifics never enter the mechanics), §3.5 (runtime layout, `/memory/X` path rule, `/memory/skills/<skill>/`, `/temp/`), §3.6 (owner profile and `brain-owner`). §5.4, §8, §9, §11, §12, §15 paths move to `/memory/...`. §5.6 names the owner layer as a governance level. §6 adds "which layer". New §7.1 (in memory or its own repository – the decision rule). §10.1 owner-wide skill configuration in `/memory/skills/`. §13.2: `/memory/RULES.md` and node rules in memory and project repositories are protected; proposals are stored per layer (`/governance/proposals/`, `/memory/governance/proposals/`, a project's `brain/proposals/`). §14: read the owner profile; each repository commits separately. §15: a manifest per repository; no personal data in the mechanics. New §16 (external project repositories: pointer node, `brain/` folder, validation and commits). Every other section keeps its substance |
| `/memory/RULES.md` | New owner layer, id `owner-rules`, inheriting `/RULES.md`; holds `RULE-2026-0042` verbatim except that its scope names all three layers |
| `/ONBOARDING_AGENT.md` | Generic mechanics only; the Google Workspace and contact-register section, account aliases, organisation links, the efficiency baseline and the credential registry path move to `/memory/ONBOARDING_OWNER.md`. List numbering repaired (the live file has two items 12 and two items 13), and the skill table completed and ordered |
| `/README.md` | Describes the mechanics layer, `memory/` as a separate ignored repository, `governance/`, and how to set up a memory |
| `/RULES.md` | Generic rules only, IDs unchanged. `RULE-2026-0042` moves to `/memory/RULES.md`. `RULE-2026-0013` reads `brain_root` from `/memory/OWNER.md`. `RULE-2026-0028`: "the owner decides". `RULE-2026-0032` and `RULE-2026-0037`: `/tasks/` and `/projects/brain-development/` become `/memory/...`. Two contract restatements added (owner skill configuration; no personal data in the mechanics) |
| `/shared/skills/repository-preflight/` | Validates both repositories as described in the summary; adds a test suite of fictional two-repository fixtures; keeps accepting the single-repository layout so it can run on the live brain unchanged |
| `/shared/templates/memory-skeleton/` | New: the minimal memory for a new owner, including owner-layer, task and node `RULES.md` templates |
| `/governance/README.md` | New: the mechanics governance folder |

Unprotected files built with it (listed so the owner sees the whole change): `.gitignore`
(ignores `memory/`; owner-specific ignore patterns move to the memory repository),
`.githooks/pre-commit` (refuses `memory/` paths; the sweep tripwire now separates governance
from everything else), `/shared/README.md`, `/shared/skills/README.md`,
`/shared/schemas/*`, `/shared/templates/README.md`,
`/shared/templates/project-pointer-README.template.md`, `/systems/raw-file-management/`
(per-file ingestion entries move to `/memory/systems/raw-file-management/LOG.md`),
`/governance/proposals/` (mechanics proposals, generalised), `/memory/OWNER.md`,
`/memory/ONBOARDING_OWNER.md`.

## Reason

- **Reuse.** The mechanics become something another person, or a future business, can adopt
  unchanged, and improvements to them are reviewable on their own.
- **Privacy by construction.** A repository that holds no personal data cannot leak it; the
  owner's records sit in a repository whose only audience is the owner.
- **Collaboration.** A project repository carries its own node files, so a collaborator gets
  the state, rules and knowledge they need without seeing the brain.
- **Focus.** Smaller repositories mean narrower searches and commits that cannot sweep across
  unrelated territory.
- **Portable governance.** Values that differ per owner or machine are read from one profile
  instead of being written into rules.

## Scope and behavioural consequences

- Every agent session: bootstrap reads two more files (`/memory/OWNER.md`, `/memory/RULES.md`).
- Every durable write: the agent decides the layer (CONTRACT §6 item 6) and commits in the
  repository that owns the file. A task that changes mechanics and memory makes two commits
  and reports two Git accounting lines (`RULE-2026-0023`).
- Every owner path in conversation, tasks and records gains the `/memory/` prefix.
- Shared skills that write owner data (raw-file ingestion, contact-register work, the owner
  board, delegation run records) must write under `/memory/` or `/memory/skills/<skill>/`. The
  skill changes are part of the same candidate build (separate work packets) and are validated
  before cutover.
- New work is placed with the §7.1 test, and its placement is logged.
- No external system, credential, vault or account changes. The vault stays where it is.

## Risks and conflicts

1. **Changes made in the old brain after the snapshot.** The candidate was built from commit
   `2ee38c4`. Work continues in the live brain until cutover, so every commit after the
   snapshot must be carried across, or it is lost when the old repository is archived. Mitigation:
   the re-sync step in Migration, run inside a declared freeze, with a check that the list of
   post-snapshot paths is empty of unhandled entries before the old brain is archived.
2. **Missed personal data in the mechanics.** A scrub check runs over the whole mechanics tree
   against a denylist built from the brain's own contacts and projects, and the validator
   warns on any mechanics `owner` value other than `brain-owner`. Neither can prove absence in
   free prose. Mitigation: the owner reviews the mechanics repository before its first push,
   and it stays private.
3. **Duplicate IDs across the two repositories.** Mechanics proposals exist in the mechanics
   repository; a live copy in memory would duplicate their IDs. The originals are kept in the
   memory repository's history only. The validator reports any duplicate across the two.
4. **Broken references.** Every `/X` owner path must become `/memory/X`. The validator
   resolves `/memory/` references into the checkout and fails on any that do not resolve.
5. **Host configuration that names the old path.** Host settings, per-project agent memory
   keyed by the folder name, logon tasks (the vault tray), Cursor hooks, the AI session log
   listener's repository filter, scheduled tasks, and documents in project repositories may
   name `C:`-drive paths of the old brain. Mitigation: a search for the old path across host
   configuration and sibling repositories is part of the cutover, and the host's per-project
   memory is copied to the new folder's entry.
6. **Two repositories drift.** A mechanics change that needs a matching memory change could be
   committed in one and not the other. Mitigation: the validator runs across both, and the
   contract requires both commits before the report.
7. **Contract conflict.** None with accepted rules: every rule keeps its ID and substance.
   `RULE-2026-0042` changes home and scope wording only. Pending proposals `RULE-2026-0044` and
   `RULE-2026-0045` target `/RULES.md` and will need their paths re-read against the split
   layout when they are next presented.

## Migration

The cutover, in order, after acceptance:

1. **Declare a freeze** on the live brain: no agent writes to it from this point. Record the
   freeze time in its `LOG.md` (the last commit to the old brain).
2. **Re-sync.** In the old brain run `git log --name-status 2ee38c4..HEAD`. For every path
   listed: a mechanics path is applied to the candidate `brain-smarts` tree with the same
   scrub; an owner path is applied to `brain-memory` at `/memory/X`; a path that holds both is
   split. Record each path and its disposition in a re-sync table in the memory's
   `projects/brain-development/LOG.md`. The step is complete when every listed path has a row.
3. **Validate.** From the new brain root, with memory checked out: the preflight validator
   passes (`--write-manifest` writes both manifests), its tests pass, and the scrub check over
   the mechanics repository reports zero hits.
4. **Owner review** of the mechanics repository, then create the two private GitHub
   repositories under the owner's account, push, and record the commits.
5. **Switch hosts** to the new brain root: host project settings and per-project memory, logon
   and scheduled tasks, Cursor hooks, the session-log listener; search sibling project
   repositories for the old path and update them in their own commits.
6. **Archive** the old repository on GitHub (read-only) and add a final commit to it that
   points to the two new repositories. Do not delete it.
7. **Record acceptance and implementation** here: `accepted_by`, `accepted_at`,
   `implemented_at`, the snapshot and final commits, and the validation results; set the
   contract's `status` to `active` and remove its candidate banner in the same commit.

## Rollback

- **Before step 6:** discard the new repositories and continue in the old brain, which was only
  frozen, not changed. Record the rollback in its `LOG.md` and mark this proposal `rejected`
  or `reverted`.
- **After step 6:** unarchive the old repository and replay onto it, by the same path rule in
  reverse, every commit made to the two new repositories since cutover; then return the hosts
  to the old path. The new repositories are archived, not deleted.

## Validation

- The preflight validator's test suite (`shared/skills/repository-preflight/tests/`) passes: it
  covers mechanics-only and two-repository brains, `/memory/` reference resolution, memory
  absent as a warning, raw-evidence exemption in memory, duplicate IDs across repositories,
  task-state enumeration in `/memory/tasks/`, separate manifests with no memory path in the
  mechanics manifest, the owner tripwire, and governance coverage in each repository.
- The validator still passes on the live single-repository brain unchanged (it keeps
  accepting `/tasks/`, `/raw/` and `/projects/brain-development/proposals/`).
- The assembled new brain passes the validator with memory present and with memory absent.
- The scrub check over the mechanics repository reports zero hits, with every allow-listed
  string justified.
- After cutover, one ordinary session – a task created, a raw file ingested, a mechanics fix
  committed – runs end to end and produces commits in the right repositories.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal, after presenting the
summary, the exact diffs and the cutover plan. Do not treat silence, adjacent approval or
general agreement as acceptance.

## Implementation record

None. The candidate repositories are built but not active.

## Amendment A1 – guided setup (2026-09-23T14:10:00+10:00)

Adds `/SETUP.md` (resumable guided setup for a new owner), `/SEED_PROMPT.md`, the host pointer and permission-settings templates under `/shared/templates/host-pointers/`, and the `active_skills:` field in the skeleton `OWNER.md`. They determine how agents locate the contract and which skills an owner switches on, so they are included in this proposal's target files. Settings keys not confirmed offline are marked `verify against current host docs` in `/SETUP.md` §11. Status unchanged: draft, pending owner acceptance.
