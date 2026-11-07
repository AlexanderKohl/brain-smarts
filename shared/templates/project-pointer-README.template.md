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
repo_visibility: null
---

# PROJECT TITLE

Read `/CONTRACT.md` first.

This is a pointer node (CONTRACT §16.1). The project lives in its own repository; its node files
(`README.md`, `RULES.md`, `STATE.md`, `LOG.md`, `KNOWLEDGE.md`) and its `tasks/`, `sources/`,
`raw/` and `data/` are in that repository's `brain/` folder, so collaborators receive them. This
node holds only what the owner keeps private about the project. Do not copy the project's state,
rules, knowledge, tasks or sources here.

`repo_visibility` is optional: `private` or `public` once known, else `null`. Everything in the
repository's `brain/` can be read by everyone who can read the repository.

## Where it lives

| Item | Location |
|---|---|
| Repository | `repo_url` above; checked out at `local_path` under `project_repos_root` (`/memory/OWNER.md`) |
| Default branch | `default_branch` above |
| Project node files | `brain/` in the repository |
| Project tasks | `brain/tasks/` in the repository, open and completed alike |
| Project sources | `brain/sources/` and `brain/raw/` in the repository |
| Owner-private tasks | this node's `tasks/`, when needed |
| Owner-private sources | this node's `sources/` and `raw/`, when needed |
| Owner-private notes | this node's `KNOWLEDGE.md`, `STATE.md` or `LOG.md`, when needed |
| Private notes about a repository task | `/memory/tasks/private/<task id>.md` |
| External systems | NAME each system that holds project data, and what it holds |

Rows are in the order a reader looks for them.

## Why its own repository

Record which CONTRACT §7.1 tests are true, one line of evidence each.

#### Folders

List each folder that exists, alphabetically, and remove the entries for folders this node does
not have yet. Each holds only what the owner keeps private about the project and is never drawn
into the repository.

##### `raw/`

Contains the immutable raw files of the owner's private sources about the project, in the
year, month and source-id layout of CONTRACT §11.1.

##### `sources/`

Contains the Markdown source records of the owner's private sources about the project; each
references its raw file in `raw/`.

##### `tasks/`

Contains the owner's private task store for the project (CONTRACT §9), in the layout of
`/shared/templates/node-tasks-README.template.md`. The project's own tasks are in the
repository's `brain/tasks/`.
