---
id: railway-general-http-logs-startdate-string
title: httpLogs startDate and endDate expect String, not DateTime
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: railway
object_type: general
field_type: null
endpoint: POST /graphql/v2 httpLogs
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-31
verified: 2026-09-12
source_refs:
  - /memory/skills/railway-access/knowledge/general--http-logs--startdate-string.md
created: 2026-08-31T15:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# httpLogs date arguments are String

## Behaviour

`deploymentLogs` / `buildLogs` accept `$startDate: DateTime` / `$endDate: DateTime`.
`httpLogs` on the same GraphQL endpoint rejects those variables:

```text
Variable "$startDate" of type "DateTime" used in position expecting type "String".
Variable "$endDate" of type "DateTime" used in position expecting type "String".
```

HTTP 400, `extensions.code` `GRAPHQL_VALIDATION_FAILED`. The failure happens even when
both arguments are omitted as GraphQL nulls, if the operation still *declares* them as
`DateTime`.

## Why it's non-obvious

The railway-access log client uses one query shape for deploy, build and HTTP logs, with
`DateTime` variables. That works for deploy/build. Official API examples do not call out
that `httpLogs` uses `String` for the same argument names.

## Evidence

Live probe 2026-08-31 against staging web deployment
`<uuid-01>` (`railway_logs.py --kind http`, with and without
`--since`). `deploymentLogs` with `--since 2h` on the same deployment succeeded.
`status: confirmed`.

## Amendment 2026-09-12 – they are also deprecated no-ops

Schema introspection with `args(includeDeprecated: true)` (the default hides deprecated
arguments, which is why the 2026-08-31 probe saw only the type mismatch) shows the full
picture:

```text
httpLogs(
  deploymentId: String!   afterDate: String   anchorDate: String   beforeDate: String
  afterLimit: Int         beforeLimit: Int    limit: Int           filter: String
  startDate: String  [DEPRECATED: This argument has no effect.
                      Use beforeDate/anchorDate/afterDate instead.]
  endDate:   String  [DEPRECATED: same]
)
```

So correcting the declared type to `String` clears the HTTP 400 but buys nothing: the
arguments are ignored. A timeframe-bounded `httpLogs` call must use `afterDate` /
`beforeDate` / `anchorDate`, all `String`. `deploymentLogs` and `buildLogs` keep real,
non-deprecated `startDate` / `endDate` of type `DateTime`.

`railway_client.fetch_logs` now branches: `httpLogs` gets its own operation mapping
`--since` to `afterDate` and `--until` to `beforeDate`; deploy/build are unchanged.

## Applies to

Confirmed for `httpLogs` only. `deploymentLogs` still accepted `DateTime` on the same
day, and still does on 2026-09-12. Do not change deploy/build variable types from this
entry alone.

See also [`general--http-logs--empty-for-account.md`](general--http-logs--empty-for-account.md):
even a correctly-formed `httpLogs` call returned zero rows for every service tested.
