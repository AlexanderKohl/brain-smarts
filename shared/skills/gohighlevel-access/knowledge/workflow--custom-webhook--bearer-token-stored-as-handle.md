---
id: ghl-workflow-custom-webhook-bearer-token-stored-as-handle
title: A custom-webhook step's bearer token is captured as a WFSM_ handle, not the token
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflow/{locationId}/{workflowId}
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: null
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--custom-webhook--bearer-token-stored-as-handle.md
created: 2026-09-14T16:10:00+10:00
updated: 2026-09-23T18:00:00+10:00
---

# A custom-webhook step's bearer token is captured as a `WFSM_` handle, not the token

## Behaviour

A `custom_webhook` step (`attributes.event: "CUSTOM"`) configured with bearer
authorization comes back from the internal workflow read as:

```json
"authorization": {
  "type": "BEARER_TOKEN",
  "data": { "token": "WFSM_6a0e90dc658b2c814762933a" }
}
```

The value is the string `WFSM_` followed by a 24-hex Mongo ObjectId. It is not the
bearer token the step sends. The same handle appears in every read of the workflow
and nowhere else in a 437-endpoint sweep of the location.

## Why it's non-obvious

The key is `token` and the value is twenty-nine characters, so any scan that judges
the key reports a pasted credential. An audit did exactly that on 14 September 2026 and
raised a literal-secret finding against a draft workflow that was, in fact,
following the recommended pattern.

The step's `headers[]` array is the place where a pasted credential would sit
(`{key: "x-webhook-secret", value: "..."}`); the reference account moved that one to
`{{custom_values.webhook_key}}`. The `authorization` block is a different mechanism
and never carries the literal.

## Evidence

Observed in the Example Co sweep of 2026-09-14T11:24:24+10:00 on the step that
updates a task through `PUT services.leadconnectorhq.com/contacts/{{contact.id}}/tasks/{{task.id}}`.
Two occurrences, one distinct value. The prefix `WFSM_` is read as "workflow secret
manager" or similar by shape alone; HighLevel has not been observed naming it. The
storage-side claim – that HighLevel holds the token and resolves the handle at run
time – is **pending**: it is the only reading consistent with the shape, but no probe
has confirmed it, and no endpoint that lists or resolves handles has been observed.

## Applies to

`custom_webhook` steps with `authorization.type: "BEARER_TOKEN"` read through the
internal `GET /workflow/{locationId}/{workflowId}`. Not checked for other
authorization types (basic, API key) or for the public API, which does not expose
step configuration at all.

Consequence for a secret scanner: a value in any identifier shape HighLevel issues – UUID,
24-hex ObjectId, a prefixed ObjectId handle like this one, or a twenty-character
short id – is treated as a reference and never as a credential, whatever key it sits
under.
