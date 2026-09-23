---
id: SYSTEM-OBJECT-TOPIC-SLUG
title: One-line description of the specific behaviour
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: SYSTEM_SLUG
object_type: OBJECT_TYPE
field_type: FIELD_TYPE_OR_NULL
endpoint: METHOD /path
status: pending
superseded_by: null
refuted_by: null
discovered: YYYY-MM-DD
verified: null
source_refs: []
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---

# Title

## Behaviour

What actually happens, stated precisely – exact wire shape, exact error
string, exact field/key names. Prefer a literal request/response fragment
over a paraphrase.

## Why it's non-obvious

What the official docs say or imply instead, or why this could not have
been guessed without trial and error.

## Evidence

How this was confirmed and when: a live raw-API probe, a production log,
an official SDK example, etc. State whether this is a `pending` hypothesis
or independently `confirmed`.

Keep `source_refs` to mechanics paths. Evidence from the owner's own
accounts (project logs, raw files, real identifiers) goes in the owner's
memory copy at `/memory/skills/<skill>/knowledge/<same filename>`, which
carries a `generic_version:` pointer back here; this entry then says
"Observed on a live account; the owner's record is kept in their memory."
Preflight rejects a mechanics `source_refs` value the memory skeleton does
not provide.

## Applies to

Which object type(s)/field type(s)/endpoint(s) this is confirmed for.
State explicitly when a sibling object type or endpoint is known to behave
*differently* – do not let a future reader assume this generalises.
