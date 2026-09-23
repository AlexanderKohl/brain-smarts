---
id: template-memory-agents-entry
title: Memory Agent Entry Point
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T13:00:00+10:00
updated: 2026-09-23T18:00:00+10:00
owner: brain-owner
install_to: <BRAIN_ROOT>/memory/AGENTS.md
---

# Agent entry point

This folder is the owner's memory, a separate repository checked out inside the brain root.
Start from the contract one level up: read [`../CONTRACT.md`](../CONTRACT.md) and follow the
bootstrap it defines (see also [`../BOOTSTRAP.md`](../BOOTSTRAP.md) and
[`../AGENTS.md`](../AGENTS.md)).

This file is a pointer only (`SMART-RULE-0007`). It exists because some hosts stop looking for
entry files at the repository root, and this repository's root is not the brain root.
