---
id: delegation-run-template
title: Delegation run template
type: template
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Run: {{TITLE}}

The script `/shared/skills/delegate-work/scripts/delegation.py new-run` writes the front matter
and substitutes the placeholders below. Do not copy this file by hand.

## Why parallel

{{WHY_PARALLEL}}

## Synthesis

The conductor fills this section after every worker has reported: what was accepted, what was
rejected and why, where each durable outcome was routed (knowledge, state, log, task), and the
`LOG.md` entry that records the run.
