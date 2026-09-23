---
id: ghl-general-folder-lists-top-level-returns-folders
title: Funnel and workflow list endpoints return folders at the top level, not records
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /funnels/funnel/list, GET /workflow/{locationId}/list
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-14
verified: 2026-09-14
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--folder-lists--top-level-returns-folders-not-records.md
created: 2026-09-14T10:10:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Funnel and workflow list endpoints return folders at the top level

## Behaviour

`GET backend.leadconnectorhq.com/funnels/funnel/list?locationId=&type=funnel&category=all&offset=0&limit=500`
returns, for the Example Co reference account, four rows – **all of them folders**:

```json
{"_id": "id_EXAMPLE_01", "category": "folder", "name": "003. List Cleanup/MGMT",
 "steps": [], "type": "funnel"}
```

The real funnels only appear when the same call is repeated with the folder's id:

```
GET /funnels/funnel/list?locationId=&type=funnel&category=all&offset=0&parentId={folderId}&limit=15
```

```json
{"funnels": [{"_id": "id_EXAMPLE_02",
  "name": "003. Update Contact Information (Wrong Contact Info)",
  "steps": [{"id": "...", "name": "Update Wrong Phone Number/Email",
             "pages": ["id_EXAMPLE_03"], "sequence": 1,
             "type": "optin_funnel_page", "url": "/update-information"}]}]}
```

`GET /workflow/{locationId}/list?parentId={folderId}&limit=50&offset=0` behaves the same way and
returns `{rows, count, folderName, folderPerm, parentId, isLocationRateLimited}`. Without
`parentId` it returns the top level; the reference account holds 81 workflows and 10 directories
and needs the recursion to see all of them.

## Why it's non-obvious

The response is a `200` with a plausible-looking list, and `category: "folder"` is the only
thing distinguishing a folder row from a funnel row – there is no `isFolder` boolean and no
envelope field saying the list is partial. An asset sweep that trusted the top level concluded
Example Co had **zero funnels** when it has eleven, then correctly fetched pages for four
folder ids and got four empty arrays, which looked like corroboration.

`category=all` reads like it would flatten the hierarchy. It does not; it filters within one
level.

## What to do

Recurse. Treat any row with `category: "folder"` (funnels) or `type: "directory"` (workflows) as
a node to descend into, and keep descending until no new folder ids appear. Count the records
you end up with against the account's own UI before believing a zero.

## Related

- `/shared/skills/gohighlevel-access/knowledge/general--merge-fields--custom-data-endpoint-per-surface.md`
