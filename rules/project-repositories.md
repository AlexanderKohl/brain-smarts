---
id: brain-rules-project-repositories
title: Rule pack: project-repositories
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-26T14:35:03+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: project-repositories

Generated from `/CONTRACT.md` and `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim,
the contract sections and the rules of one situation, so that they are read together. A section's
canonical home stays `/CONTRACT.md`, and a rule's `/RULES.md`.

Read the whole file before: working in a project repository: reading or writing its `brain/` folder, committing or pushing there, or joining one.

## 16. External project repositories

A body of work that passes a test in section 7.1 lives in its own repository, checked out as a sibling of the brain root under the owner's `project_repos_root` (see `/memory/OWNER.md`). It stays part of the brain: this contract governs it, and an agent working inside it bootstraps from the brain root.

### 16.1 Pointer node in memory

Memory keeps one small pointer node per project repository, at `/memory/projects/<node>/`. Its `README.md` carries, in front matter or a short table:

- `repo_url`: the repository's remote URL
- `local_path`: the checkout path, relative to `project_repos_root` or absolute
- `default_branch`: the branch that holds released or agreed work
- what lives where: which of the project's records are in the repository's `brain/` folder, which are in memory, and which external systems hold the rest

The pointer node may also hold what the owner keeps private about the project, in the layout of section 3.1: notes in its own `KNOWLEDGE.md`, `STATE.md` or `LOG.md`, private tasks in `tasks/`, and private sources in `sources/` and `raw/`. It holds nothing else: no copy of the project's state, rules, knowledge, tasks or sources.

Tasks about the project, open and completed alike, are kept in the repository's `brain/tasks/` (sections 9 and 16.2), except the owner's private tasks and private notes about it. A project with collaborators may also run its own issue tracker; a task then links the issue instead of copying it.

### 16.2 The project's own node files

The project's node files – `README.md`, `RULES.md`, `STATE.md`, `LOG.md` and `KNOWLEDGE.md`, and its `tasks/`, `sources/`, `raw/` and `data/` in the layout of section 3.1 – live inside the project repository in a `brain/` folder, so a collaborator who clones the repository receives them. They follow this contract: YAML front matter with `contract: /CONTRACT.md`, the standard file meanings of section 4, and the timestamp rules of section 8.2. Their `RULES.md` inherits `/CONTRACT.md`, `/RULES.md` and `/memory/RULES.md` for the owner's agents; a collaborator without the brain reads it as the project's own rules. A board the owner-board skill keeps for the project lives there too, in `brain/status/`, when more than one brain works on it. A project shared between brains also carries `brain/JOINING.md`, a joining manifest that names the repository, the working branch, the contract and skill versions it assumes, its shared boards, the vault entries each person creates for themselves (names only) and the records to read first; a brain joins from it with `/shared/skills/join-project/`, in its own memory, and never by copying another brain's memory. Every such brain is a peer: its records carry its author and are rewritten by no other author, a task record excepted as below, and its generated pages are not committed. Any brain that works on the project may change a task record in `brain/tasks/`; every change adds a History entry `- <timestamp> – <author>: <what changed>`, so each edit names the brain that made it, and a Git conflict in a record is resolved by hand, keeping the History entries of both sides in time order. A task whose `owner` has left the project is reassigned by the repository's maintainer, with a History entry. Each owner's private tasks, notes and sources about the project stay in that owner's memory (section 16.1) and are never drawn into the repository.

References from a project repository's `brain/` files to its own files use paths relative to the repository root, prefixed with the repository name and a colon when a reader outside the repository needs them (for example `example-repo:brain/STATE.md`). References into the brain use repository-root paths such as `/shared/skills/<skill>/`. A project repository never references `/memory/` paths, because a collaborator cannot resolve them.

### 16.3 Validation and commits

The repository preflight validator validates the mechanics repository and, when present, `/library/` and `/memory/`. A project repository runs its own checks; its `brain/` folder follows section 15 where it applies. Commits and pushes in a project repository follow the inherited Git rules and are reported separately from the brain's own repositories. A brain that shares a project repository with another pulls before it builds and before it pushes, and derives shared state from the repository's records rather than carrying its own copy.
