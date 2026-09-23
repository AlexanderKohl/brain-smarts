---
id: ghl-general-forms-list-type-folder-subset
title: GET /forms/ ignores type=form but type=folder returns a smaller form subset
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /forms/
status: refuted
superseded_by: null
refuted_by: ghl-general-forms-list-type-param-semantics
discovered: 2026-09-09
verified: null
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--forms-list--type-folder-returns-unfoldered-subset.md
created: 2026-09-09T16:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# GET /forms/ `type=folder` returns a subset of forms, not folders

## Behaviour

`GET https://services.leadconnectorhq.com/forms/?locationId=<id>&limit=50&skip=0`
returns `{"forms": [...], "total": N, "traceId": "..."}` where each item is
only `{"id", "locationId", "name"}` – no folder, status, created or updated
field is exposed.

The `type` query parameter changes the result set but never the item shape:

- omitted → `total: 14` (all forms)
- `type=form` → `total: 14` (identical to omitted)
- `type=folder` → `total: 4`, still form objects with form names, **not**
  folder objects

Observed against `Example Co (Staging)` (`loc_EXAMPLE_01`) on
2026-09-09. The four returned under `type=folder` were `New Quote Request`,
`008. Contact Us Form (Google Ads) - no address`,
`011. Pre-Install Checklist Form - Copy` and `Event Lead Capture`.

`limit` is capped at 50 on `GET /surveys/` (HTTP 422
`"limit must not be greater than 50"`), while `GET /forms/` accepted
`limit=100` without error. Use 50 for both.

## Why it's non-obvious

The parameter name implies `type=folder` enumerates folders so a caller can
map forms to folders. It does not: it returns form records, and the response
carries no folder identifier at all, so form→folder membership cannot be
reconstructed from this endpoint. A caller who trusts the name will read the
4-item response as "this location has 4 folders".

## Evidence

Live read-only probe of the three variants in one session against the staging
subaccount, with `total` read back from each response. `pending`: the exact
selection rule behind the 4-item subset is inferred, not proven. The working
hypothesis is that `type=folder` returns forms that sit at the root of the
forms list rather than inside a folder – it matched the count the owner saw
in the HighLevel forms UI – but no second location has been probed and no
folder was created or moved to test it.

## Applies to

`GET /forms/` on a Location token. `GET /surveys/` uses the same envelope
(`{"surveys": [...], "total": N}`) and the same minimal item shape, but was
not probed with `type`. Do not assume other list endpoints accept `type`.

## Refuted 2026-09-09

The hypothesis that `type=folder` returns forms sitting at the root of the
folder view is **wrong**. A probe of `Example Co Master`
(`loc_EXAMPLE_02`) the same day returned four records under
`type=folder` whose IDs appear in none of its 23 forms: they are genuine
folders. `type=folder` lists folder records.

The observation that Staging returns four *forms* under `type=folder` still
stands and is now recorded as an unexplained anomaly, not as the parameter's
meaning. Staging has no folders at all. See
[`general--forms-list--type-param-folder-records-and-invalid-value.md`](general--forms-list--type-param-folder-records-and-invalid-value.md).
