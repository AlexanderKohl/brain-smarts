---
id: shared-skills-readme
title: Core Skills
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: skill_library
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-10-27T16:58:41+10:00
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

##### `command-output/`

Contains the command-output skill: shortens the long output of a recognised shell command (tests, builds, installs, long git diff and log) before an agent reads it, keeps every error line and the exit code, and saves the full output to a local file the last line names. One filter for every model and host: an after-command hook where the host can replace output (Claude Code, Codex, Copilot CLI, Gemini CLI), `scripts/run.py` as a wrapper elsewhere. Each hook is registered once in the host's user settings (`scripts/hook.py settings <host>` prints the entry), never in a repository's committed host file. `SMART-RULE-0047` requires it.

##### `delegate-work/`

Contains the delegated-work protocol: a conductor agent writes bounded packets that reference canonical files, workers return compressed result records, and `scripts/delegation.py` creates, dispatches, validates and summarises a run under `/temp/delegation/runs/`. Workers are isolated, read-only and credential-free by default; at most four per run, depth one. Host dispatch notes in `hosts/`. Not a queue or task system.

##### `join-project/`

Contains the way a brain joins a project repository shared with other brains (CONTRACT §16): the repository's `brain/JOINING.md` manifest says what the project needs, and `scripts/join.py` syncs, checks versions, clones, checks out the working branch, makes the pointer node in the person's own memory, registers the shared boards, checks each vault entry by name and prints the person's own steps (their key, their companion), changing nothing with `--dry-run`. `sync.py` nudges with it. Tests in `tests/` run on a fictional project.

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

##### `product-feedback/`

Contains the product-feedback skill: the triage brief one headless run reads for each feedback packet the Brain Feedback browser extension sends through the owner's local companion (an element, a screenshot or a voice recording of a page), the result and mockup conventions, and the conductor's sweep that turns logged bugs and ideas into cards. The extension and the companion live in their own repository, named by the owner's configuration; this skill holds only what every brain shares. `SMART-RULE-0048` names it.

##### `raw-file-ingestion/`

Contains the canonical shared executable skill for preserving raw files under `/memory/raw/` and creating traceable Markdown source records under `/memory/sources/`. It converts text, CSV, JSON, Markdown, Word and Excel files with the standard library, and PDF through `pdftotext` or `pypdf` where installed, and says in each record what was left out. It must never modify or delete an existing raw file. Tests in `tests/` run on fictional files.

##### `raise-ambition/`

Contains the way-of-working skill `SMART-RULE-0044` requires at the intake of every request: name the outcome behind the request and offer a bigger version – higher (an outcome kept true), deeper (an expert's methods and a harder target) or wider (other fields and roles) – as the first, recommended option of a clarifying question, never widening the work without the user's yes. No scripts, no external access.

##### `release-notes/`

Contains the release-notes skill: one note per change a user would notice, not per commit, kept in each project repository or written by hand for changes made in an outside system; a local page where the owner chooses, edits and holds notes before anything goes out; and a team page that keeps every past release. `scripts/release_notes.py` builds, applies, publishes and checks. `SMART-RULE-0046` requires it.

##### `repository-preflight/`

Contains the canonical validator for metadata, identifiers, references, task state, README folder coverage, contract versioning and accepted governance-change evidence. It validates the mechanics repository and, when present, the memory checkout at `/memory/`, and may update only the generated repository manifests when explicitly requested. Protected governance (CONTRACT §13.2).

##### `skill-exchange/`

Active (`SMART-RULE-0032`). How agents notice a reusable capability and suggest promoting it to a shared skill, offer it upstream as a pull request, tell the owner about new or changed upstream skills, and install a skill from another brain with its provenance recorded. `scripts/skill_exchange.py` does the read-only parts: the upstream comparison, the provenance record and the promotion check.

##### `split-file/`

Contains the method and tools for shortening a large code file without changing what it does (`SMART-RULE-0041`): a destination table first; moves of whole declarations, class methods or route blocks into new files with the text unchanged and only wiring added; refusals for any move that could change behaviour; and a shape snapshot that shows a file's names, exports, classes and routes are the same afterwards, with every new file loaded alone. JavaScript tools in `scripts/js/` (CommonJS; `move.js`, `analyse.js` and `shape.js` also read ES modules) with their own pinned parser (`npm ci` in the folder; `node_modules/` is ignored) and Python tools in `scripts/py/` (standard library only). Tests in `tests/` run on fictional apps.

##### `tasks/`

Contains the task operating procedure and the task-review skill named in CONTRACT §9.1: capture, inbox processing, review, update and close for `/memory/tasks/`, with `scripts/tasks.py` (review, record check, next task number, and `new`, which creates a record from the template and puts it on its board at once).
