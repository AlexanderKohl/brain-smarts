---
id: delegation-packet-template
title: Delegation packet template
type: template
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# {{TITLE}}

The script `/shared/skills/delegate-work/scripts/delegation.py new-packet` writes the front
matter (`context_mode`, `writes`, `write_paths`, `external`, `external_target`, `model`,
`max_tool_calls`, `max_output_words`, `context_refs`) and substitutes the placeholders below.
Do not copy this file by hand.

## Objective

{{OBJECTIVE}}

## Out of scope

{{EXCLUDE}}

## Context to read

References, not copies. Read these and nothing else unless the objective requires it.

{{CONTEXT_REFS}}

## Facts verified at packet time

Command output the conductor captured when writing this packet. Trust these over any number
in the objective.

{{FACTS}}

## Fork reason

{{FORK_REASON}}

## Acceptance

{{ACCEPTANCE}}

## Worker instructions

{{WORKER_INSTRUCTIONS}}

Result file: `{{RESULT_PATH}}`
