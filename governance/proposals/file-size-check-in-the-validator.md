---
id: PROPOSAL-file-size-check-in-the-validator
title: The validator checks the code-file size limit, and preflight.py is split to hold it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
created: 2026-10-01T08:26:14+10:00
updated: 2026-10-01T08:50:17+10:00
accepted_by: brain-owner
accepted_at: 2026-10-01T08:50:17+10:00
implemented_at: 2026-10-01T08:50:17+10:00
owner: brain-owner
rule_id: SMART-RULE-0041
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/scripts/preflight_base.py
  - /shared/skills/repository-preflight/scripts/preflight_references.py
  - /shared/skills/repository-preflight/scripts/preflight_governance.py
  - /shared/skills/repository-preflight/scripts/preflight_manifest.py
  - /shared/skills/repository-preflight/scripts/file_sizes.py
  - /shared/skills/repository-preflight/tests/test_file_sizes.py
  - /shared/skills/repository-preflight/tests/test_robust_hooks.py
  - /shared/skills/repository-preflight/SKILL.md
  - /.code-map/sizes.json
---

# The validator checks the code-file size limit, and preflight.py is split to hold it

Read `/CONTRACT.md` first. The exact diff is the branch `proposal/file-size-check` in the mechanics.

## Summary

What will be different:

- **For agents:** a commit in the mechanics or the skill library fails when it adds a code file over
  800 lines, or makes a recorded oversized file larger. The error names the file, its lines and what to
  do. Today the limit (`SMART-RULE-0041`, accepted) is written down but nothing in the brain checks it.
- **For the owner:** nothing to do. The brain's own code keeps to the limit it asks of project
  repositories.
- **The validator's own file:** `preflight.py`, 934 lines and itself over the limit, is split into
  five files with its text unchanged, so the new check has room. It becomes 464 lines.

## What changes

1. **A new check, `file_sizes.py`**, called once from `preflight.run()`. For each repository that has
   adopted the limit (the mechanics, the library and, if it ever keeps one, the memory), it reads the
   record `sizes.json` from the folder `code-map.config.json` names (`.code-map/` in the mechanics and
   the library, adopted on 1 October 2026). It counts code files as the code map does: git's list of
   files, the code map's ignored and size-exempt patterns and its code extensions, the repository's
   own extra patterns, and lines counted the same way. It reports:
   - `/<file>: N lines, over the 800-line limit; split it before committing, since a new file over the
     limit is not recorded (SMART-RULE-0041)`;
   - `/<file>: grew from its recorded X lines to Y; move code out of it rather than into it
     (SMART-RULE-0041)`.
   A repository without a record is not checked.
2. **`preflight.py` split** with the split-file skill, every moved line unchanged, in four moves. It
   imports the moved names back, so everything that uses `preflight` sees the same names:
   - `preflight_base.py`: where each repository is, the git helpers, and the `Result` every check
     writes to;
   - `preflight_references.py`: declared references and mechanics references into memory;
   - `preflight_governance.py`: the protected-governance check;
   - `preflight_manifest.py`: the manifests and the personal-data check.
   The new lines in `preflight.py` are the four import statements and the two lines that call the new
   check.
3. **Tests:** `test_file_sizes.py` (13 tests on fictional repositories: each failure on purpose, each
   exemption, and a comparison with the code map's own lists so the two cannot drift). One test in
   `test_robust_hooks.py` read `preflight.py`'s text for a line that has moved; it now reads
   `preflight.py` and the modules split from it. Its assertions are unchanged.
4. **`SKILL.md`** of the validator describes the new check and the modules.
5. **The mechanics' size record** loses `preflight.py`, now within the limit; it is empty.

## Reason

`SMART-RULE-0041` says the limit is checked where every change to a repository is checked. In the
brain that is the validator: the pre-commit hook and CI both run it. Until it does, the rule's last
bullet applies, and nothing but care stops an oversized file from growing.

## Scope and consequences

- Every commit in the mechanics and the library, through the pre-commit hook and CI.
- Adds about a second to a validator run (it reads each code file once).
- The five other oversized files were split on 1 October without touching governance; the library's
  record is empty and the mechanics' will be after this change. So the check starts with nothing
  recorded: any new file over 800 lines fails.

## Risks and conflicts

- **Counting could drift from the code map's** if either changes its patterns. A test compares the
  lists and fails when they differ.
- **A moved line could behave differently in its new file.** The split-file skill refused every move
  that could (names left behind, `global`, tests patching a moved name, effects at load). The shape of
  `preflight.py` (every name, with function source hashes) is unchanged, and the validator's tests
  pass (107, including the 13 new ones).
- **No conflict** with other rules. `SMART-RULE-0041` is unchanged; this implements its checking
  bullet for the brain itself.

## Migration

None: the records were adopted on 1 October 2026, and every file in them is now within the limit.

## Rollback

Revert the proposal's commits. The size record stays; without the check it is only a record again.

## Validation

- The validator's tests: 107 of 107 pass.
- A planted 801-line file in the real mechanics makes the validator fail with the new message; removed,
  it passes.
- `shape.py --compare` on `preflight.py`: unchanged.
- The validator on the whole brain passes, apart from the protected-governance warnings for this
  proposal's own files on its `proposal/*` branch.

## Acceptance

Accepted by the owner and merged into `main`. The owner's record is kept in their memory.
