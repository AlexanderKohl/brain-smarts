---
id: template-projects-readme
title: Projects
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: 2026-09-23T17:41:05+10:00
owner: OWNER_SHORT_NAME
---

# Projects

Read `/CONTRACT.md` first.

Canonical project nodes for outcome-based work kept in memory, and pointer nodes for projects
that live in their own repositories. Decide which with CONTRACT §7.1; create a pointer node from
`/shared/templates/project-pointer-README.template.md`. Tasks stay canonical in
`/memory/tasks/`.

#### Folders

##### `brain-development/`

Contains the node for the owner's work on the brain itself: the active conductor and
`## Handover` (`SMART-RULE-0019`), delegation trials (`SMART-RULE-0024`) and measurements.

##### `credential-management/`

Contains the owner's credential node: the non-secret registry
`data/credential-registry.json` that every credentialed skill records its vault entry in, and the
git-ignored encrypted vault operated by `/shared/skills/manage-credentials/`.
