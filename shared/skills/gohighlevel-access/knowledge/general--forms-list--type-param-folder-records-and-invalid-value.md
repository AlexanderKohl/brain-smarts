---
id: ghl-general-forms-list-type-param-semantics
title: GET /forms/ type=folder returns folder records; an invalid type value returns forms plus folders
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /forms/
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-09
verified: 2026-09-09
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--forms-list--type-param-folder-records-and-invalid-value.md
created: 2026-09-09T17:20:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# `GET /forms/` `type` parameter: folder records, and an unfiltered invalid value

## Behaviour

`GET https://services.leadconnectorhq.com/forms/?locationId=<id>&limit=50&skip=0`
returns `{"forms": [...], "total": N, "traceId": "..."}`. Every item – form or
folder – has the identical minimal shape `{"id", "locationId", "name"}`. There
is no `type`, `parentId` or `folderId` discriminator on the record, so the only
way to tell a folder from a form is to compare ID sets across two calls.

`type` behaves as follows:

- omitted → forms only
- `type=form` → forms only (identical to omitted)
- `type=folder` → **folder records**, in the same form-shaped envelope
- `type=folders` (or any unrecognised value) → **no filter applied**: forms
  *and* folders in one list, folders first

Measured 2026-09-09 across two subaccounts:

| location | plain | `type=form` | `type=folder` | `type=folders` |
|---|---|---|---|---|
| `Example Co Master` `loc_EXAMPLE_02` | 23 | 23 | 4 | 27 |
| `Example Co (Staging)` `loc_EXAMPLE_01` | 14 | 14 | 4 | 14 |

Master's four `type=folder` IDs appear nowhere in its 23-form list, and
`23 + 4 = 27` matches the unfiltered count – they are real, distinct folders
(`003. List Cleanup/MGMT`, `007. Calendar Automations`,
`008. Inbound Messaging`, `011. Form Automations`).

`GET /forms/folders` is not a route: it returns HTTP 400
`{"message":"Form does not exist"}` because `folders` is parsed as a form ID.
`includeFolders` is rejected with HTTP 422 `"property includeFolders should not
exist"`. `parentId=root` is accepted but returns `total: 0`.

## Why it's non-obvious

Nothing in the response distinguishes a folder from a form, so a caller that
merges the two lists silently treats folders as forms. The unfiltered
behaviour of an invalid `type` is the useful part – it is the only single call
that returns both – but it is reached by passing a *wrong* value, which no
documentation would suggest and which a future API tightening could remove.

`limit` is capped at 50 on `GET /surveys/` (HTTP 422 `"limit must not be
greater than 50"`); `GET /forms/` accepted `limit=100`. Use 50 for both.

## Evidence

Live read-only probes of all four `type` variants against both subaccounts in
one session, compared by ID set rather than by count, plus the three negative
route/param probes above. `confirmed` for the folder-listing behaviour: the
disjoint ID sets and the `23 + 4 = 27` arithmetic on Master prove it directly.

**Open anomaly – do not assume `type=folder` implies folders exist.** Staging
has *zero* folder records (its unfiltered count equals its form count, 14), yet
`type=folder` still returned four items, and all four are real forms present in
its own form list: `New Quote Request` `id_EXAMPLE_01`,
`008. Contact Us Form (Google Ads) - no address` `id_EXAMPLE_02`,
`011. Pre-Install Checklist Form - Copy` `id_EXAMPLE_03`,
`Event Lead Capture` `id_EXAMPLE_04`. Those four appear to carry a
stored folder-ish marker despite being forms. Unexplained; not reproduced
elsewhere. Verify a `type=folder` result against the form list before treating
its items as folders.

## Applies to

`GET /forms/` on a Location token. `GET /surveys/` uses the same envelope
(`{"surveys": [...], "total": N}`) and honours `type=folder` the same way –
Master returned one survey folder, `B-009. Review Automations`
`id_EXAMPLE_05`, distinct from its one survey. Do not assume other list
endpoints accept `type`.

Supersedes the refuted hypothesis in
[`general--forms-list--type-folder-returns-unfoldered-subset.md`](general--forms-list--type-folder-returns-unfoldered-subset.md).
