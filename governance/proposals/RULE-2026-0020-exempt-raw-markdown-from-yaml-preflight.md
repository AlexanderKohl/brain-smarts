---
id: RULE-2026-0020
title: Exempt immutable /raw/ Markdown from YAML front-matter preflight
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0020
owner: brain-owner
created: 2026-08-12T08:05:00+10:00
updated: 2026-08-12T10:21:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-12T10:20:35+10:00
implemented_at: 2026-08-12T10:20:35+10:00
verified_at: 2026-08-12T10:21:00+10:00
previous_contract_version: 0.6.0
new_contract_version: 0.6.1
target_files:
  - /CONTRACT.md
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/SKILL.md
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0020: Exempt immutable `/raw/` Markdown from YAML front-matter preflight

## Status

**Verified.** the owner explicitly accepted this proposal with “accept” at 2026-08-12T10:20:35+10:00. Exact diffs A–C applied; `contract_version` is `0.6.1`. Repository preflight passed at 2026-08-12T10:21:00+10:00 with no `/raw/` YAML errors.

## Current problem

Contract §11.1 makes `/raw/` immutable source evidence: do not edit, overwrite, normalise or delete it. Some ingested packages are themselves Markdown (for example exported workflow baselines from a client system). Those files correctly have companion source records under `/sources/` with full YAML metadata and `raw_source` links.

Contract §8 / §15 and the repository preflight validator currently require every `*.md` file – including immutable `/raw/` evidence – to begin with YAML front matter. That forces a false choice: either mutate raw evidence (forbidden) or leave repository-wide preflight permanently failing on known immutable files.

Known current failures:

- `/raw/2026/08/source-4a1ca75b3f40/00-README-How-To-Use.md`
- `/raw/2026/08/source-67395db70f81/CHANGELOG.md`

Companion source records already exist and pass metadata validation:

- two companion source records under `/sources/` for exported Markdown baselines (named in the owner's memory copy of this proposal)

## Exact diffs (protected)

### A. `/CONTRACT.md` – clarify §8 opening and §15 bullet

After the sentence `Every Markdown file must begin with YAML front matter.` in §8, insert:

```markdown
Exception: immutable evidence files stored under `/raw/` are exempt. Do not add or rewrite front matter on raw files. Their companion Markdown source records under `/sources/` (and any project-local derivatives) carry the required metadata and must reference the raw path.
```

In §15, replace:

```markdown
- every Markdown file begins with valid YAML front matter
- every Markdown file references `/CONTRACT.md`
```

with:

```markdown
- every Markdown file outside `/raw/` begins with valid YAML front matter
- every Markdown file outside `/raw/` references `/CONTRACT.md`
- immutable `/raw/` Markdown evidence remains unchanged; companion source records under `/sources/` carry metadata and `raw_source`
```

Also set front matter `contract_version: 0.6.1` and update `updated` on acceptance.

### B. `/shared/skills/repository-preflight/scripts/preflight.py`

Add helper after `IGNORED_DIRS`:

```python
def is_raw_evidence_path(path: Path, root: Path) -> bool:
    parts = path.relative_to(root).parts
    return bool(parts) and parts[0] == "raw"
```

Change `markdown_paths` to exclude `/raw/` evidence:

```python
def markdown_paths(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.md")
        if not any(part in IGNORED_DIRS for part in path.relative_to(root).parts)
        and not is_raw_evidence_path(path, root)
    )
```

### C. `/shared/skills/repository-preflight/SKILL.md`

In Failure behaviour, after the first fail bullet, add:

```markdown
- skip immutable `/raw/` Markdown evidence (companion `/sources/` records remain validated)
```

Update the skill `updated` timestamp on acceptance.

## Reason

Aligns preflight with the immutable-raw rule and the existing companion source-record convention, without altering raw bytes.

## Scope and behavioural consequences

- Repository-wide preflight no longer fails solely because ingested raw Markdown lacks front matter.
- Agents must still create `/sources/` records with required metadata for raw Markdown.
- No change to validation of non-raw Markdown, tasks, references, or protected-governance coverage checks.

## Risks / conflicts / migration

- Risk: a mistaken file placed under `/raw/` would no longer be caught for missing front matter. Mitigation: `/raw/` is only for immutable ingestion; ordinary docs do not belong there.
- No content migration. Existing companion source records already satisfy metadata for the known failing files.
- Does not cover unrelated dirty protected files (for example a client project's `RULES.md` if concurrently modified without an accepted proposal).

## Rollback

Revert the three target files to pre-acceptance text and restore `contract_version` to `0.6.0`.

## Planned validation

1. Apply only the accepted diffs.
2. Run `python shared/skills/repository-preflight/scripts/preflight.py --root . --write-manifest`.
3. Confirm the two `/raw/` YAML delimiter errors are gone.
4. Report any remaining unrelated failures separately.

## Acceptance

the owner explicitly accepted with “accept” at 2026-08-12T10:20:35+10:00 in response to the acceptance question authorising implementation of diffs A–C and the contract-version increase from `0.6.0` to `0.6.1`.

## Implementation record

Accepted changes implemented on 2026-08-12T10:20:35+10:00. Target files updated; `contract_version` is `0.6.1`.

Full repository preflight passed at 2026-08-12T10:21:00+10:00 (`contract_version` `0.6.1`; 2344 Markdown files; 0 errors). Proposal status → **verified**.
