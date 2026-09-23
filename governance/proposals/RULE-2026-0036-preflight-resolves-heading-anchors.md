---
id: RULE-2026-0036
title: Preflight resolves heading anchors in declared references
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0036
owner: brain-owner
created: 2026-09-15T00:48:52+10:00
updated: 2026-09-15T01:04:19+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T01:04:19+10:00
implemented_at: 2026-09-15T01:04:19+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /shared/skills/repository-preflight/scripts/preflight.py
  - /shared/skills/repository-preflight/SKILL.md
project_refs:
  - /memory/projects/brain-development
related_rules:
  - RULE-2026-0022
supersedes: []
---

# RULE-2026-0036: Preflight resolves heading anchors in declared references

## Plain-language summary

The repository preflight validator currently treats a reference such as
`/projects/example/LOG.md#2026-09-12T16:40:00+10:00` as broken, because it looks for a file
literally named with the `#` fragment. But that is exactly the form the API-knowledge entry
template prescribes for `source_refs`, so every knowledge entry written to the house convention
fails preflight. After this change the validator splits the fragment off, checks the file exists,
and then checks that a Markdown heading in that file begins with the fragment. A wrong or
truncated anchor is reported as `broken <key> anchor`; a missing file is still reported as
`broken <key> reference`.

The validator is protected governance under CONTRACT §13.2, which is why this is a proposal.

## Current problem

`RULE-2026-0022` (2026-08-27) introduced per-API knowledge entries and a template whose
`source_refs` example is `/projects/EXAMPLE/LOG.md#TIMESTAMP`. The validator's
`validate_declared_references` was last changed on 2026-08-12 (`RULE-2026-0020`) and does not
know about fragments. The result is that the preflight error count has risen with every
knowledge entry written: 11 on 2026-09-12, 21 on 2026-09-14. The root log has called these
"source_refs anchors the validator cannot resolve" since 2026-09-03 and treated them as a
baseline to be matched rather than a defect to be fixed.

A rising baseline defeats the purpose of the check. An agent comparing "21 before, 21 after"
cannot tell a new broken reference from an old one without reading every line.

Of the 21 errors reported on 2026-09-14, four were genuine and have been fixed directly
(two duplicate ids, two malformed `source_refs` values carrying free text after the path). The
remaining 17 are all anchors of this form, and every one of them points at a heading that
exists.

## Current wording

`/shared/skills/repository-preflight/scripts/preflight.py`, in `validate_declared_references`:

```python
                target = root / value.lstrip("/")
                if not target.exists() and not is_template:
                    result.errors.append(
                        f"{display}: broken {key} reference {value}"
                    )
```

`/shared/skills/repository-preflight/SKILL.md`, "Failure behaviour":

```markdown
- fail on missing required Markdown metadata, duplicate IDs, invalid task states, broken declared references, contract-version mismatch, or an uncovered protected-governance change
```

## Proposed wording or exact diff

### Diff A – `/shared/skills/repository-preflight/scripts/preflight.py`

```diff
--- /shared/skills/repository-preflight/scripts/preflight.py (current)
+++ /shared/skills/repository-preflight/scripts/preflight.py (proposed)
@@ -238,6 +238,24 @@
     result.contract_version = str(version)


+def heading_exists(target: Path, anchor: str) -> bool:
+    """True when a Markdown heading in target begins with `anchor`.
+
+    Log entry headings begin with an ISO 8601 timestamp (CONTRACT §4) and may
+    carry a title after it, so the anchor must match the whole first token.
+    """
+    if not target.is_file():
+        return False
+    try:
+        text = target.read_text(encoding="utf-8")
+    except OSError:
+        return False
+    pattern = re.compile(
+        r"^#{1,6}\s+" + re.escape(anchor) + r"(?:\s|$)", re.MULTILINE
+    )
+    return pattern.search(text) is not None
+
+
 def validate_declared_references(
     root: Path, records: dict[Path, dict[str, Any]], result: Result
 ) -> None:
@@ -266,11 +284,17 @@
                             f"{display}: {key} value must be a repository-root path: {value}"
                         )
                     continue
-                target = root / value.lstrip("/")
+                path_part, _, anchor = value.partition("#")
+                target = root / path_part.lstrip("/")
                 if not target.exists() and not is_template:
                     result.errors.append(
                         f"{display}: broken {key} reference {value}"
                     )
+                    continue
+                if anchor and not is_template and not heading_exists(target, anchor):
+                    result.errors.append(
+                        f"{display}: broken {key} anchor {value}"
+                    )


 def validate_tasks(
```

