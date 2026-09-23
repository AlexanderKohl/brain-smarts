---
id: ghl-general-email-templates-requires-version-v3-header
title: Email template CRUD needs an explicit Version:v3 header; undocumented /emails/builder alias also works
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET/PATCH /emails/locations/:locationId/templates[/:templateId]; GET/POST /emails/builder; PATCH /emails/builder/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-28
verified: 2026-08-30
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--email-templates--requires-version-v3-header.md
created: 2026-08-28T14:30:00+10:00
updated: 2026-09-23T18:00:00+10:00
---

# Email template CRUD needs an explicit Version: v3 header

## Behaviour

There are **two working paths to the same underlying template object** – confirmed by fetching
the identical `id` and `previewUrl` through both:

**Listing is folder-scoped** – the list endpoints below return only the current folder level, and the ignored-parameter trap that hides the rest is in `general--email-templates--list-is-folder-scoped-use-folderid.md`. Read that before trusting a count.

**1. Documented path – requires `Version: v3` explicitly:**

```
GET   /emails/locations/{locationId}/templates                -> {"items":[{...}]}
GET   /emails/locations/{locationId}/templates/{templateId}   -> {id, name, editorType,
                                                                   isPlainText, subject,
                                                                   previewText,
                                                                   editorContentUrl, ...}
PATCH /emails/locations/{locationId}/templates/{templateId}
      body: {name, editorContent, editorType ("html"|"text"), previewText, subjectLine,
             fromName, fromEmail, archived, parentFolderId, userId} – all optional; only send
             editorContent + editorType together when changing the body.
      -> 200 {id, name, archived, fromName, fromEmail, subjectLine, previewText, previewUrl,
              editorType, updatedAt, createdAt, isPlainText, ...}
```

This client's `HighLevelConnection.request()` sends a default `Version` header
(`2021-07-28`) unless overridden. This resource requires `Version: v3` – **without it, every
one of these paths returns a plain routing-level `404 Cannot GET/PATCH <path>`**, indistinguishable
from the path genuinely not existing. Pass `headers={"Version": "v3", ...}` explicitly.
`GET /emails/templates?locationId=...` (no `/locations/{id}/` segment) is a different, wrong
guess and still 404s even with `Version: v3`.

**2. Undocumented alias – no special Version header needed:**

```
GET   /emails/builder?locationId={locationId}          -> {"builders":[{...}], "total":[...]}
POST  /emails/builder                                   -> 201 {"id", "redirect", "status":"ok"}
      body: {locationId, name, type}; type must be one of html, folder, import, builder,
      blank, ai_template, vibe-editor (422 lists these exact values otherwise). The "name"
      sent at create time is ignored – every new template comes back named "New Template";
      rename via PATCH. "blank"/"builder" both normalise to templateType "builder"; "html"
      stays "html".
PATCH /emails/builder/{id}                               -> 200, same object as above
      body: {locationId, name, subjectLine, previewText, fromName, fromEmail,
             archived: bool, editorType, editorContent, isPlainText: bool}
```

**Correction 2026-09-15:** a hard delete does exist at `DELETE /emails/builder/{locationId}/{templateId}` (see `general--email-templates--delete-route-needs-location-id-segment.md`). The statement below held only for the `/emails/builder/{id}` form.

No working `DELETE` exists on the `/emails/builder/{id}` form – every variant tried on `/emails/builder/{id}`
(with/without query string or body `locationId`) gave a genuine routing-level
`404 Cannot DELETE ...`. `PATCH {"archived": true}` is the effective delete; archived items drop
out of the default `GET /emails/builder` listing (and presumably the documented list too,
untested).

**`isPlainText: true` / `editorType: "text"` do NOT mean the stored content is plain text –
`editorContent` is always HTML, and these labels don't gate or transform it.** Sending raw `\n`
characters in `editorContent` does round-trip verbatim (fetching `editorContentUrl` afterward
returns the literal `\n`s unchanged), which looks like confirmation that plain-text line breaks
work – **but it's a false positive**: opening that same template in the HighLevel UI renders it
as one unbroken line, because a bare `\n` with no markup produces no visual break in the actual
renderer. This was only caught because the owner manually re-edited the template in the UI and
reported the API-authored version looked wrong. See "Content format" below for what actually
works.

### Content format: real line breaks and lists need real HTML markup

Confirmed by round-tripping the owner's UI-hand-edited template (`GET .../templates/{id}` then
fetching `editorContentUrl`) and then independently reproducing the same structure via API and
re-verifying with a fresh `GET`:

- **Line breaks**: use `<br>` within a paragraph, or separate `<p>...</p>` blocks between
  paragraphs. Plain `\n` is inert.
- **Numbered list**: `<ol style="list-style-type: decimal;"><li><p style="margin-top:
  0px;margin-bottom: 0px;">Item text</p></li>...</ol>` – each `<li>` wraps its text in a `<p>`
  with zero top/bottom margin; this is the exact shape the UI's own editor produces and it
  round-trips byte-for-byte through the API.
- **Bulleted list**: identical shape with `<ul style="list-style-type: disc;">` instead of `<ol>`.
- The API accepts and stores this as a **bare content fragment** – no surrounding
  `<html><head>...<body>` wrapper is required or auto-added by `PATCH`. By contrast, the version
  the owner saved from the visual UI editor *did* have a full `<html><head><style>...</style>
  </head><body style="...">...</body></html>` wrapper (with default `p`/`h1`-`h6` styling rules).
  Whether the missing wrapper on an API-only write affects actual send/rendering fidelity (vs.
  just the editor/preview) is **not yet confirmed** – treat API-authored templates that skip the
  wrapper as unverified for real sends until checked.

