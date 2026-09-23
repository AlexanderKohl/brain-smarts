---
id: skill-repository-preflight
title: Repository Preflight
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/tests/test_preflight.py
created: 2026-08-04T23:16:08+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Repository Preflight

## Purpose

Validate Portable AI Brain repository invariants reproducibly before a substantive update is reported complete.

The validator runs from the brain root, the mechanics repository. When the owner's memory repository is checked out at `/memory/` (CONTRACT §3.5), it validates that too, in the same pass: repository-root paths beginning `/memory/` resolve into the memory checkout, and Git change state is read from each repository separately. A missing memory checkout is a warning, not an error, so the mechanics can be validated on their own. A brain kept in one repository, without a separate memory (tasks at `/tasks/`, raw files at `/raw/`), also validates.

## Allowed operations

- read repository Markdown, metadata and Git change state
- validate contract and proposal governance
- print human-readable or JSON results
- replace `/repository-manifest.json` and, when memory is present, `/memory/repository-manifest.json` only when `--write-manifest` is explicitly supplied

The skill must not modify any other repository file.

## Required inputs

- brain root, supplied with `--root` or discovered by moving upward from the current directory (a path inside `/memory/` finds the root above it)
- optional `--write-manifest`
- optional `--json`

## Data sources

- `/CONTRACT.md`
- Markdown YAML front matter in both repositories
- proposals under `/governance/proposals/` and `/memory/governance/proposals/`
- `/memory/tasks/` (or `/tasks/` in a brain without a separate memory)
- Git tracked and untracked change state of each repository when Git is available
- current directory structure of both repositories

## Script

```bash
python shared/skills/repository-preflight/scripts/preflight.py --root .
python shared/skills/repository-preflight/scripts/preflight.py --root . --write-manifest
python -m unittest discover -s shared/skills/repository-preflight/tests -v
```

The tests build fictional two-repository brains in temporary folders and need `git` for the governance cases.

The script uses only the Python standard library.

## Outputs

- pass or fail result
- errors and warnings with repository-root paths
- Markdown-file and identifier counts
- generated manifests when requested: `/repository-manifest.json` holds only mechanics results; `/memory/repository-manifest.json` holds every message that names a `/memory/` path, so owner paths never enter the mechanics repository

## Permissions

- read access to the repository
- write access to the two repository manifests only with `--write-manifest`
- read-only Git commands; no commits, staging or configuration changes

## Failure behaviour

- fail if the contract is missing or malformed
- skip immutable `/memory/raw/` (and `/raw/` in a brain without a separate memory) Markdown evidence (companion source records remain validated)
- fail on missing required Markdown metadata, duplicate IDs, invalid task states, an open task missing from its store's `STATE.md` (`/memory/tasks/STATE.md`) or listed there without its status word (`SMART-RULE-0025`), broken declared references (a `#fragment` after the path must match the start of a Markdown heading in the referenced file), a `/memory/` reference that does not resolve while memory is present, contract-version mismatch in either manifest, or an uncovered protected-governance change in either repository
- warn about undocumented immediate folders, unavailable Git state, an absent memory checkout, a memory folder that is not its own repository, `/memory/` references left unchecked because memory is absent, a missing memory manifest, and a mechanics file whose `owner` is not `brain-owner` (a tripwire for CONTRACT §3.4, not a personal-data scan)
- never repair content silently

## Logging behaviour

The script does not edit activity logs. The calling agent records significant validation-driven changes under the owning node.

## Repository updates

With `--write-manifest`, replace each repository's manifest atomically with its layer, the current contract version, validation time, that repository's counts, errors and warnings. Otherwise make no repository update.

Validation does not itself update state, knowledge or tasks. The calling agent must route any discovered durable issue under the contract.
