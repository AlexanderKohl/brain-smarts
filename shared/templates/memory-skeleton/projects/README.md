---
id: template-projects-readme
title: Projects
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
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

##### `contacts/`

Contains the owner's contact register: one file per person, organisation, newsletter sender or
system, and one file per identity the owner communicates as. Its rules apply while `crm` is in
`active_skills` (`/shared/skills/crm/`).
