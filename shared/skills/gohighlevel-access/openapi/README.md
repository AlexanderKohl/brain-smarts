---
id: gohighlevel-access-openapi-readme
title: HighLevel OpenAPI Reference Snapshots
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: reference_library
status: active
parent: /shared/skills/gohighlevel-access
created: 2026-08-06T09:33:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
skill_refs:
  - /shared/skills/gohighlevel-access
---

# HighLevel OpenAPI Reference Snapshots

Read `/shared/skills/gohighlevel-access/SKILL.md` first.

These JSON files are downloaded HighLevel Marketplace OpenAPI 3.0 snapshots used to ground API request shapes for the shared HighLevel skill (especially custom object data-plane setup). They are **API documentation**, not live sub-account data.

They are kept next to the skill that consumes them so any agent can find them.

| File | Use |
|---|---|
| `custom-fields-v3.json` | Custom Fields V2 / `CreateCustomFieldsDTO` (Version `v3`) |
| `objects-v3.json` | Custom Objects schemas and records |
| `associations-v3.json` | Associations and relations |
| `contacts-v3.json` | Contacts and contact custom fields |
| `users-v3.json` | Users search/create/update |

Project-specific live exports and verify results belong under the requesting project (memory layer or its own repository), not here.

#### Folders

No immediate child folders. OpenAPI snapshot files are stored directly in this directory.
