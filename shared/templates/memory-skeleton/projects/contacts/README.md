---
id: template-contacts-readme
title: Contacts
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: project
status: active
parent: /memory/projects
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
skill_refs:
  - /shared/skills/crm
---

# Contacts

Read `/CONTRACT.md` first.

## Purpose

The owner's contact register: one Markdown file per person, organisation, newsletter sender or
system the owner deals with, and one file per identity the owner communicates as. Agents read the
matching contact before drafting a reply, scheduling or creating a contact-linked task. Model and
procedures: `/shared/skills/crm/SKILL.md`.

## Navigation

- `RULES.md`: when a contact is created or updated, and how a reply identity is chosen
- `STATE.md`: current position and open work
- `KNOWLEDGE.md`: persona catalogue and durable principles
- `LOG.md`: structural decisions (new personas, rule changes, bulk imports and merges)

#### Folders

##### `contacts/`

Contains one file per remote party, `contact-<slug>.md`, copied from `_TEMPLATE.md`. Canonical
for relationship memory.

##### `data/`

Contains non-secret configuration such as `google-accounts.json` (sending account aliases and the
vault entry each uses). Created when the first account is registered. Never a secret.

##### `personas/`

Contains one file per owner identity, `persona-<key>.md`, copied from `_TEMPLATE.md`. Contacts
refer to a persona by its key only.
