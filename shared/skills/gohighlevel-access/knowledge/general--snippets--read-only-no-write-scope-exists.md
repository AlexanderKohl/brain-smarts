---
id: ghl-general-snippets-read-only-no-write-scope-exists
title: Snippets (GET /locations/{id}/templates) are read-only over the API; the PUT route exists but no write scope does, so renaming must happen in the UI
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET/PUT /locations/{locationId}/templates[/{templateId}]
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-28
verified: 2026-09-15
source_refs:
  - /shared/skills/gohighlevel-access/knowledge/general--email-templates--requires-version-v3-header.md
created: 2026-09-15T15:55:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Snippets are readable but not writable over the API

## Behaviour

`GET /locations/{locationId}/templates?type=sms|email|whatsapp` is the **Snippets** feature in
the HighLevel UI (Marketing > Snippets), not the Email Builder templates resource. It is
distinct from `/emails/...` and holds different records.

Reads work and are complete:

```
GET /locations/{locationId}/templates?type=sms&limit=50&skip=0
  -> {"templates":[{"id","name","type"}], "totalCount": N}
GET /locations/{locationId}/templates/{templateId}
  -> {"template":{"id","name","type","locationId","dateAdded",
                  "template":{"body","attachments":[]}}}
```

`type` must be `sms`, `email` or `whatsapp`; anything else is `422 "type must be a valid enum
value"`. `includeBody` is rejected (`422 property includeBody should not exist`) – the list
gives name/id/type only, and the body comes from the per-id read.

**Writes are impossible on the current agency grant, and appear impossible in principle:**

| attempt | result |
|---|---|
| `PUT /locations/{id}/templates/{templateId}` (full record) | `401 The token is not authorized for this scope.` |
| `PUT` with `{"name": ...}` only | `401` same |
| `PATCH /locations/{id}/templates/{templateId}` | `404 Cannot PATCH ...` – not a route |
| `POST /locations/{id}/templates` | `401` same (2026-08-28) |

The `401` (not `404`) on `PUT` proves the route exists and the block is purely the scope. The
connected agency grant carries **168 scopes** including `.readonly`/`.write` pairs for every
sibling (`locations/customFields`, `locations/customValues`, `locations/tags`,
`locations/tasks`, `emails/templates`, `invoices/template`) – but for this resource only
`locations/templates.readonly` is present. No `locations/templates.write` appears in the grant
or in HighLevel's published scope documentation, and HighLevel's own support material directs
users to rename, edit or delete snippets in the Snippets screen.

No alternate route family exists either: `/snippets/`, `/locations/{id}/snippets` and
`/templates/` are all routing-level `404`, and `/locations/{id}/templates/folders` is `400
Template does not exists.` (`folders` parsed as a template id).

**Practical consequence: any bulk snippet rename, edit or delete is a UI task.** Do not plan
API automation for it, and do not read the `401` as a fixable app-configuration problem – adding
the scope in the Marketplace app is not an available option.

## Why it's non-obvious

The resource sits at a `/locations/...` path alongside customFields, customValues, tags and
tasks, all of which have working write scopes, so a write pair looks like a safe assumption. The
`401` message says "not authorized for this scope", which reads like a fixable app-configuration
problem – request the missing scope and reauthorise – rather than what it is: a scope that does
not exist to request. The route responding `401` rather than `404` reinforces the wrong reading.
The name collision with the Email Builder template resource compounds it, since that one *is*
writable, so experience with `/emails/...` predicts a write path that is not there.

## Evidence

Confirmed live 2026-09-15 against `Example Co (Staging)` (`loc_EXAMPLE_01`), which holds
36 snippets (29 sms, 7 email). One snippet, `AI Outreach Manual - Piper`
(`id_EXAMPLE_01`), was read in full, then a rename was attempted three ways (full-record
`PUT`, name-only `PUT`, `PATCH`) with the results tabulated above. A re-read afterwards confirmed
the name and body were completely unchanged, so the failed attempts are non-destructive. Granted
scopes were enumerated from the live token. Earlier `POST` evidence is from 2026-08-28.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

The Snippets resource via a Location OAuth token derived from the connected agency grant, for
`sms` and `email` types. `whatsapp` returns an empty list in this subaccount and was not
write-tested. Unrelated to the Email Builder v2 templates under `/emails/...`, which are fully
writable.
