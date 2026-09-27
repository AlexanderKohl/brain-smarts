---
id: brain-root-readme
title: Portable AI Brain
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: system
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T19:34:24+10:00
owner: brain-owner
---

# Portable AI Brain

**A file-based working memory and rulebook that any AI coding agent can read, so your work keeps its context from one session, and one model, to the next.**

Most AI sessions start from nothing: you explain your projects, your preferences and your accounts again, and whatever the agent learnt disappears when the chat closes. The Portable AI Brain is a pair of ordinary Git repositories that the agent reads at the start of every session. They hold an operating contract, rules, your tasks and projects, what has been decided and why, and reusable skills for the systems you work with. The agent reads them, does the work, and writes back what changed – so the next session, in any host, starts where the last one stopped.

Agents: read [`/CONTRACT.md`](CONTRACT.md) before using this repository.

## Why use it

<!-- Order: most general benefit first, then the ones that build on it. -->

### Works with any AI host

The brain is Markdown, YAML, JSON and small Python scripts. Nothing depends on one vendor's memory feature or plugin format. Claude Code, Codex and Cursor each find the contract through a one-line pointer file (`CLAUDE.md`, `AGENTS.md`), and any other agent that can read files and run commands can follow it too. You can switch hosts or models mid-project without losing anything.

### You own it

Everything lives in private GitHub repositories under your own account and in folders on your own computer. There is no service to sign up for and no export step: the files are the brain. If you stop using it, you keep a readable archive of your work.

### Knowledge accumulates instead of evaporating

Each project keeps its own `STATE.md` (where things stand), `LOG.md` (what happened, with times), `KNOWLEDGE.md` (what is known and why) and `RULES.md` (standing constraints). A decision made in one session is still there next month, for a different model, with its reasoning. Uploaded files are kept unchanged, with a readable Markdown copy beside them and a record of where they came from.

### One canonical home for everything

Every fact, task, rule and source file has exactly one home; other places link to it rather than copying it. The contract says where each kind of input goes – a passing instruction, durable knowledge, a change of state, a task, a new standing rule – so notes do not drift apart in three places, and a validator checks the structure before each commit.

### Guardrails that hold across sessions

<!-- Order: the order an agent meets them in a typical session. -->

- **Secrets stay in an encrypted vault.** Tokens and client secrets are typed only into a hidden prompt, stored with authenticated encryption outside Git, and injected into a single command when needed. They never appear in chat, files or command lines.
- **External writes are confirmed.** Before anything is sent, created or changed in an outside system, the agent names the exact target account and asks. Email is drafted first, never sent on its own.
- **Governance changes need your acceptance.** The contract, rules, templates and validator are protected: an agent can propose a change, with a summary, the exact diff, risks and a rollback, but it takes effect only when you accept that specific proposal.
- **Checkpoint commits mean nothing is lost.** Work is committed at each logical step, staging named files only, with the host and model in the message. Force pushes, hard resets and skipped hooks are ruled out.

### Reusable skills for common systems

Skills are instructions plus tested scripts for a job or an outside system. They carry no personal data; your own configuration for each lives in your memory.

**Core skills** live here and are always on, because the brain itself depends on them. Alphabetical:

- `delegate-work` – hands bounded pieces of work to parallel worker agents
- `learning-maintenance` – captures, reviews and integrates what the brain learns from use
- `manage-credentials` – the encrypted vault every credentialed skill uses
- `owner-board` – one permanent page showing every request you have made and what needs you
- `problem-recovery` – searches the brain's own knowledge before re-investigating a failure
- `product-development` – the evidence-and-decision process for software work
- `raw-file-ingestion` – keeps uploaded files unchanged with a traceable Markdown copy
- `repository-preflight` – the validator run before every commit
- `skill-exchange` – offers to share what is worth sharing, reports upstream changes, and installs skills from other brains
- `tasks` – capture, review and close tasks, and surface what has come due

**Library skills** live in the separate skill library repository, checked out at `/library/`; you switch on the ones you want, and can take in skills other people have written. Alphabetical:

