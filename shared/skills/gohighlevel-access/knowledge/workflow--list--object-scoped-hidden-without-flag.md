---
id: ghl-workflow-list-object-scoped-hidden-without-flag
title: The workflow list omits custom-object-scoped workflows unless includeCustomObjects is asked for
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: workflow
field_type: null
endpoint: GET /workflow/{locationId}/list
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: 2026-09-14
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/workflow--list--object-scoped-hidden-without-flag.md
created: 2026-09-14T19:30:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Object-scoped workflows are hidden by a default, not by a limitation

## Behaviour

```text
GET /workflow/{loc}/list?limit=500&offset=0&sortBy=name&sortOrder=asc
    -> every workflow scoped to contacts. Custom-object workflows are absent.

GET /workflow/{loc}/list?limit=500&offset=0&sortBy=name&sortOrder=asc
      &includeCustomObjects=true&includeObjectiveBuilder=true
    -> the same list, plus the workflows scoped to a custom object.
```

The UI sends both flags together on every list call it makes.

A workflow scoped to an object carries `customObjectType` on its own record, naming
the object it runs on:

```json
"customObjectType": "custom_objects.site_visits"
```

Contact-scoped workflows carry `customObjectType: null`. In the reference account 45
captures had `null` and 2 had `custom_objects.site_visits`.

Their triggers are of types that only exist for objects – `custom_object_created`,
`custom_object_changed` – so a trigger inventory built from contact-scoped workflows
alone will not contain them either.

## Why it's non-obvious

The list without the flag is not an error and not obviously short. It returns a large,
plausible, correctly-shaped result, and nothing in it says a category has been
withheld. A sweep of the reference account returned 421 assets and 91 workflows and
looked complete; two workflows were missing and only someone who knew they existed
could tell.

The flag name is also not a filter one would think to try: the natural guess is that
object-scoped workflows need a different endpoint or an object parameter, not that the
ordinary list has a boolean that suppresses them by default.

## Consequence

Any inventory built from this endpoint must send `includeCustomObjects=true` or it
will be quietly incomplete – and incomplete in a way that gets worse as an account
adopts custom objects. Folder listings need the flag too; it is not inherited from the
parent call.

This narrows, rather than contradicts, the recorded finding that object-scoped
workflows are invisible to `GET /workflows/` on the **public** API. That remains true
there. On the internal list they are one query parameter away.

## Evidence

The two missing workflows were identified by the owner from an asset sweep of
`Example Co` (`loc_EXAMPLE_01`) on 2026-09-14 – `179ba849…` and `7345901a…`,
both scoped to `custom_objects.site_visits`. Neither appeared anywhere in a
421-asset document. Searching three traffic recordings for either id found nothing:
the pages that list them were never opened. The flag was found by comparing the
sweep's list URL against the seven list URLs the UI was recorded sending, every one
of which carried `includeCustomObjects=true`.

## Applies to

`GET /workflow/{locationId}/list` on `backend.leadconnectorhq.com`, at the root and
with `parentId`. Not tested: whether the same flag exists on any other collection that
can be object-scoped.
