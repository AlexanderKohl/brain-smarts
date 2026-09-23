---
id: template-credential-management-data-readme
title: Credential Management Data
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Credential Management Data

Read `/CONTRACT.md` first.

`credential-registry.json` names each vault entry, its fields, provider and consumers – never a
value. `credentials.vault`, created by `/shared/skills/manage-credentials/`, holds only
authenticated ciphertext and is ignored by Git (`*.vault` in `/memory/.gitignore`).

#### Folders

No immediate child folders exist.
