---
id: agents-entry
title: Agent Entry Point
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-06T11:10:00+10:00
updated: 2026-10-01T11:02:10+10:00
owner: brain-owner
---

# Agent entry point

**Start here:** [`/BOOTSTRAP.md`](./BOOTSTRAP.md) – choose the bootstrap tier first; a session that will write reads [`/CORE.md`](./CORE.md) and [`/CORE-RULES.md`](./CORE-RULES.md), with the host's file-reading tool (for example Read), not a shell command such as `cat`: a shell may show only the start of a long file.

The canonical rules are [`/CONTRACT.md`](./CONTRACT.md) and [`/RULES.md`](./RULES.md); `/CORE.md` and `/CORE-RULES.md` are generated from them.

Then:

1. The owner profile `/memory/OWNER.md`, the owner-layer rules `/memory/RULES.md`, and inherited `RULES.md` down to the active node
2. Active node `README.md`, `STATE.md`, and relevant dependencies
3. The owner's own notes in `/memory/ONBOARDING_OWNER.md`; the skill indexes are `/shared/skills/README.md` and `/library/skills/README.md`

This file is a cross-tool pointer. It does not replace the contract.
