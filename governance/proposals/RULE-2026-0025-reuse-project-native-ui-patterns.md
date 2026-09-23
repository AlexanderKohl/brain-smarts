---
id: RULE-2026-0025
title: Reuse project-native UI patterns
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0025
owner: brain-owner
created: 2026-08-31T09:11:39+10:00
updated: 2026-08-31T09:25:52+10:00
accepted_by: brain-owner
accepted_at: 2026-08-31T09:25:52+10:00
implemented_at: 2026-08-31T09:25:52+10:00
previous_contract_version: 0.7.0
new_contract_version: 0.7.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
supersedes: []
---

# RULE-2026-0025: Reuse project-native UI patterns

## Plain-language summary

Before creating or styling any interface element in a development project, agents must first look
inside that project for an existing element that serves the same or closest purpose. Equivalent
elements must reuse or extend the project's existing component, style and interaction pattern so
the interface remains visually and behaviourally aligned. A parallel style may be introduced only
when there is no suitable existing pattern or a documented requirement makes reuse inappropriate.

The owner explicitly accepted this proposal, and the rule is active in root `/RULES.md`.

## Current problem

The root rules do not currently require agents to inspect a development project's existing UI
patterns before adding an element. An agent can therefore invent a second multiselect, button,
modal, field layout or other style even when the project already contains a suitable version,
causing visual and behavioural drift inside one product.

## Current wording

There is no active repository-wide rule governing project-internal UI pattern discovery and reuse.

## Proposed exact diff

In root `/RULES.md`, add `0025` to the `Root IDs in this file` list and add this section after
`RULE-2026-0016`:

```diff
+## RULE-2026-0025 – Reuse project-native UI patterns
+
+- In every software or development project, before creating or styling a user-interface element,
+  search the active project's code, components, styles and design-system assets for the same or
+  closest existing element and interaction pattern.
+- Equivalent elements must reuse or extend the project's existing component, design tokens,
+  styling and behaviour so they remain visually and functionally aligned. Do not invent a
+  parallel element style when a suitable project-native pattern already exists.
+- If no suitable pattern exists, derive the new element from the project's established visual
+  language and adjacent components. Make it reusable when the project is likely to need the same
+  pattern again.
+- Do not preserve a known accessibility, security or functional defect merely for visual
+  consistency. Explicit owner requirements and supplied design references may override an
+  existing pattern; when they do, integrate the change deliberately with the rest of the project.
```

At implementation time only, update `/RULES.md` metadata and the root-ID inventory:

```diff
-updated: 2026-08-27T13:05:03+10:00
+updated: <implementation timestamp in ISO 8601 with the owner's offset>
 owner: the owner
-accepted_proposal: RULE-2026-0023
+accepted_proposal: RULE-2026-0025
```

```diff
-Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`.
+Root IDs in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`.
```

No existing rule is removed or weakened. `/CONTRACT.md` is unchanged.

## Reason

Keep each product internally consistent, reduce duplicate UI code, and make new work feel like part
of the existing project instead of a separately designed feature.

## Scope and behavioural consequences

- Applies to all software and development projects governed by this brain, regardless of framework.
- Requires a targeted project-local lookup before introducing a UI element or its styling.
- Prefers actual component/style reuse; visual imitation is a fallback when direct reuse is not
  technically suitable.
- Covers visual styling and interaction behaviour, including controls, fields, menus, tabs, modals,
  tables, alerts and responsive states.
- Does not require copying styles between different projects; alignment is within each project.
- Does not change `/CONTRACT.md`; contract version remains `0.7.0`.

## Risks and conflicts

- Blind reuse can perpetuate an accessibility, security or functional defect. The proposed rule
  explicitly excludes known defects from the consistency requirement.
- A project may contain several inconsistent legacy patterns. In that case, prefer the active
  design system, shared component or pattern used by the closest current feature; do not silently
  treat the first search result as authoritative.
- A supplied design or explicit owner direction may intentionally introduce a new pattern. The
  rule permits that override but requires deliberate integration rather than accidental drift.

## Migration

1. After acceptance, apply only the displayed root-rule, metadata and ID-inventory changes.
2. Use the lookup-and-reuse requirement for new development work from that point forward.
3. Do not retroactively restyle existing projects solely because this rule became active.

## Rollback

Remove `RULE-2026-0025` from root `/RULES.md`, remove `0025` from its root-ID inventory, and restore
the prior `accepted_proposal` metadata. Existing UI changes made while the rule was active are not
automatically reverted.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require a pass except for clearly identified,
   unrelated pre-existing warnings.
3. Confirm the live root rule exactly matches the accepted wording and no other rule changed.
4. Confirm the root-ID inventory contains `0025` once and the metadata names `RULE-2026-0025`.
5. On the next applicable development task, confirm the agent searches for and reuses the closest
   project-native UI pattern before adding a new element.

## Acceptance

Explicitly accepted by the owner on 2026-08-31T09:25:52+10:00 with “I accept”, in direct response to
the acceptance question identifying `RULE-2026-0025` and its exact displayed change set.

## Implementation record

Applied the accepted root-rule wording, root-ID inventory and metadata changes to `/RULES.md` on
2026-08-31T09:25:52+10:00. Contract version remains `0.7.0`.
