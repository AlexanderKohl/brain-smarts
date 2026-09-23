---
id: railway-knowledge-convention
title: Knowledge base convention for this skill
type: api_knowledge_convention
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-08-31T15:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Knowledge base convention

One file per confirmed or hypothesised piece of non-obvious API behaviour.
Copy `/shared/templates/api-knowledge-entry.template.md` for a new entry.

## Filename

`<object_type>--<field_or_topic>--<short-slug>.md` – lowercase,
hyphen-separated segments, double-hyphen between the three parts. Use
`general` as `object_type` for a fact that isn't scoped to one object type
(a client/transport behaviour, an OAuth/scope rule, a cross-object field
convention).

## Status lifecycle

`pending` -> `confirmed` | `refuted`
`confirmed` -> `deprecated`

See root `/RULES.md` for when to create, promote, refute or deprecate an
entry.

## Finding entries

No hand-maintained index – use `Glob`/`Grep` directly against this folder:

- By object type: `Glob "business--*"`
- By field type: `Grep "field_type: textbox_list"`
- By endpoint: `Grep "endpoint: .*businesses/:id"`
- By status: `Grep "status: refuted"`

## Owner provenance

Entries here are generic: project, service and deployment ids and hostnames are fictional
placeholders (`<uuid-01>`, `forms.example.com`). Where an entry was learnt on the owner's own
account, the original with its real identifiers and source paths is kept in the memory layer at
`/memory/skills/railway-access/knowledge/<same filename>`, which carries a `generic_version:`
pointer back here.
