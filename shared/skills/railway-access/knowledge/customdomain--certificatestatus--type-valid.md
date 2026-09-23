---
id: railway-customdomain-certificatestatus-type-valid
title: Ready custom-domain certificates report TYPE_VALID, not ISSUED
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: railway
object_type: customdomain
field_type: enum
endpoint: POST /graphql/v2 domains.customDomains.status.certificateStatus
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-31
verified: 2026-08-31
source_refs:
  - /memory/skills/railway-access/knowledge/customdomain--certificatestatus--type-valid.md
created: 2026-08-31T18:14:30+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Ready certificates use CERTIFICATE_STATUS_TYPE_VALID

## Behaviour

Once DNS has propagated and the certificate is live, `domains.customDomains[].status`
returns:

- `verified: true`
- `certificateStatus: "CERTIFICATE_STATUS_TYPE_VALID"`
- `certificateErrorMessage: null`
- CNAME `dnsRecords[].status: "DNS_RECORD_STATUS_PROPAGATED"`
- `currentValue` equal to `requiredValue`

It does **not** use `CERTIFICATE_STATUS_ISSUED` (or any value ending in `ISSUED`) on
this query. Matching only `/ISSUED$/` therefore never maps a ready domain to
`verified`.

Do not treat a suffix of `VALID` alone as issued: `CERTIFICATE_STATUS_TYPE_INVALID`
also ends with `VALID`. Match `TYPE_VALID` (or an explicit `ISSUED` suffix) instead.

## Why it's non-obvious

Older Railway snippets and some SDKs mention `CERTIFICATE_STATUS_ISSUED` /
`CERTIFICATE_STATUS_PENDING`. The live `domains` query uses the `CERTIFICATE_STATUS_TYPE_*`
family (`TYPE_VALID` when the cert is ready).

## Evidence

Live GraphQL `domains` query 2026-08-31 against staging project
`<uuid-01>` / environment
`<uuid-02>`. Both the existing `staging.forms.example.com`
attachment and a newly attached customer hostname returned
`CERTIFICATE_STATUS_TYPE_VALID` while `verified` was true. `status: confirmed`.

## Applies to

Confirmed for `query domains { customDomains { status { certificateStatus } } }` on
this account. Not confirmed for other Railway domain APIs or older enum names that
might still appear in docs.
