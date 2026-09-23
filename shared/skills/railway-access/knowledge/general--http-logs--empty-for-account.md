---
id: railway-general-http-logs-empty-for-account
title: httpLogs returns zero rows for every service on this account
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: railway
object_type: general
field_type: null
endpoint: POST /graphql/v2 httpLogs
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs: []
created: 2026-09-12T08:20:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# httpLogs returns no rows, even when correctly formed

## Behaviour

A syntactically valid, authorised `httpLogs` query returns `[]` for every deployment
tested – with and without time bounds, with `beforeDate` anchored at now, and against a
service that is demonstrably serving public traffic. No GraphQL error, no auth error,
just an empty list. `deploymentLogs` and `buildLogs` on the *same* deployment IDs return
rows normally in the same session.

## Why it's non-obvious

The call succeeds. There is nothing in the response to distinguish "this deployment
received no HTTP requests" from "HTTP logs are not available to this account", so a
caller can easily read the empty list as evidence about the app rather than about the
API. It also masks itself behind the older `startDate`/`endDate` problem
([`general--http-logs--startdate-string.md`](general--http-logs--startdate-string.md)) –
once that HTTP 400 is fixed the call looks healthy.

## Evidence

Live probes 2026-09-12:

- `ExampleBillAPI` testing, deployment `<uuid-01>`
  (custom domain `testing.example.com`): 0 rows unbounded, 0 rows with
  `--since 2d`, 0 rows with `beforeDate` = now. Its `deploymentLogs` for the same window
  showed ~222 inbound scanner requests, so the service certainly received HTTP traffic.
- `ExampleFormsApp` production web `<uuid-02>`,
  latest deployment `<uuid-03>` (live public site
  `forms.example.com`): 0 rows for `--since 6h` and with `beforeDate` = now.

Two unrelated projects, one of them a live production site, both empty.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Candidate explanations, none yet confirmed

- HTTP logs may be a plan-gated observability feature not enabled on this workspace.
- They may require the request to traverse Railway's edge proxy in a configuration these
  services do not use.
- Retention may be far shorter than the windows probed.

`status: pending` – the observation is solid, the cause is not. Resolve it by checking
the Railway dashboard's own HTTP Logs tab for one of these services: if the dashboard
shows rows the API does not, the fault is in our query shape; if the dashboard is also
empty, it is an account/plan or routing matter and the skill is behaving correctly.

## Applies to

`httpLogs` only. Deploy and build logs are unaffected and remain the reliable source for
this account.
