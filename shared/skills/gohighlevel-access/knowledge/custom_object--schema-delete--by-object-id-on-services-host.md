---
id: ghl-custom_object--schema-delete--by-object-id-on-services-host
title: A custom object is deleted by its object id, not its key, and the call takes the fields and associations with it
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: highlevel
object_type: custom_object
field_type: null
endpoint: DELETE /objects/{objectId}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs: []
created: 2026-09-15T21:30:47+10:00
updated: 2026-09-23T14:45:16+10:00
---

# Deleting a custom object: by id, on the services host

## Behaviour

Deleting the `ExampleDocs Records` object from the HighLevel interface, captured by a browser extension's
traffic recorder on 15 September 2026:

```text
DELETE https://services.leadconnectorhq.com/objects/000000000000000000000001?locationId=loc_EXAMPLE_04
→ 200 {"id":"000000000000000000000001","success":true,
       "meta":{"deletedFields":[…3 ids…],"deletedAssociationIds":[…1 id…]},"traceId":"…"}
```

- The object is addressed by its **object id**, the `id` the objects listing returns, not by
  its key (`custom_objects.example_docs`). Every other schema call in this API is addressed by key,
  which is why an inferred delete by key was wrong.
- The sub-account rides in the query string; there is no request body.
- One call removes the object's fields and its associations as well, and the response names
  them. Nothing had to be deleted first: the object still held its records and its fields.
- Host is `services.leadconnectorhq.com`, the same host the object is created on. The
  interface then re-read the listing from both `services` and `backend`.

## Why it's non-obvious

The vendored specification `openapi/objects-v3.json` has nine operations, and `/objects/{key}`
carries only `get` and `put`. No schema delete appears in it anywhere, so the capability looks
absent from the API until a capture of the interface shows the call. The id-rather-than-key
shape is the second surprise, and an inferred `DELETE /objects/custom_objects.example_docs` would
have failed or, worse, matched nothing and looked like a permissions problem.

## How to use it

Read the objects listing for the sub-account, find the entry whose `key` is the one to remove,
take its `id`, and delete that. Reading the listing first is not optional: the id is the only
way in, and it also proves which sub-account the object belongs to.

## Scope and caveats

- Observed through the **interface's own session**, not through an OAuth token. The host and
  the shape are the public ones, so an OAuth location token is expected to work, but that is
  unverified: the first OAuth run should be treated as a probe.
- Recorded in `shapes` mode, so string values in the listing are elided. The URL, the method,
  the status and the response keys are exact.
- Destructive and not reversible. Run it only with the owner's explicit permission for that
  object in that confirmed sub-account (see `SKILL.md` and the owning node's `RULES.md`).

## Evidence

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.
