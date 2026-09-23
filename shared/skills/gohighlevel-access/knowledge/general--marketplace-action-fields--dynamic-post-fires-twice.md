---
id: ghl-general-marketplace-dynamic-post-fires-twice
title: One field change fires the Dynamic POST twice, and the Object options GET twice with it
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: POST <app>/api/marketplace/action-fields
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-09-14'
verified: '2026-09-14'
created: '2026-09-14T12:20:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- Railway staging deploy logs, deployment <uuid-01>, 2026-09-14T02:16:01Z–02:17:10Z
---

# The Dynamic POST is not fired once per change

## Behaviour

Changing a single **Alters Dynamic Field** value in the workflow editor
produces **two** POSTs to the action's Dynamic URL, each preceded by its
own GET to the Object field's External API options URL – four inbound
requests for one click. The pair arrives within milliseconds to about a
second of each other, from different `x-forwarded-for` addresses:

```
02:16:01.286  marketplace_objects_request
02:16:01.288  marketplace_action_fields_request   mode='select'
02:16:01.297  marketplace_objects_request
02:16:01.309  marketplace_action_fields_request   mode='select'   <- same change, second POST
```

Reproduced on all three changes in the session (02:16:01, 02:17:01,
02:17:09/10). Opening the action fires the same pattern.

## Why it's non-obvious

Nothing documents a retry, double-dispatch or debounce-failure here, and
the duplicate is invisible in the editor UI – it only shows in the
consuming app's own request logs. A single log line per change is what a
reader would expect, so duplicate entries look like the owner clicking
twice rather than platform behaviour.

## Consequences

- These endpoints must stay **idempotent and side-effect free**. Anything
  that writes, bills, sends, or increments a counter here runs twice per
  click. Today's handlers are read-only, so this costs only cache-warm
  HighLevel reads.
- Rate limiting on the Dynamic endpoint must budget for roughly double the
  request count an author's interaction implies.
- When reading logs to reconstruct a config session, collapse adjacent
  identical POSTs rather than reading them as two separate author actions.

## Evidence

Live, owner-run, in the real HighLevel workflow editor against the staging
Marketplace app (`generate_record_update_form_s`), read from Railway
staging deploy logs. Not a code-level retry in the consuming app: the two
requests carry different `x-railway-request-id` values and different
client IPs, so both originate from HighLevel.

## Applies to

Marketplace custom workflow **action** Dynamic fields and the Object
field's External API options URL. Not tested for workflow **triggers**.
Discovered alongside
[[general--marketplace-action-fields--second-alters-dynamic-refires]].
