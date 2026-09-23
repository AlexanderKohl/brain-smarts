---
id: ghl-general-workflows-no-enrolment-read-surface
title: The public API exposes no way to read which contacts are in a workflow, or which workflows a contact is in
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /workflows/
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-10
verified: 2026-09-10
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--workflows--no-enrolment-read-surface.md
created: 2026-09-10T07:35:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# No workflow-enrolment read surface on the public API

> **Scope narrowed 2026-09-12.** Everything below is correct and stays `confirmed` – for the
> public API. The *internal* API used by the workflow builder does expose enrolment totals
> and per-step contact counts. See
> [workflow--enrolment--internal-api-exposes-step-counts](workflow--enrolment--internal-api-exposes-step-counts.md).
> Do not read the consequence section below as "runtime state is unreachable"; read it as
> "unreachable from a server-side integration holding a public API token".

## Behaviour

`GET https://services.leadconnectorhq.com/workflows/?locationId=<id>` returns the
workflow **catalogue only** – `id`, `name`, `status`, `version`, `createdAt`,
`updatedAt`. It carries no step logic, no enrolment list and no execution history.

Every obvious way to ask "who is enrolled?" or "what is this contact enrolled in?"
fails, and the failures distinguish a missing route from a permission problem:

```text
GET /contacts/{contactId}/workflow          404 {"message":"Cannot GET /contacts/{id}/workflow"}
GET /contacts/{contactId}/workflows         404 Not Found
GET /contacts/{contactId}/workflow/{wfId}   404 Not Found
GET /workflows/{wfId}/contacts              404 {"message":"Cannot GET /workflows/{id}/contacts"}
GET /workflows/{wfId}/enrollments           404 Not Found
GET /workflows/{wfId}/executions            404 Not Found
GET /workflows/?locationId=X&contactId=Y    422 {"message":["property contactId should not exist"]}
GET /contacts/{contactId}?includeWorkflows=true
                                            200 – parameter silently ignored, no workflow key in the response
```

The `422` is the most informative: `/workflows/` validates its query schema and
explicitly rejects `contactId`, so the filter is absent by design rather than
undocumented. The `404`s are Express "Cannot GET" route misses, not `401`/`403`,
so no additional OAuth scope will unlock them.

`POST /contacts/{contactId}/workflow/{workflowId}` (add) and the matching `DELETE`
(remove) do exist. Enrolment is **write-only**: you can put a contact into a
workflow and take it out, but you cannot ask where it currently is.

## Why it's non-obvious

The presence of `POST` and `DELETE` on `/contacts/{id}/workflow/{wfId}` strongly
implies a `GET` on the same path, and every other HighLevel collection supports a
read. It does not. Nothing in the docs states the asymmetry, so the natural
assumption – that enrolment is readable because it is writable – costs a probe
cycle to disprove.

## Consequence

Any assertion that depends on enrolment state – "workflow X removed the contact",
"the contact is no longer being chased", "no duplicate enrolment occurred" – has
**no API evidence path**. It must come from the workflow execution history in the
authenticated UI, or be inferred indirectly by observing that a scheduled action
did not occur past its due time plus a processing grace period.

For test suites this matters: proof-of-absence assertions cannot be automated
through this API. Treat them as UI-evidence or timed-observation cases, and never
record a silent inbox as proof of removal when nothing was scheduled to send anyway.

## Evidence

Live raw-API probes against `Example Co (Staging)` (`loc_EXAMPLE_01`) on
2026-09-10 with a valid agency-derived Location token, during the Example Co
staging workflow test run `SA-20260910-01`. All eight request forms above were
issued in one pass; status codes and bodies are quoted verbatim. Confirmed, not
hypothesised.
