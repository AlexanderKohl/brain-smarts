---
id: ghl-opportunity-picklist-classic-catalogue-bare-strings
title: Classic opportunity/contact field catalogue returns picklistOptions as bare strings, with no key to read
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: picklist
endpoint: GET /locations/{locationId}/customFields?model=all
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-21
verified: null
source_refs: []
created: 2026-09-21T09:13:02+10:00
updated: 2026-09-23T18:00:00+10:00
---

# Classic picklist options are bare strings; only the objects surface splits key from label

## Behaviour

The two custom-field surfaces describe the same kind of choice field differently.

**Classic catalogue** – `GET /locations/{locationId}/customFields?model=all` – returns a
choice field's options as a flat list of strings:

```json
{
  "fieldKey": "opportunity.installation_scheduler_status",
  "dataType": "RADIO",
  "picklistOptions": [
    "Not required", "Ready", "Week assigned",
    "Scheduled", "Communicated", "Reschedule needed"
  ]
}
```

**Objects surface** – `GET /objects/{key}?fetchProperties=true` – returns the same kind of
field as `{key, label}` pairs:

```json
{
  "fieldKey": "custom_objects.installers.scheduler_role",
  "dataType": "SINGLE_OPTIONS",
  "picklistOptions": [
    {"key": "crew_lead", "label": "Crew lead"},
    {"key": "trade_assistant", "label": "Trade assistant"}
  ]
}
```

There is no `key` anywhere in the classic shape, so a caller writing to a classic opportunity
or contact choice field has only the displayed string to send. On the objects surface the
stored value is `opt.key` (see [[general--picklist-fields--value-is-key-not-label]]), which is
why an installer's `scheduler_role` reads back as `crew_lead` while an opportunity's
`installation_scheduler_status` is expected to read back as `Week assigned`.

## Why it's non-obvious

`general--picklist-fields--value-is-key-not-label.md` states the key-not-label rule for "any
RADIO/SINGLE_OPTIONS/CHECKBOX field on any object type". That reads as universal, and a caller
who believes it will go looking for an `opt.key` on an opportunity field and find nothing to
read. The two surfaces are already known to diverge for field *definitions*
([[opportunity--custom-fields--v3-object-key-rejected-use-classic]]); they diverge for option
*shape* as well, and the same integration frequently touches both – one object's options need
the key, the other's have none.

## Evidence

Live read-only probe against `Example Co (Staging)` (`loc_EXAMPLE_01`) on 2026-09-21
while auditing a scheduling integration's field dependencies. The classic catalogue
returned 225 opportunity fields; every `RADIO` / `SINGLE_OPTIONS` / `CHECKBOX` among them
carried `picklistOptions` as a bare string list (`["Yes", "No", "N/A"]` on
`opportunity.ac_isolation_switch`). The same probe read `custom_objects.installers` through
`GET /objects/...?fetchProperties=true`, where `accreditations`, `active_in_scheduler` and
`scheduler_role` all came back as `{key, label}` pairs.

`pending`, deliberately: the *catalogue shape* difference is directly observed and not in
doubt. The consequence – that a classic field therefore stores and returns the displayed
string – is an inference. No opportunity in that sub-account had any of these fields set, so
no stored classic choice value was read back. Promote to `confirmed` once a write-then-read on
a classic RADIO field is observed, or refute it if the stored value turns out to be a
server-derived key that the catalogue simply does not expose.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Observed for the classic `locations/{id}/customFields` catalogue, which serves both
`model=opportunity` and `model=contact`. Custom-object fields are the contrasting case and
keep the `{key, label}` shape, so code that reads both surfaces cannot use one parser for
options without normalising first.
