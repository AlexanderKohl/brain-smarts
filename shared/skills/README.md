---
id: shared-skills-readme
title: Core Skills
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: skill_library
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-10-01T07:50:51+10:00
---

# Core Skills

Read `/CONTRACT.md` first.

The core skills: those the brain itself depends on – a skill a `SMART-RULE` or the contract requires, or that another core skill calls (CONTRACT §3.4). Every other reusable skill is in the skill library, `/library/skills/`.

Each skill directory contains a `SKILL.md` defining purpose, permissions, inputs, scripts, outputs, failure handling and repository updates.

Skills are mechanics: they hold instructions, scripts, tests and generic knowledge about the external systems they reach, and no personal data (CONTRACT §3.4). Owner configuration, data and owner-specific notes for a skill live in `/memory/skills/<skill>/`, mirroring the skill's inner layout; a script finds them by locating the brain root and joining `memory/skills/<skill>/`, never through a hard-coded machine path (CONTRACT §3.5). Results belong to the requesting node.

Plaintext credentials and recovery material must remain outside the repository. An approved encrypted credential container must be excluded from Git.

#### Folders

Folders are alphabetical.

##### `code-map/`

Contains the code map: a deterministic map of a code repository (files, functions, imports, routes, UI calls, database columns, data fields, templates, settings and environment variables) built from the code by fixed rules, `show` and `find` for agents, a generated inventory, checks that fail when a link breaks, and a report-only list of code no longer used. Node scripts with their own pinned parser packages (`npm ci` in the folder; `node_modules/` is ignored). A candidate core skill: it becomes core when a rule requires it, and moves to the skill library if none does. Tests in `tests/` run on a fictional fixture.

##### `delegate-work/`

Contains the delegated-work protocol: a conductor agent writes bounded packets that reference canonical files, workers return compressed result records, and `scripts/delegation.py` creates, dispatches, validates and summarises a run under `/temp/delegation/runs/`. Workers are isolated, read-only and credential-free by default; at most four per run, depth one. Host dispatch notes in `hosts/`. Not a queue or task system.

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

##### `raw-file-ingestion/`

Contains the canonical shared executable skill for preserving raw files under `/memory/raw/` and creating traceable Markdown source records under `/memory/sources/`. It must never modify or delete an existing raw file.

##### `repository-preflight/`

Contains the canonical validator for metadata, identifiers, references, task state, README folder coverage, contract versioning and accepted governance-change evidence. It validates the mechanics repository and, when present, the memory checkout at `/memory/`, and may update only the generated repository manifests when explicitly requested. Protected governance (CONTRACT §13.2).

##### `skill-exchange/`

Active (`SMART-RULE-0032`). How agents notice a reusable capability and suggest promoting it to a shared skill, offer it upstream as a pull request, tell the owner about new or changed upstream skills, and install a skill from another brain with its provenance recorded. `scripts/skill_exchange.py` does the read-only parts: the upstream comparison, the provenance record and the promotion check.

##### `split-file/`

Contains the method and tools for shortening a large code file without changing what it does (`SMART-RULE-0041`): a destination table first; moves of whole declarations, class methods or route blocks into new files with the text unchanged and only wiring added; refusals for any move that could change behaviour; and a shape snapshot that shows a file's names, exports, classes and routes are the same afterwards, with every new file loaded alone. JavaScript (CommonJS) tools in `scripts/js/` with their own pinned parser (`npm ci` in the folder; `node_modules/` is ignored) and Python tools in `scripts/py/` (standard library only). Tests in `tests/` run on fictional apps.

##### `tasks/`

Contains the task operating procedure and the task-review skill named in CONTRACT §9.1: capture, inbox processing, review, update and close for `/memory/tasks/`, with `scripts/tasks.py` (review, record check, next task number, and `new`, which creates a record from the template and puts it on its board at once).
