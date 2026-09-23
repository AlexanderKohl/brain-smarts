---
id: template-credential-management-readme
title: Credential Management
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
  - /shared/skills/manage-credentials
---

# Credential Management

Read `/CONTRACT.md` first.

The owner's credential node. It holds the non-secret credential registry and, ignored by Git,
the encrypted vault that `/shared/skills/manage-credentials/` operates. Every credentialed skill
(`abr-access`, `google-workspace-access`, `railway-access`, `xero-access` and others) records its
vault entry and field names in the registry here. No credential value is ever stored in this node
except as authenticated ciphertext inside `data/credentials.vault`.

#### Folders

##### `data/`

Contains `credential-registry.json`, the non-secret registry of vault entries, field names,
providers and consumers, and the locally ignored `credentials.vault`.
