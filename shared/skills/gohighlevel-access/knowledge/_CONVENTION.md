---
id: gohighlevel-knowledge-convention
title: Knowledge base convention for this skill
type: api_knowledge_convention
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-08-24T21:30:00+10:00
updated: 2026-09-23T18:00:00+10:00
---

# Knowledge base convention

One file per confirmed or hypothesised piece of non-obvious API behaviour.
Copy `/shared/templates/api-knowledge-entry.template.md` for a new entry.

## Filename

`<object_type>--<field_or_topic>--<short-slug>.md` – lowercase,
hyphen-separated segments, double-hyphen between the three parts. Use
`general` as `object_type` for a fact that isn't scoped to one object type
(a client/transport behaviour, an OAuth/scope rule, a cross-object field
convention). Object types used in this folder: `contact`, `opportunity`,
`business`, `custom_object`, `task`, `general`.

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

## Sources

Entries are learnt from live use of the API, not derived speculatively:
live probes, production or staging logs, traffic recordings of the
HighLevel interface, and root-cause investigations of real failures.
Each entry's Evidence section names its own source; project logs,
commit references and other owner-specific provenance belong in the
memory layer (see below), not here.

## Owner provenance

Entries here are generic: sub-account names, record ids and project paths
are fictional placeholders (`Example Co`, `loc_EXAMPLE_01`, `id_EXAMPLE_01`,
`<uuid-01>`). Where an entry was learnt on the owner's own accounts, the
original with its real identifiers and source paths is kept in the memory
layer at `/memory/skills/gohighlevel-access/knowledge/<same filename>`,
which carries a `generic_version:` pointer back here. A new entry follows
the same split: the learning here, the owner's evidence there.

The entry here names no `/memory/` path in its front matter, because another owner's memory
does not have that file; its Evidence section says instead that it was observed on a live account
and the owner's record is kept in their memory. Preflight rejects a mechanics metadata reference
into `/memory/` that the memory skeleton does not provide.
