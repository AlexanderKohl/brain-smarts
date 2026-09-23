---
id: ghl-rate-limits-hundred-per-ten-seconds
title: 100 requests per 10 seconds and 200,000 per day; 10 to 20 in flight is safe
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: null
field_type: null
endpoint: all authenticated endpoints
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-17
verified: null
source_refs: []
created: 2026-09-17T21:10:00+10:00
updated: 2026-09-23T14:45:16+10:00
---

# The rate limits, and how much can be in flight

## Behaviour

HighLevel's stated limits, as reported on 17 September 2026:

> HighLevel currently allows 100 requests per 10 seconds and 200,000 requests per day,
> 10 to 20 requests at a time should work.

The same report, with the scope:

> HighLevel currently allows 100 requests per 10 seconds **per app per Location**.

So the ceiling is **10 requests per second sustained per location**, with a daily cap of
**200,000**, and a concurrency of **10 to 20 in flight** stays inside the per-10-second window
in practice. The per-location scope means two sub-accounts do get two budgets - the opposite of
what this entry first assumed.

Marked `status: pending`: this is a reported figure, not something this repository has
measured. Promote it to `confirmed` when a run either sustains that rate without a 429 or
finds the real edge. The limits are HighLevel's to change and the phrasing *currently* is
theirs.

## Why it's non-obvious

Nothing in this skill stated a number before this entry. `SKILL.md` said only that the client
"honours HighLevel rate-limit responses", and `ghl_oauth/client.py` retries a 429 with
`Retry-After` up to `GHL_RATE_LIMIT_RETRIES`. That is a reaction, not a budget: it tells a
caller what to do when it has already gone too fast, and nothing about how fast it may go.

The consequence is that every caller written here has been **sequential by default**, because
one request at a time is the only rate obviously safe without a number. On a test
runner that is the difference between a run of minutes and a run of hours: its fixture
creation alone is one contact, one opportunity and two collision searches per check, and it
performs them one after another.

## Evidence

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

All authenticated calls on `https://services.leadconnectorhq.com/`, agency and sub-account
alike, **budgeted per app per location**.

The shape that fits it is a reservoir rather than a concurrency cap: capping how many requests
are in flight says nothing about how many went in the last ten seconds, and twenty callers
firing four requests each is eighty in a burst. Count what has actually gone in the window and
wait when the next one would break it, with headroom below 100 because the runner is rarely the
only thing talking to a sub-account. The runner's request reservoir is that, defaulted to 95 in
10 seconds.

Worth pairing with retry on 429 **and** on 500, 502, 503 and 504, with exponential backoff and
jitter. `ghl_oauth/client.py` retries 429 with `Retry-After` today and does not retry the 5xx
family at all.

Two consumers worth sizing against it:

- A check runner - a full run against one sub-account can plan roughly 470
  write requests plus polling reads, comfortably inside the daily cap and entirely
  bottlenecked on being sequential.
- Any sweep or bulk read in `/shared/skills/gohighlevel-access/`.

## Related

Bulk creation does not exist as an alternative. The contacts OpenAPI snapshot carries only
`POST /contacts/bulk/tags/update/{type}`, `POST /contacts/bulk/business` and
`POST /contacts/upsert`; none creates many records in one call, so throughput has to come
from concurrency rather than from batching.
