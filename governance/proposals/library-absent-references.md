---
id: PROPOSAL-library-absent-references
title: A reference into the skill library is a warning when the library is not checked out
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-11-10T08:40:03+10:00
updated: 2026-11-10T08:40:03+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 3.2.0
new_contract_version: 3.2.0
target_files:
  - /shared/skills/repository-preflight/SKILL.md
  - /shared/skills/repository-preflight/scripts/preflight_references.py
---

# A reference into the skill library is a warning when the library is not checked out

## Summary

The repository preflight runs in CI on the mechanics repository alone: the memory and the skill
library are separate repositories and are not checked out there. A declared reference into
`/memory/` is then a warning, "not checked: memory checkout absent". A declared reference into
`/library/` has no such path and is an error. Every mechanics file that names a library skill
therefore fails CI, although the same commit passes on a computer that has the library.

After this change a `/library/` reference is a warning when the library is not checked out, and
is checked exactly as today when it is.

## Current problem

- CI on the mechanics `main` has failed on every push since 21 October 2026. The last passing run
  was on 20 October 2026.
- At the current tip the run reports four errors, all of this kind: two closed proposals whose
  `target_files` name `/library/skills/README.md`, and two core skills whose `skill_refs` name
  `/library/skills/ui-mockup`.
- Because the preflight step fails, the two unit-test steps after it are skipped. A real failure
  on `main` would not be noticed.
- The workflow file already says "memory and library are absent here, which preflight allows".
  The validator does not do what that line says.

## Current wording

`/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*, the bullet that begins "warn
about undocumented immediate folders":

> warn about undocumented immediate folders, unavailable Git state, an absent memory checkout, a
> memory folder that is not its own repository, `/memory/` references left unchecked because
> memory is absent, a missing memory manifest, a declared reference to a git-ignored file absent
> from this checkout (a local-only recording or scratch run), and a mechanics file whose `owner`
> is not `brain-owner` (a tripwire for CONTRACT §3.4, not a personal-data scan)

## Proposed wording or exact diff

### 1. `/shared/skills/repository-preflight/SKILL.md`, *Failure behaviour*

In the bullet quoted above, after "`/memory/` references left unchecked because memory is
absent," insert:

> `/library/` references left unchecked because the skill library is absent,

The bullet then reads:

> warn about undocumented immediate folders, unavailable Git state, an absent memory checkout, a
> memory folder that is not its own repository, `/memory/` references left unchecked because
> memory is absent, `/library/` references left unchecked because the skill library is absent, a
> missing memory manifest, a declared reference to a git-ignored file absent from this checkout (a
> local-only recording or scratch run), and a mechanics file whose `owner` is not `brain-owner` (a
> tripwire for CONTRACT §3.4, not a personal-data scan)

### 2. `/shared/skills/repository-preflight/scripts/preflight_references.py`

```diff
@@ -9,7 +9,7 @@ from __future__ import annotations
 import re
 from pathlib import Path
 from typing import Any
-from preflight_base import MEMORY_PREFIX, in_memory, memory_root, library_root, layer_of, Result, root_path, git_ignored, is_template_path, is_own_repository
+from preflight_base import LIBRARY_PREFIX, MEMORY_PREFIX, in_memory, memory_root, library_root, layer_of, Result, root_path, git_ignored, is_template_path, is_own_repository
 from preflight_tasks import repository_checkouts, resolve_repository_ref
 
 
@@ -86,6 +86,7 @@ def validate_declared_references(
     root: Path, records: dict[Path, dict[str, Any]], result: Result
 ) -> None:
     memory_present = memory_root(root) is not None
+    library_present = library_root(root) is not None
     checkouts = None
     for path, metadata in records.items():
         display = root_path(path, root)
@@ -120,6 +121,13 @@ def validate_declared_references(
                         f"{display}: {key} reference {value} not checked: memory checkout absent"
                     )
                     continue
+                if path_part.startswith(LIBRARY_PREFIX) and not library_present:
+                    # The skill library is a separate checkout (CONTRACT 3.5); a run on the
+                    # mechanics alone, such as CI, cannot say whether the target exists.
+                    result.warnings.append(
+                        f"{display}: {key} reference {value} not checked: library checkout absent"
+                    )
+                    continue
                 if not target.exists():
                     if key == "target_files" and str(metadata.get("status", "")) in CLOSED_PROPOSAL:
                         # A closed proposal's target_files record history, never rewritten
```

### 3. `/shared/skills/repository-preflight/tests/test_preflight.py` (not protected)

Two tests in `LayoutTests`:

- `test_library_reference_is_a_warning_when_the_library_checkout_is_absent`: a `skill_refs` entry
  and a closed proposal's `target_files` entry, both into `/library/`, give no error and two
  "library checkout absent" warnings.
- `test_library_reference_is_checked_when_the_library_checkout_is_present`: with a `library/`
  folder present, a `skill_refs` entry naming a skill that does not exist is still the error
  "broken skill_refs reference".

## Reason

The library is a separate repository by design (CONTRACT §3.5), as the memory is. A run that
cannot see it cannot say whether a target exists, so the honest result is "not checked", which
is what the validator already says for memory. CI then turns green and guards `main` again.

## Scope and behavioural consequences

- Only a run without a `library/` folder changes: CI, and a fresh clone of the mechanics before
  the library is cloned. There, `/library/` references in `skill_refs`, `target_files` and every
  other declared-reference field become warnings.
- A run with the library checked out is unchanged: a broken `/library/` reference is an error.
  Every session copy and the shared checkout have the library, so every merge to `main` is still
  checked in full before it is pushed.
- The contract is unchanged; no rule number is assigned.

## Risks and conflicts

- A broken `/library/` reference is no longer caught by CI. It is caught by the local preflight
  that `session.py finish` runs before every push. Size: low.
- A person who works on the mechanics without the library sees warnings where they saw errors.
  That is the same position as for memory today.
- No conflict with another open proposal: none lists these two files.

## Migration

None. No existing file changes its meaning.

## Rollback

Revert the commit that applies the two target files and the tests. CI returns to its present
failing state.

## Validation

Carried out on the candidate diff on 10 November 2026, before this proposal was written:

- the full preflight test suite passes with the two new tests in it (249 tests);
- in a clean checkout of the mechanics alone, as CI has it, the preflight reports `PASS` with
  eight "library checkout absent" warnings and no error.

At implementation: the full preflight test suite, the preflight in the session copy, and the CI
run on `main` after the push, which must be green.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal. Do not treat silence, adjacent approval or general agreement as acceptance.

## Implementation record
