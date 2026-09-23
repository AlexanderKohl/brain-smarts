---
name: google-drive-access
description: Find, identify, read, export, download and route authorised files from the user's connected Google Drive, including Google Docs, Sheets, Slides, PDFs and stored files. Use when the user refers to a document or detail that may live in Drive, supplies a Drive URL or file ID, asks to locate Drive material, or wants a Drive source incorporated into a Portable AI Brain project node.
metadata:
  id: skill-google-drive-access
  title: Google Drive Access
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: Google Drive
  canonical_source: /shared/skills/google-drive-access
  project_refs:
    - /memory/projects/credential-management
  created: 2026-08-04T21:16:40+10:00
  updated: 2026-09-23T12:00:00+10:00
---

# Google Drive Access

## Purpose

Use the connected Google Drive app as the authorised discovery and retrieval layer, then route durable imported material through the Portable AI Brain's source and knowledge rules.

## Allowed operations

- Search accessible Drive files and folders.
- Read file metadata and bounded readable content.
- Inspect revisions when the user asks for previous versions or changes.
- Export or download a grounded file when required for an authorised task.
- Route a downloaded snapshot through `/shared/skills/raw-file-ingestion/`.
- Update Drive content or file organisation only when the user explicitly requests the write.

## Inputs

- a Drive, Docs, Sheets or Slides URL or file ID; or concise identifying terms
- the intended detail or operation
- the requesting project node when output should become durable
- the desired snapshot or export format when raw ingestion is required

## Access and credentials

Use the connected Google Drive app first. Its OAuth credentials are managed by the connector and are not exposed to this repository, Python code or the portable vault. Do not request, inspect, copy or duplicate connector tokens.

No vault secret is required for this backend. Record the non-secret connector alias in `/memory/projects/credential-management/data/credential-registry.json`.

If a future environment has no connected Drive app, fail and ask the user whether to configure the connector or explicitly commission a standalone Google OAuth client. Do not create a vault entry, OAuth application or reduced-security fallback implicitly.

## Workflow

1. Read `/CONTRACT.md`, inherited rules and the requesting node.
2. If given a URL or file ID, read its metadata directly.
3. Otherwise search with short, specific title or subject terms.
4. Compare title, type, owner-visible metadata, parent folder and modification time.
5. When multiple plausible files remain, present the candidates and obtain the user's choice before treating one as canonical.
6. Fetch only the content needed for the current request.
7. Cite the grounded Drive title and URL when reporting information.
8. For temporary analysis, do not persist the file merely because it was read.
9. For durable project knowledge, capture a reproducible snapshot:
   - record Drive file ID, URL, MIME type and modification or revision metadata;
   - export a native Google file to an appropriate open snapshot format;
   - download a stored non-native file without conversion;
   - ingest the local snapshot through `/shared/skills/raw-file-ingestion/`;
   - identify any export transformation or fidelity limitation;
   - add project-local source references and only then promote verified facts to `KNOWLEDGE.md`.
10. Update relevant state, logs and tasks without storing credentials.

## File routing

- Google Doc prose work: use the connected Google Docs capability after Drive discovery.
- Google Sheet analysis or editing: use the connected Google Sheets capability.
- Google Slides analysis or editing: use the connected Google Slides capability.
- File discovery, metadata, download, export, revision history and lifecycle operations: remain in Google Drive.

## Permissions and safety

- Treat search and read as authorised only within the user's connected Drive access.
- Preserve existing sharing, parents and content unless the user requests a change.
- Never guess a file ID, URL, folder or revision.
- Never use public web search as a substitute for private Drive discovery.
- Do not expose authenticated download references, bearer URLs or binary data.
- Avoid persisting sensitive document content unless the user requests durable incorporation.

## Outputs

- grounded Drive file metadata and user-facing Drive URL
- requested bounded content or analysis
- an authenticated export or download reference when required
- optional immutable raw snapshot and canonical Markdown source record
- project-local state, log, knowledge or task updates with provenance

## Failure behaviour

- Empty search: broaden terms once with related wording, then report that no grounded file was found.
- Multiple candidates: do not choose silently.
- Authentication failure: request connector reauthorisation; do not fall back to plaintext credentials.
- Export size or type mismatch: choose the correct metadata-grounded download route and report limitations.
- Incomplete conversion: preserve the snapshot, mark conversion incomplete and create a review task when material.
- Write uncertainty: verify Drive metadata or content before retrying.

## Data sources

- The connected Google Drive app (connector-managed OAuth) for search, metadata, content, revisions, export and download.
- `/memory/projects/credential-management/data/credential-registry.json` for the non-secret connector alias.
- Snapshots routed through `/shared/skills/raw-file-ingestion/`, which become `/memory/raw/` files and `/memory/sources/` records.

## Scripts or commands

None. This skill is operated through the host's connected Google Drive capability. Portable, script-based access is `/shared/skills/google-workspace-access/`.

## Repository updates

- Log each durable import in the requesting node's `LOG.md` and, through raw-file ingestion, in `/systems/raw-file-management/LOG.md`. Temporary reads are not logged.
- Add project-local source references for imported material, then promote verified facts to the owning `KNOWLEDGE.md`; update `STATE.md` when an import changes current reality; create a task when conversion is incomplete or a write needs owner confirmation.
- Never store connector tokens, download URLs or credentials in any file.
