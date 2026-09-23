---
id: ghl-workflow--trigger--checkbox-add-does-not-fire-on-create
title: "A checkbox 'added' opportunity trigger does not fire when the opportunity is created with the value already set; a select equality trigger does"
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: workflow
field_type: CHECKBOX
endpoint: POST /opportunities/
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: null
source_refs: []
created: 2026-09-15T12:50:00+10:00
updated: 2026-09-23T18:00:00+10:00
---
# Checkbox "added" triggers ignore creation; select equality triggers do not

## Behaviour

On Example Co (Staging), creating an opportunity by `POST /opportunities/` with a checkbox
custom field already holding `Deposit Paid` did not start `4.4` (stage and site-visit status
untouched), while creating one with the single-option field Enquiry Type set to `Support` did
start `5.0`. Observed once each during a staging test run. Working reading: an
"option added" trigger on a checkbox field needs a change event, and creation with the value
in place produces none, whereas an equality condition evaluates on the create event.

## Why it's non-obvious

Both are Opportunity Changed triggers on a custom field, and the builder shows no difference
in when they evaluate.

## Evidence

Rows of a local test-run folder, 15 September 2026.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

