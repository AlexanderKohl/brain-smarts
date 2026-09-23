---
id: template-owner-rules
title: Owner-Layer Rules
type: rules
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
scope: brain
inherits: /RULES.md
---

# Owner-Layer Rules

Read `/CONTRACT.md` first, then `/RULES.md`.

This is the owner layer. It inherits `/CONTRACT.md` and `/RULES.md`, is always read, and applies
to the whole brain: the mechanics repository, this memory and every project repository the
owner's agents work in. Node `RULES.md` files below it inherit it.

It holds the owner's own standing preferences – rules another owner might reasonably choose
differently. Mechanisms any owner could adopt belong in `/RULES.md`. A change here is protected
governance: propose it under `/memory/governance/proposals/` and apply it only after the
owner's explicit acceptance (CONTRACT §13.2).

Owner-layer IDs in this file: none yet.