### Diff B – `/shared/skills/repository-preflight/SKILL.md`

```diff
-- fail on missing required Markdown metadata, duplicate IDs, invalid task states, broken declared references, contract-version mismatch, or an uncovered protected-governance change
+- fail on missing required Markdown metadata, duplicate IDs, invalid task states, broken declared references (a `#fragment` after the path must match the start of a Markdown heading in the referenced file), contract-version mismatch, or an uncovered protected-governance change
```

At implementation time only, update the skill's `updated` timestamp.

A heading "begins with" the anchor when the anchor is followed by whitespace or end of line, so
`## 2026-09-12T16:40:00+10:00 – Triggers found` satisfies the anchor
`2026-09-12T16:40:00+10:00` and `## 2026-09-12T16:40:00+10:00` does too, but a truncated
anchor `2026-09-12T16:40:00+10:0` does not.

`/CONTRACT.md` is unchanged; `contract_version` stays at `0.9.0`.

## Reason

The template and the validator disagree, and the template is the convention agents actually
follow. Fixing the entries instead would mean stripping the timestamp from every `source_refs`
value, which loses the pointer to the specific log entry that is the whole point of the field.
Fixing the validator makes the existing convention checkable: a wrong timestamp now fails
instead of passing silently as it would if fragments were simply ignored.

## Scope and behavioural consequences

- Applies to every reference key the validator already checks: `project_refs`,
  `knowledge_refs`, `skill_refs`, `source_refs`, `raw_source`, `canonical_source_md`,
  `script_paths`, `target_files`.
- A reference with a fragment now passes when the file exists and a heading begins with the
  fragment, and fails with a distinct `broken <key> anchor` message otherwise.
- References without a fragment behave exactly as before.
- Templates remain exempt, as before.

## Risks and conflicts

- A heading that has been reworded so it no longer begins with the timestamp would now fail.
  CONTRACT §4 requires log entry headings to begin with the timestamp, so that failure is
  correct.
- Reading each referenced file adds a small cost per anchored reference. On this repository
  (2568 Markdown files) the patched validator runs in the same order of time as the current one.
- No conflict with `RULE-2026-0022`; this makes its template's convention enforceable.

## Migration

None. All 17 current anchor references already resolve under the proposed check.

## Rollback

Revert Diffs A and B and mark this proposal `reverted`. The 17 anchor errors return.

## Validation

Already performed against a patched copy of the validator held outside the repository, on
2026-09-15T00:48:52+10:00:

1. Patched validator against this repository: **PASS**, 0 errors, 2568 Markdown files, 2568
   unique ids (the current validator reports 17 errors on the same tree, all anchors).
2. Negative test on a throwaway tree with one log and one knowledge entry carrying four
   `source_refs`: an exact anchor on a heading with a trailing title (passes), a truncated
   anchor (fails as `broken source_refs anchor`), a timestamp with no heading (fails as
   `broken source_refs anchor`), and an anchor on a file that does not exist (fails as
   `broken source_refs reference`). All four outcomes as intended.

At implementation: apply Diffs A and B, run `git diff --check`, run the live validator and
require **PASS**, then `--write-manifest`.

## Acceptance

**Question asked:** Do you accept `RULE-2026-0036` with exactly Diffs A and B in its proposal?

**Accepted by the owner, 2026-09-15T01:04:19+10:00**, in the exact words "I accept".

## Implementation record

Implemented 2026-09-15T01:04:19+10:00. Diff A applied to `preflight.py` and Diff B to `SKILL.md` (with its
`updated` timestamp), wording unchanged from the accepted text. `contract_version` unchanged at
0.9.0. Validation results are recorded below the log entry of the same timestamp in
`/projects/brain-development/LOG.md`.
