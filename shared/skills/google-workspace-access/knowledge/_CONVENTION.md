---
id: google-workspace-knowledge-convention
title: Knowledge base convention for this skill
type: api_knowledge_convention
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-09-12T14:50:00+10:00
updated: 2026-09-12T14:50:00+10:00
---

# Knowledge base convention

One file per confirmed or hypothesised piece of non-obvious API behaviour.
Copy `/shared/templates/api-knowledge-entry.template.md` for a new entry.

## Filename

`<object_type>--<field_or_topic>--<short-slug>.md` – lowercase,
hyphen-separated segments, double-hyphen between the three parts. Use
`general` as `object_type` for a fact that isn't scoped to one object type
(a client/transport behaviour, an OAuth/scope rule, a cross-object field
convention). Object types used in this folder: `oauth`, `calendar`,
`contact`, `gmail`, `general`.

## Status lifecycle

`pending` -> `confirmed` | `refuted`
`confirmed` -> `deprecated`

See root `/RULES.md` for when to create, promote, refute or deprecate an
entry.

## Finding entries

No hand-maintained index – use `Glob`/`Grep` directly against this folder:

- By object type: `Glob "oauth--*"`
- By field type: `Grep "field_type: refresh_token"`
- By endpoint: `Grep "endpoint: POST /token"`
- By status: `Grep "status: refuted"`
