---
id: skill-join-project
title: Join Project
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 1.0.0
script_paths:
  - /shared/skills/join-project/scripts/join.py
  - /shared/skills/join-project/scripts/joining.py
created: 2026-10-21T11:55:16+10:00
updated: 2026-10-21T11:55:16+10:00
owner: brain-owner
skill_refs:
  - /shared/skills/repository-preflight
  - /shared/skills/owner-board
  - /shared/skills/manage-credentials
  - /library/skills/product-feedback
---

# Join Project

Read `/CONTRACT.md` first. A project repository that more than one brain works on (CONTRACT
section 16) carries a **joining manifest**, `brain/JOINING.md`, and this skill lets any brain set
itself up for the project from that manifest, without asking the project's other owners what to
do. It is a core skill because `sync.py` (`SMART-RULE-0034`) nudges with it.

## Purpose

Turn "how do I join this project?" into one command. The manifest says what the project needs
(the working branch, the contract and skill versions, the shared boards, the vault entries each
person makes for themselves, the feedback inbox, the first records to read); `join.py` does every
step that can be done in the joining person's own memory and tells them, exactly, the steps that
are theirs alone (a key is always theirs alone).

## The joining manifest

`<repository>/brain/JOINING.md`: ordinary front matter (`id`, `title`, `type: joining_manifest`,
`contract: /CONTRACT.md`, timestamps, `owner`) plus one `joining:` mapping, then a short human
part. The keys of `joining:`, in the order `join.py` uses them:

| Key | Meaning |
|---|---|
| `repository` | The remote URL to clone. |
| `project_title` | The title the pointer node takes. |
| `working_branch` | The branch everyone works on (`testing`, `main`); checked out when the clone is clean. |
| `minimum_contract_version` | The lowest `contract_version` of `/CONTRACT.md` the project assumes. |
| `skills` | List of `{path, minimum_version}`: brain skills the project relies on; `minimum_version` is compared with the skill's `version` field when the skill states one. |
| `active_skills` | Library skill names the person lists in `active_skills` of their `/memory/OWNER.md`. |
| `pointer_node` | The folder name of the pointer node under `/memory/projects/`. |
| `boards` | List of `{id, label, status}` with `status` relative to the repository (`brain/status`); registered as `<clone folder>:<status>`. |
| `vault_entries` | List of `{entry, fields, purpose}`: entries each person creates in their own vault, by name and field names only, never a value. |
| `feedback` | `{inbox_url, vault_entry, key_page}`: the product's team inbox and where an admin makes a pull key. |
| `read_first` | Repository-relative paths, with `#Heading` anchors, in reading order. |

The manifest holds nothing personal to one owner and no secret: every value in it is the
project's own. The parser reads this subset of YAML only: scalars, lists of scalars (block or
`[a, b]`), lists of one-level mappings, and nested mappings.

## Allowed operations

- read the manifest, this brain's `/memory/OWNER.md`, the pointer nodes under `/memory/projects/`,
  `/memory/skills/owner-board/config/boards.json` and `/memory/skills/product-feedback/config/companion.json`
- run `sync.py --no-merge`; clone the repository under `project_repos_root`; `git fetch` and
  `git checkout <working branch>` in a clean clone
- create the pointer node from `/shared/templates/project-pointer-README.template.md`, or update its
  `repo_url`, `local_path` and `default_branch`; name the node under Folders in `/memory/projects/README.md`
- add a board entry to this brain's `boards.json`
- run the vault's `list` (names only) and print `put-entry` commands

## Required inputs

- a repository URL or the path of a clone; `--dry-run` to see the steps without changes
- a brain root with `/memory/OWNER.md` (`project_repos_root`, `owner_short_name`, `active_skills`)
- for tests: `--vault-listing <file>`, one entry name per line, instead of the vault

## Data sources

- `<repository>/brain/JOINING.md` (canonical, the project's)
- this brain's memory files named above (the person's own)
- `git` for the clone, branch and status; the vault's `list` for entry names

## Scripts or commands

    python shared/skills/join-project/scripts/join.py <url or path> --dry-run   # say, change nothing
    python shared/skills/join-project/scripts/join.py <url or path>             # join
    python shared/skills/join-project/scripts/join.py <path> --json             # the report as JSON
    python -m unittest discover -s shared/skills/join-project/tests -v         # tests (fictional data)

`scripts/joining.py` is the one implementation of the manifest and of what "joined" means,
imported by `join.py` and by `/shared/skills/repository-preflight/scripts/sync.py`.

## Outputs

A report in four parts, printed in this order: **Ready** (what already holds), **Changed** or
**Would change** (what the run did or would do), **Your own steps** (what only the person can do,
each with the exact command or place), **Could not continue** (when the manifest could not be
read). `--json` gives the same four lists.

## Permissions

- writes only inside this brain's own memory and the clone; never another owner's memory, never
  the project's `brain/` files, never a push
- never reads or prints a secret value, a vault field, a `.env` file or the vault file; a vault
  entry is checked by name through `vault_credentials.py list`
- never commits (the person reviews the pointer node and the board entry, then commits their memory)
- never changes protected governance

## Failure behaviour

- no brain root with `/memory/OWNER.md`, no `brain/JOINING.md` in the repository, a manifest
  without a `joining:` mapping, or a failed clone: reported under **Could not continue**, exit 1
- a clone with changed tracked files is not switched to the working branch; the person is told
- a board registered under another status, a contract or skill below the minimum, a skill without a
  version, a locked or missing vault, a companion not configured: each is the person's step, exit 0
- `--dry-run` with a URL that is not cloned stops after saying it would clone, since the manifest
  cannot be read before that

## Logging behaviour

The script writes no log. The person records the join in their memory as they see fit (the
pointer node's `LOG.md` is the usual place) and commits their memory under the inherited Git rules.

## State, knowledge and task update behaviour

The pointer node is the only durable record created; the project's state, rules and knowledge
stay in the repository and are read there (`read_first`). No task is created: the **Your own
steps** list is handed to the person, who makes a task of a step they defer.

#### Folders

##### `scripts/`

Contains `join.py` (the command) and `joining.py` (the manifest reader and the "joined" test).
Canonical, shared, standard library only.

##### `tests/`

Contains `test_join.py`: an invented brain, memory and project in a temporary folder, authors
and names fictional. Run from the brain root.
