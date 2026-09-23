---
id: ghl-publishing-state-is-a-field-not-an-endpoint
title: Publishing is a field on the record, not a separate call
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: null
field_type: null
endpoint: PUT /membership/locations/{locationId}/posts/{postId}, PUT /invoices/estimate/{estimateId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: 2026-09-14
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--publishing--state-is-a-field-not-an-endpoint.md
created: 2026-09-14T19:35:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# "Save" and "Save and publish" are the same request

## Behaviour

Course content, membership offers and estimates all have two visible states in the UI
– a draft you are still working on, and a published or sent version. None of them has
a publish endpoint. The state is a field in the body of the ordinary save:

| What | Endpoint | Field | Values observed |
| --- | --- | --- | --- |
| Course post | `PUT /membership/locations/{loc}/posts/{id}` | `visibility` | `draft`, `published` |
| Membership offer | `PUT /membership/locations/{loc}/offers/{id}` | `visibility` | `draft`, `published` |
| Estimate | `PUT /invoices/estimate/{id}` | `estimateStatus` | `draft` |

The evidence is two saves of the same offer, seconds apart, identical but for
`visibility`. "Save" sent `draft`; "Save and publish" sent `published` to the same URL
with the same method.

`isLivePaymentMode` (offers) and `liveMode` (estimates) sit alongside and are a
different axis – test versus live payment processing, not draft versus published.

## Why it's non-obvious

The UI presents publishing as an action, with its own button and its own confirmation,
so the natural expectation is a `POST .../publish`. Looking for one and not finding it
reads as a gap in the recording rather than as the answer.

## Consequence

Good news for anyone capturing configuration: **no special handling is needed.** The
state comes back in the ordinary read, so a capture that reads the record already
knows whether it is live. There is no second call to model, no publish event to
observe, and no risk of a capture that cannot tell a draft from a live one – provided
the read is there at all.

It also means a save-detection rule keyed to endpoints sees publishing and drafting as
the same event, which is correct: both change the record, and both should refresh it.

The reverse case is the one to watch. Because the state is a field, a diff between two
captures will show a publish as an ordinary field change, indistinguishable in shape
from a title edit. Anything that wants to report "this went live on Tuesday" has to
look at that field specifically.

## Evidence

`traffic-2026-09-14-19-28-18.json` (not committed – full-body recording, see the raw
README). Offer `<uuid-01>` saved twice, `visibility` being
the only difference; post `<uuid-02>` likewise; estimate
`000000000000000000000001` carrying `estimateStatus: draft`.

## Applies to

Membership posts and offers, and estimates. **Not tested:** funnels and websites, blog
posts, social planner posts, or forms and surveys, all of which also have a published
state in the UI and none of which were exercised. Whether they follow the same pattern
is an open question, not an assumption to carry over.
