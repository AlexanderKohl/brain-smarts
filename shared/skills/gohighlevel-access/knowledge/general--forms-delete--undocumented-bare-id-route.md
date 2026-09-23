---
id: ghl-general-forms-delete-undocumented-bare-id-route
title: Forms can be hard-deleted with DELETE /forms/{formId}; no locationId anywhere, and the response reports snapshot origin
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: DELETE /forms/{formId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /shared/skills/gohighlevel-access/knowledge/general--forms-list--type-param-folder-records-and-invalid-value.md
created: 2026-09-15T15:30:00+10:00
updated: 2026-09-23T14:45:16+10:00
---

# Form hard delete: bare id, no location anywhere

## Behaviour

```
DELETE /forms/{formId}
  headers: Location OAuth token, default Version (2021-07-28)
  no locationId in the path, query string or body
  -> 200 {"source":"snapshot","locationId":"<loc>","deleted":true,
          "originId":"<id>","versionHistory":[{...}]}
```

The form disappears from `GET /forms/?locationId=...` immediately. The route is not in the
documented Forms API, which exposes only listing and submissions.

Two things worth noting in the response:

- It echoes a `locationId` the caller never supplied, resolved from the token. So the location
  scope is implicit in the Location token alone – a wrong token silently targets a different
  subaccount with no path segment to cross-check against. Verify the location before calling.
- `"source": "snapshot"` and `originId` show the form arrived by snapshot push and identify its
  origin record. Deleting the local copy does not touch the origin in the snapshot.

Contrast with the sibling email-template resource, where the working delete needs the location
as a path segment (`DELETE /emails/builder/{locationId}/{templateId}`) and the bare-id form
404s. The two resources take opposite shapes; do not carry one over to the other.

## Why it's non-obvious

Nothing documents form deletion at all, so the reasonable prior is that it is not exposed and
that forms must be removed in the UI. Having just learned that email templates need an explicit
`{locationId}` path segment, the natural first guess for forms is the same shape – which is the
wrong one here.

## Evidence

Confirmed live 2026-09-15 in `Example Co Master` (`loc_EXAMPLE_02`). A candidate ladder
was probed against one designated target form, `DELETE Example Form
V2` (`id_EXAMPLE_01`); the first candidate, the bare-id route, returned the 200 body
above. A re-list confirmed the location went from 24 forms to 23, the target absent, its
non-prefixed twin and all four folders untouched.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Forms, via a Location OAuth token derived from the connected agency grant. Not tested for
surveys (`/surveys/`), and not tested for form folders – folder records share the form response
shape (see the forms-list entry) but were not passed to this route.
