---
id: templates-readme
title: Shared Templates
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Shared Templates

Read `/CONTRACT.md` first.

Copy these templates when creating a node or source record. Replace placeholders and remove metadata fields that are not useful.

Use `governance-proposal.template.md` for any proposed semantic change to protected governance. Store completed proposals under `/governance/proposals/` (mechanics governance) or `/memory/governance/proposals/` (owner-layer governance), never in the active inherited rule path (CONTRACT §13.2).

Use `project-pointer-README.template.md` for the pointer node memory keeps for a project that lives in its own repository (CONTRACT §16.1). The project's own node files inside its repository's `brain/` folder use the `node-*.template.md` files.

#### Folders

##### `memory-skeleton/`

Contains the minimal memory a new owner starts from: owner profile, owner-layer rules, brain-wide state, log and knowledge, owner onboarding, the task system with its rules and templates, and empty `governance/`, `projects/`, `raw/`, `skills/`, `sources/` and `systems/` areas. Copy the whole folder to `<brain_root>/memory/` and follow `/README.md` § Setting up a memory. Canonical template; every `id` carries a `template-` prefix so the skeleton never collides with a live memory.
