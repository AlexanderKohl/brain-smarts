---
id: ghl-general-marketplace-dynamic-refresh-20s-tick
title: A Dynamic field group refresh arrives on a ~20 second tick, so it looks broken to anyone who does not wait
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
created: '2026-09-14T14:20:00+10:00'
updated: 2026-09-23T12:00:00+10:00
evidence:
- Railway staging deploy logs, deployment <uuid-01>, 2026-09-14T03:52:53Z-03:55:24Z
---

# The refresh works, but not immediately

## Behaviour

Changing an **Alters Dynamic Field** value does refresh the Dynamic group
([[general--marketplace-action-fields--second-alters-dynamic-refires]]) - but the request
that carries the change arrives on a recurring tick of roughly 20 seconds, not the moment
the value changes:

```
03:54:44.345  object='contact'  mode='hide'
03:55:04.356  object='contact'  mode='select'    +20.01s
03:55:24.343  object='contact'  mode='hide'      +19.98s
```

Three consecutive gaps of 19.98-20.01s while a dropdown was being changed between them. A
person clicking does not land on a 20-second grid three times running. Other gaps in the
same session (49.95s, 41.13s) are near-multiples of the same tick. Opening the action panel
fires a request immediately, outside the cadence.

The practical consequence: an author changes the control, sees nothing happen, and concludes
it is broken. Roughly twenty seconds is well past the point where a person assumes a UI did
not respond. The owner's first report of this feature was exactly that - "it only switches if
I save the workflow action" - and saving does work, because reopening the panel forces an
immediate fetch. Waiting also works.

## Why it's non-obvious

The latency is long enough to be mistaken for absence, and short enough that any test
involving a save or a reopen hides it entirely. It also makes causation hard to establish in
either direction: a value appearing in a later request does not prove the change caused the
request, and a UI that has not updated yet does not prove the refresh never happens.

To measure it, compare *intervals* between consecutive requests, and check what the
multiselect widget was holding in each - the widget's contents can only have been put there
by a field HighLevel actually rendered.

## Consequences for design

A Dynamic response may vary its titles, options and which fields it returns on an
Alters-Dynamic value, and that does reach the author. But it will not feel instant, so:

- Do not build anything that depends on the author seeing the change immediately.
- Where the swap matters, say so in help text that is visible in *both* states, so someone
  looking at a stale panel is not misled by it.

## Applies to

Marketplace custom workflow **action** Dynamic fields. Not tested for workflow **triggers**.
See [[general--marketplace-action-fields--dynamic-post-fires-twice]] for the duplicate-request
behaviour observed in the same sessions.
