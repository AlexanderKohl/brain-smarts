---
id: PROJECT-ID-pointer-readme
title: PROJECT TITLE
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: project_pointer
status: active
parent: /memory/projects
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER
repo_url: https://github.com/ACCOUNT/REPOSITORY
local_path: REPOSITORY
default_branch: main
---

# PROJECT TITLE

Read `/CONTRACT.md` first.

This is a pointer node (CONTRACT §16.1). The project lives in its own repository; its node files
(`README.md`, `RULES.md`, `STATE.md`, `LOG.md`, `KNOWLEDGE.md`) are in that repository's `brain/`
folder, so collaborators receive them. Do not copy the project's state, rules or knowledge here.

## Where it lives

| Item | Location |
|---|---|
| Repository | `repo_url` above; checked out at `local_path` under `project_repos_root` (`/memory/OWNER.md`) |
| Default branch | `default_branch` above |
| Project node files | `brain/` in the repository |
| Owner tasks | `/memory/tasks/`, with this node in `project_refs` |
| Owner-private notes | this node's `KNOWLEDGE.md`, `STATE.md` or `LOG.md`, when needed |
| External systems | NAME each system that holds project data, and what it holds |

Rows are in the order a reader looks for them.

## Why its own repository

Record which CONTRACT §7.1 tests are true, one line of evidence each.

#### Folders

No immediate child folders exist. Owner-private notes, when needed, are the standard node files
in this directory.