## Why it's non-obvious

The generic client default (`Version: 2021-07-28`) is correct for most of this skill's other
confirmed endpoints (Custom Values, Contact fields, Objects records, Users, phone numbers), so
there was no reason to suspect this one specific resource needed a different, undocumented-by-
this-repo default (`v3`) until the actual docs page was fetched with a literal-reproduction
prompt and it explicitly listed `Version: v3` as a required header – a general summarisation
prompt against the same URL had failed to surface this earlier and returned only the page title,
which read as "no documentation available" rather than "you're missing a required header".
**Lesson: a 404 on a documented HighLevel path is not proof the path is wrong – try the
documented `Version` header before concluding the path doesn't exist.**

Separately, there is a second, genuinely unrelated template resource – **this is the UI's
Snippets feature**, and it is **read-only over the API with no write path at all**; see
`general--snippets--read-only-no-write-scope-exists.md` for the 2026-09-15 confirmation –
`GET /locations/{locationId}/templates?type=email|sms|whatsapp` (confirmed live, returns
`{"templates":[],"totalCount":0}` even after the resource above had real entries – a different
store). Only a `.readonly` scope (`locations/templates.readonly`) appears to exist for it; a
live write attempt against `POST /locations/{locationId}/templates` returned
`401 {"message":"The token is not authorized for this scope."}` on the connected agency grant,
and no `locations/templates.write` scope was found anywhere. Do not assume this second resource
is a viable email/SMS template write path.

**Resolved:** the owner initially couldn't see the created/updated template in the HighLevel UI
despite the API confirming it existed, was correctly scoped, and was attributed to the owner's
own HighLevel user (`updatedBy`). It later became visible in the UI without any API-side change
identified as the fix – most likely a UI cache/refresh issue rather than a data problem, since
every API read throughout (including the documented list endpoint) consistently showed exactly
one correct, non-corrupted active record the whole time. Not fully root-caused, but no longer
blocking.

**Caution – alternating writes between the two path families produced an inconsistent
record.** After a full-content `PATCH /emails/builder/{id}` (subjectLine + previewText +
editorContent all changed together and independently verified), a later
`PATCH /emails/locations/{locationId}/templates/{templateId}` that sent **only** `{"name": ...}`
came back with `subjectLine` reverted to the pre-update value while `previewText` stayed at the
new value – and a subsequent full `GET` showed `editorContentUrl` had reverted to the
*original* (pre-update) body text entirely, even though nothing in the intervening calls
should have touched it. Root cause not isolated (not enough probing budget spent to confirm
whether this is inherent to partial-field PATCHes on the documented endpoint specifically, or
to mixing the two path families) – but the practical fix that resolved it cleanly: **always
send every content field (`name`, `subjectLine`, `previewText`, `editorType`, `editorContent`)
together in one PATCH**, and prefer sticking to one path family per record rather than
alternating. A single complete `PATCH /emails/locations/{locationId}/templates/{templateId}`
with all fields set at once was independently re-verified correct via a fresh `GET` immediately
after, with no drift.

## Evidence

Confirmed 2026-08-28: created "Sample Text Template (Test)" in `Example Test`
(`loc_EXAMPLE_04`, a designated test sub-account) via `POST /emails/builder` ->
`PATCH /emails/builder/{id}` with `isPlainText: true`. Two accidental duplicate shells created
during path discovery were archived (`PATCH {"archived": true}`) rather than left as clutter.
A follow-up `PATCH .../emails/builder/{id}` set multi-paragraph, numbered-list `editorContent`
with `\n` line breaks, verified intact via the `previewUrl` asset. Finally, the documented
`PATCH /emails/locations/{locationId}/templates/{templateId}` was independently tried with
`Version: v3` and succeeded (`200`), returning the *same* `id` and `previewUrl` as the
`/emails/builder` object – confirming both paths address one underlying resource. Re-fetching
`GET /locations/{locationId}` in the same pass confirmed the location name really is
"Example Test", ruling out a wrong-subaccount write. `GET /emails/locations/{locationId}/
templates` (the documented list endpoint, `include=all`) was also confirmed to return exactly
the one active record via `total: 1`, with the two accidental shells and the superseded record
correctly excluded (only appearing under `?archived=true`).

2026-08-30: after a report that the API-authored template rendered as one unbroken line in
the UI, fetched a UI-hand-edited version of the same template and found it stored
as full HTML (`<p>`, `<br>`, `<ol><li><p>`), not plain text with `\n`. Reproduced that exact
markup shape via `PATCH` (single request, all content fields together) with a numbered list and
a bulleted list, then independently re-fetched via `GET` and confirmed the stored
`editorContentUrl` matched the sent HTML byte-for-byte.

## Applies to

Confirmed for the Email Builder v2 template resource, using a Location OAuth token derived from
the connected agency grant, for both the documented (`Version: v3`) and undocumented
(`/emails/builder`) path families. The content-format findings (HTML required, `\n` inert, list
markup shape) apply to `editorContent` on this resource regardless of which path family wrote
it. SMS template write access remains unconfirmed – no working create/update endpoint was found
for SMS templates in this pass; only listing (`GET /locations/{locationId}/templates?type=sms`)
is confirmed.
