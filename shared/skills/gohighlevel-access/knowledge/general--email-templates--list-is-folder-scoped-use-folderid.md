---
id: ghl-general-email-templates-list-is-folder-scoped-use-folderid
title: Email template listing returns only the current folder level; descend with folderId, or search across all folders with search=
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /emails/locations/{locationId}/templates?folderId=|search=
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: 2026-09-15
source_refs:
  - /shared/skills/gohighlevel-access/knowledge/general--email-templates--requires-version-v3-header.md
created: 2026-09-15T14:40:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# The template list is one folder level, not the whole location

## Behaviour

`GET /emails/locations/{locationId}/templates` (`Version: v3`) returns **only root-level
entries**, and its `total` counts only that level. Folders appear as ordinary rows with
`"type": "folder"` and a `childCount`; their children are **not** included:

```json
{"id":"...","name":"Appointment - Confirmations & Reminders","type":"folder",
 "childCount":11,"createdAt":"...","updatedAt":"..."}
```

A template row has `"type": "template"` instead, plus `templateType`, `subjectLine` etc. A
location showing `total: 5` at root can therefore hold 39 templates.

Two ways to reach the rest:

- **`&folderId={folderId}`** returns that folder's children (`total` = the folder's own count).
  Recurse on nested folders. **`parentId`, `parentFolderId`, `parent` and `name` are silently
  ignored** on this endpoint – each returns the unfiltered root level with `200`, which reads
  exactly like an empty or fully-enumerated result. `folderId` is the only one that works.
- **`&search={text}`** matches across every folder at once and returns flat template rows
  (no folder rows). Useful as an independent cross-check of a recursive walk.

On the undocumented `/emails/builder?locationId=` alias the working parameter is the opposite
one: **`parentId`** descends into a folder there, while `folderId` and `search` are ignored.
Two sibling endpoints on the same underlying resource, each ignoring the other's parameter name.

`limit` is capped at 50 (`422 ["limit must not be greater than 50"]`); page with `offset`.

## Why it's non-obvious

The ignored parameters fail open, not closed. `parentId=<folder>` returns `200` with the root
listing, so a script that filters those results finds nothing inside the folder and concludes
the folder is empty rather than that the filter was dropped. Combined with the root `total`
looking like a location-wide count, a caller can confidently report "5 templates, 1 match" for
a location that actually holds 39 templates and 35 matches. Verify a folder walk against
`?search=` or against each folder's `childCount` before treating a count as complete.

## Evidence

Confirmed live 2026-09-15 in `Example Co Master` (`loc_EXAMPLE_02`). Root listing
returned 5 rows (4 folders with `childCount` 11/9/9/5, plus 1 template). A recursive walk via
`folderId` found the 34 children; `?search=DELETE` independently returned the same 34 ids.
The earlier single-level pass in the same session had reported 5 active templates and found
only the 1 root-level match – the owner knew more existed, which is what exposed this.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Email Builder v2 templates via a Location OAuth token derived from the connected agency grant,
on both path families. Folder rows themselves are not deleted by the template DELETE route
(see `general--email-templates--delete-route-needs-location-id-segment.md`); emptying a folder
leaves the folder in place with `childCount` absent.