- `abr-access` – Australian Business Register lookups (ABN, ACN, name search)
- `crm` – a contact register: people, organisations and which of your identities to reply as
- `gohighlevel-access` – HighLevel CRM access across sub-accounts, with rotating tokens in the vault
- `google-workspace-access` – Gmail (draft-first), Calendar, Tasks, Drive and Contacts for several accounts
- `railway-access` – Railway projects, deployments and logs
- `ui-implementation` – rules a live screen must keep while data changes underneath it
- `ui-mockup` – builds a measured preview of a screen for you to refine before anything is built
- `xero-access` – Xero organisation selection and read-only downloads

The full list with what each needs is in [`/SETUP.md`](SETUP.md), [`/shared/skills/README.md`](shared/skills/README.md) and the library's own `skills/README.md`.

### Parallel work with bounded delegation

A conductor agent can hand independent pieces of a job to up to four worker agents at once. Each worker gets a written packet that points at the canonical files, works isolated, read-only and without credentials by default, and returns a short result record. Workers do not start workers of their own, so the work stays traceable.

### Discipline for software work

New software, internal tools and feature changes follow an investment-proportionate process: the agent gathers evidence and prepares decisions for you at defined gates, considers building versus buying, and has an independent model review the plan and the release. Screens are mocked up and refined with you before they are implemented. The rules also ask for security by design, tests that demonstrate behaviour, and one implementation per side effect.

### Shareable by design

The mechanics – contract, generic rules, core skills, templates – live in this repository, and optional skills in a separate skill library; neither contains personal data, so anyone can adopt them unchanged. Everything about you lives in a separate private memory repository. Large projects live in their own repositories, where collaborators get the project's own brain files without seeing your memory.

## How it fits together

The brain is four layers, each its own repository. One working tree holds the first three; project repositories sit beside it.

```text
C:\dev\                        project repositories root (your choice)
├── brain\                     brain-smarts – this repository; the brain root "/"
│   ├── CONTRACT.md            the operating contract every agent reads first
│   ├── RULES.md               generic rules any owner could adopt
│   ├── shared\skills\         core skills the brain depends on (no personal data)
│   ├── library\               brain-skills – the skill library, ignored by this repository
│   │   └── skills\            optional skills: outside systems and ways of working
│   └── memory\                brain-memory – your private repository, ignored by this one
│       ├── OWNER.md           who the brain works for
│       ├── RULES.md           your own standing preferences
│       ├── tasks\  projects\  raw\  sources\  ...
└── example-project\           a project repository, with its own brain\ folder
```

1. **Smarts** (this repository) – how the brain works. Identical for every owner.
2. **Skill library** (`/library/`) – optional skills, shareable like the smarts; you use the ones you switch on.
3. **Memory** (`/memory/`) – what the brain knows about you: profile, rules, tasks, projects, contacts, files, state and history.
4. **Project repositories** – bodies of work with their own lifecycle; memory keeps a small pointer to each.

Rules inherit downwards – contract, generic rules, your rules, then each project's rules – and a lower level may add constraints but never override a higher one. See [`/CONTRACT.md`](CONTRACT.md) §3.4 to §3.6 and §16.

## Getting started

Open an AI host – Claude Code, Codex or Cursor – and paste the prompt from [`/SEED_PROMPT.md`](SEED_PROMPT.md), with this repository's address filled in. Nothing else needs to be installed first.

The agent checks for Git, Python and the GitHub CLI and installs whatever is missing after your yes. Signing in to GitHub stays with you: it tells you the command to run in your own terminal. It then clones the smarts, reads the contract and follows [`/SETUP.md`](SETUP.md). It makes your private copy of the smarts and a new private memory from the skeleton, interviews you for your profile, lets you choose skills, sets up the vault and any accounts, wires your host to the contract and validates everything. It asks only what it cannot detect, always with a suggested answer, and hands you the steps that must stay yours – choosing the vault passphrase, pasting secrets into a hidden prompt, registering apps and approving sign-ins. Progress is recorded as it goes, so the same prompt resumes an unfinished setup.

## Staying up to date and contributing

Your AI handles both (`SMART-RULE-0032`, the `skill-exchange` skill), and asks before every step:

- **Improvements from upstream.** Your smarts repository is your own private copy (or a GitHub fork) with this repository kept as the `upstream` remote, push disabled. About once a week, at the start of a session, the agent checks `upstream` and tells you in a short numbered list what changed in the skills you use, in the core skills and in governance. It merges only what you say yes to; a change to protected governance comes to you as a proposal.
- **Sharing what you built.** When the agent notices that something built for one of your projects would help other people – a skill, a fix, a lesson – it suggests generalising it and offering it back as a pull request with a proposal, the personal-data check's result and passing tests. Nothing leaves your machine until the check reports no personal data and you say yes to that contribution. The upstream maintainer accepts or declines it; on your own machine a new optional skill does nothing until you list it in `active_skills` in your `/memory/OWNER.md`.

To do it by hand instead:

```bash
cd <brain_root>
git fetch upstream
git merge upstream/main
python shared/skills/repository-preflight/scripts/preflight.py --root .
```

## What it is not

<!-- Order: the misconceptions newcomers raise most often, first. -->

- **Not a hosted service.** There is no server, account or subscription. The brain is files on your computer and in your GitHub account.
- **Not a runtime or framework.** It does not run agents, schedule them or wrap an API. Your AI host does the work; the brain tells it how and remembers the results.
- **No telemetry.** Nothing in the brain reports usage anywhere. Its scripts talk only to the outside systems you connect and confirm. (Your AI host's own data handling is between you and its provider.)

## Navigation

Entries are in reading order.

- `/SEED_PROMPT.md`: the short prompt a new person pastes into their agent to start a brain
- `/SETUP.md`: the resumable guided setup the agent follows (prerequisites, repositories, skill activation, credentials, host wiring, permissions)
- `/CONTRACT.md`: canonical operating contract (read this first)
- `/BOOTSTRAP.md`: portable entry and contract-discovery instructions
- `/AGENTS.md`: cross-tool agent entry pointer to the contract
- `/CLAUDE.md`: Claude Code entry pointer to the contract
- `/RULES.md`: generic root rules; the owner layer is `/memory/RULES.md`
- `/repository-manifest.json`: generated by the preflight validator; records the contract version and validation result for this repository
- `/memory/OWNER.md`: the owner profile (in the memory repository)
- `/memory/STATE.md`, `/memory/LOG.md`, `/memory/KNOWLEDGE.md`: brain-wide state, history and knowledge (in the memory repository)

#### Folders

##### `governance/`

Describes how a change to the mechanics layer is proposed (`governance/proposals/`): changes to `/CONTRACT.md`, `/RULES.md`, shared governance schemas and templates, bootstrap files and the preflight validator. Proposals are not active governance; only the implemented content of the target file is. Owner-layer proposals, and an owner's record of mechanics decisions, live in `/memory/governance/proposals/`.

##### `library/`

The skill library: a **separate repository**, checked out here and listed in this repository's `.gitignore`. Never commit anything under it to this repository. It holds the optional skills – outside systems and ways of working – each with its own `SKILL.md`, scripts and tests, and no personal data (CONTRACT §3.4). See [`/SETUP.md`](SETUP.md) step B3a to check it out.

##### `memory/`

The owner's memory: a **separate repository**, checked out here and listed in this repository's `.gitignore`. Never commit anything under it to this repository. It holds the owner profile, owner-layer rules, tasks, projects, contacts, raw files, sources, outbox, boards and the brain-wide state, log and knowledge. When absent, agents work on the mechanics only (see [`/SETUP.md`](SETUP.md) step B4 to create one).

##### `shared/`

Contains the core skills the brain depends on, schemas and templates, including the skeleton for a new owner's memory (`shared/templates/memory-skeleton/`). Reusable resources belong here and must be referenced rather than copied into projects. Owner configuration for a skill lives in `/memory/skills/<skill>/`, never here.

##### `systems/`

Contains canonical persistent operating-system nodes without a natural completion date, currently raw-file management. The mechanism lives here; owner-specific operating history for a system lives at the same path under `/memory/systems/`.

##### `temp/`

Local, ephemeral, regenerable runtime artefacts (delegation run folders, probe output). Ignored by Git in every brain repository and absent from a fresh clone. Safe to delete; never store credentials or durable knowledge here.
