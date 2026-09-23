---
id: shared-skills-readme
title: Shared Skills
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: skill_library
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T16:53:00+10:00
---

# Shared Skills

Read `/CONTRACT.md` first.

Each skill directory contains a `SKILL.md` defining purpose, permissions, inputs, scripts, outputs, failure handling and repository updates.

Skills are mechanics: they hold instructions, scripts, tests and generic knowledge about the external systems they reach, and no personal data (CONTRACT §3.4). Owner configuration, data and owner-specific notes for a skill live in `/memory/skills/<skill>/`, mirroring the skill's inner layout; a script finds them by locating the brain root and joining `memory/skills/<skill>/`, never through a hard-coded machine path (CONTRACT §3.5). Results belong to the requesting node.

Plaintext credentials and recovery material must remain outside the repository. An approved encrypted credential container must be excluded from Git.

#### Folders

Folders are alphabetical.

##### `abr-access/`

Contains the ABR ABN Lookup JSON web-services skill (vault-stored authentication GUID). Use for ABN/ACN validation and name search whenever an Australian Business Number is required. Docs: https://abr.business.gov.au/Tools/WebServices. Never commit the GUID.

##### `crm/`

Contains the contact register (CRM) skill: the contact and persona model, procedures for creating a contact on first encounter, deduplication, newsletter handling, persona-to-account binding and directory merges, the templates for a CRM node, and `scripts/crm_check.py` (read-only find, validate and duplicate checks). The register itself and its rules live in the owner's memory; the skeleton ships a starter node at `projects/contacts/`.

##### `delegate-work/`

Contains the delegated-work protocol: a conductor agent writes bounded packets that reference canonical files, workers return compressed result records, and `scripts/delegation.py` creates, dispatches, validates and summarises a run under `/temp/delegation/runs/`. Workers are isolated, read-only and credential-free by default; at most four per run, depth one. Host dispatch notes in `hosts/`. Not a queue or task system.

##### `gohighlevel-access/`

Contains the canonical executable HighLevel agency OAuth manager and reusable API client. It stores rotating Company tokens only in the encrypted portable vault, derives Location tokens in memory, and keeps project permissions and results local to the requesting node. Downloaded HighLevel Marketplace OpenAPI snapshots used to ground request shapes live under `gohighlevel-access/openapi/` (public vendor documentation, not live sub-account data).

##### `google-workspace-access/`

Contains the canonical portable Google Workspace skill (Gmail, Calendar, Tasks, Drive, Contacts) with multi-account vault OAuth, persona/account resolution against the owner's contact register in memory, draft-first email, local scripts, and an optional SQLite local sync layer for Gmail indexing and Google Tasks mirroring (`google_sync_ctl.py` worker; flags default off). Does not use host marketplace/MCP Google connectors.

##### `learning-maintenance/`

Portable capture, research, cross-model review, retirement, single-writer integration and weekly digest under SMART-RULE-0028. Agents read the compact discovery index at task entry. No vendor dependency or active concurrency prototype.

##### `manage-credentials/`

Contains the canonical shared passphrase-encrypted vault skill for hidden input, ephemeral child-process injection and rotating OAuth JSON storage. It uses authenticated encryption, keeps the passphrase out of storage and excludes the encrypted vault from Git.

##### `owner-board/`

Contains the owner board: one permanent link showing the owner every request they have made and what needs them. Cards are Markdown records under `<node>/status/cards/`, the page is generated from them by the one shared implementation in `scripts/` (configured per owner in `/memory/skills/owner-board/config/boards.json`), and `reconcile.py` compares it against Git on every regeneration. The owner's verdict comes back as a saved file, and a card is closed only by the owner. The same boards show the owner's tasks, drawn from `/memory/tasks/` by `task_board.py`: each open task on its first project's board, otherwise on the personal board.

##### `problem-recovery/`

Targeted brain-first diagnosis, bounded recovery and evidence capture with narrow owner escalation. Uses learning-maintenance for canonical integration.

##### `product-development/`

Contains the investment-proportionate product-development process for new and existing software, internal tools and feature iterations. The agent gathers evidence and prepares gate decisions for the owner, considers internal and commercial routes, and uses independent-model reviews at material planning and release checkpoints.

##### `railway-access/`

Contains the Railway GraphQL access skill (vault-stored account or workspace API token). Use to list projects, resolve the current/latest deployment ID, and fetch timeframe-bounded deploy/build/HTTP logs with Railway filter syntax. Prefer one account token for all-project access; do not use per-project tokens for brain-wide log reads. Docs: https://docs.railway.com/integrations/api. Never commit the token.

##### `raw-file-ingestion/`

Contains the canonical shared executable skill for preserving raw files under `/memory/raw/` and creating traceable Markdown source records under `/memory/sources/`. It must never modify or delete an existing raw file.

##### `repository-preflight/`

Contains the canonical validator for metadata, identifiers, references, task state, README folder coverage, contract versioning and accepted governance-change evidence. It validates the mechanics repository and, when present, the memory checkout at `/memory/`, and may update only the generated repository manifests when explicitly requested. Protected governance (CONTRACT §13.2).

##### `skill-exchange/`

Proposed, not active (`PROPOSAL-skill-exchange`). How agents notice a reusable capability and suggest promoting it to a shared skill, offer it upstream as a pull request, tell the owner about new or changed upstream skills, and install a skill from another brain with its provenance recorded. `scripts/skill_exchange.py` does the read-only parts: the upstream comparison, the provenance record and the promotion check.

##### `tasks/`

Contains the task operating procedure and the task-review skill named in CONTRACT §9.1: capture, inbox processing, review, update and close for `/memory/tasks/`, with `scripts/tasks.py` (review, record check, next task number, and `new`, which creates a record from the template and puts it on its board at once).

##### `ui-implementation/`

Contains the rules a live screen must hold once data is arriving underneath it: a renderer removes
only what it made, a refresh changes what a person sees and never what they chose, work in
progress outranks freshness, and the rule goes where the next author cannot fail to inherit it.
Every rule carries a short rationale. No scripts; it governs work in a product
repository and is the implementation half of `ui-mockup/`.

##### `ui-mockup/`

Contains the UI mockup skill: builds a preview from a product's own stylesheets, measures it in the
browser instead of judging it by eye, and holds the change there until the owner has refined it.
Nothing it previews may be implemented in components or pushed before the owner responds to the
mockup. `scripts/build_mockup.py` assembles the harness inside `temp/ui-mockup/`.

##### `xero-access/`

Contains the canonical shared Xero OAuth, organisation-selection and read-only download skill. Tokens and credentials remain external; retrieved outputs belong under the requesting node with provenance metadata.
