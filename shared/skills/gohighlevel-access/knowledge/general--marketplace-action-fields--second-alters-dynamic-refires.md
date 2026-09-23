---
id: ghl-general-marketplace-second-alters-dynamic-refires
title: A second Manage Field flagged "Alters Dynamic Field" does refresh the Dynamic group, on the next ~20s tick
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: select
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
- /memory/skills/gohighlevel-access/knowledge/general--marketplace-action-fields--second-alters-dynamic-refires.md
---

# More than one action field can refresh the Dynamic field group

## Behaviour

A custom workflow action may flag **more than one** Manage Field with
**Alters Dynamic Field**, and each flagged field genuinely re-fires the
action's Dynamic POST when its value changes. Confirmed with a plain
**constants Select** (not an External API Select) added alongside the
existing Object field on `Generate Record Update Form`:

```
02:08:58  action_fields_request  object_key='opportunity'  field_selection_mode='hide'    <- Object changed
02:16:01  action_fields_request  object_key='opportunity'  field_selection_mode='select'  <- mode changed only
02:17:01  action_fields_request  object_key='opportunity'  field_selection_mode='hide'    <- mode changed only
02:17:09  action_fields_request  object_key='opportunity'  field_selection_mode='select'  <- mode changed only
```

`object_key` is constant across the last three; only the second flagged
field's value changed, and the POST fired each time carrying both values.
This means a Dynamic response can legitimately vary its field titles,
options and which fields it returns at all on something other than Object.

## Why it's non-obvious

HighLevel's Custom Actions documentation describes one Dynamic field per
action and does not say how many fields may alter it. This repository
carried a **contradicting** earlier finding: a 2026-08 live test split Hide
Fields out into its own *External API Select* with the flag on, hoping the
still-combined Read-only/Required Dynamic field would cascade-refresh, and
observed no refresh – recorded as "tried and reverted, don't re-attempt
without new information" (Pathway 12).

That earlier finding is **not refuted**, but it is narrower than it reads.
The distinction that appears to matter: the working case is a **constants
Select whose value is posted in `data` and read by the same Dynamic
endpoint**; the failing case tried to make one field's *options endpoint*
cascade into a second, separate field's Dynamic group. Do not generalise
either result past its own shape.

## Evidence

Live, owner-run, in the real HighLevel workflow editor against the staging Marketplace app
(`generate_record_update_form_s`), location `loc_EXAMPLE_04`, read from Railway staging
deploy logs.

The decisive evidence is not the request timing - it is **what the multiselect widget was
holding** in consecutive requests, which only the rendered field can have put there:

```
03:54:44  mode='hide'    excluded=None  included=None   widget empty
03:55:04  mode='select'  excluded=2     included=None   Hide Fields was rendered and seeded
03:55:24  mode='hide'    excluded=None  included=51     Select Fields was rendered and seeded
```

Between 03:55:04 and 03:55:24, with no save, the widget stopped holding a 2-item *excluded*
list (Hide Fields' seeded default for Contact) and started holding a 51-item *included* list
(Select Fields' seeded default). HighLevel cannot have populated an include list unless it
had actually rendered the `included_field_keys` field. The group refreshed.

## Correction history

Marked `refuted` for about fifteen minutes on the day it was written, then restored. The
refutation was half right and half wrong, and the half that was wrong mattered more:

- **Right:** the requests arrive on a ~20 second tick, not the instant a value changes. The
  original evidence below (a mode value appearing in a later request) genuinely did not prove
  causation on its own - the tick would have carried it regardless. That latency now has its
  own entry, [[general--marketplace-action-fields--dynamic-refresh-lands-on-a-20s-tick]].
- **Wrong:** the claim that the rendered field list only changes once the action is saved and
  reopened. It changes without a save. The proof is the widget's own state in consecutive
  requests - see Evidence below.

The lesson worth keeping: an owner reporting "it only works if I save" and a measurement
showing "these requests are 20s apart" are both true and do not add up to "a save is
required". A slow refresh looks exactly like no refresh to someone who does not wait.

## Applies to

Marketplace custom workflow **actions**. Not tested on custom workflow
**triggers**, whose filter fields use a different endpoint
(`/api/marketplace/triggers/filters`) – do not assume it carries over.
See [[general--marketplace-action-fields--dynamic-post-fires-twice]] for
the duplicate-call behaviour observed in the same session.
