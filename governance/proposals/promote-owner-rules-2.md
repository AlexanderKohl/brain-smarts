---
id: PROPOSAL-promote-owner-rules-2
title: Three more owner rules that any brain can use move into the mechanics
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: accepted
owner: brain-owner
created: 2026-11-09T12:08:45+10:00
updated: 2026-11-09T13:25:17+10:00
accepted_by: brain-owner
accepted_at: 2026-11-09T13:25:17+10:00
implemented_at: 2026-11-09T13:25:17+10:00
rule_id: SMART-RULE-0049
previous_contract_version: 3.2.0
new_contract_version: 3.2.0
target_files:
  - /RULES.md
  - /CORE-RULES.md
  - /shared/skills/manage-credentials/SKILL.md
  - /shared/skills/learning-maintenance/SKILL.md
---

# Three more owner rules that any brain can use move into the mechanics

Read `/CONTRACT.md` first. Nothing here is active until the owner accepts it (CONTRACT §13.2).
`rule_id` names the one new rule, `SMART-RULE-0049`; part A amends `SMART-RULE-0028` and keeps its
number. The second such move after `PROPOSAL-promote-owner-rules` (October 2026). The owner-layer
side (retiring the moved rules in the owner's own memory) is a companion proposal in that memory,
accepted together with this one.

## Plain-language summary

An owner's rules sometimes turn out to suit every brain. Three such rules move from one owner's
memory into the mechanics, so every brain that uses or follows these mechanics gets them:

- **A. Learnings carry their risk, impact and suggestion.** Whenever an agent shows the owner a
  learning, it says what can go wrong, how much that would matter, and what it suggests, and says
  when the fix is already built. Added to `SMART-RULE-0028` (evidence-driven learning).
- **B. Fast project checks without reduced coverage** becomes `SMART-RULE-0049`, unchanged in
  substance: exact cache keys, measured test concurrency, no check skipped unless its result
  belongs to the exact commit, never a bypass flag.
- **C. The credential policy** moves into the credential skill, where it governs every brain's
  vault: storage, vault structure, passphrase, OAuth lifecycle, portability and logging. About
  half of it was already in the skill; the rest (one refresh writer per credential set, scopes,
  tenant context, child-process injection, logging and the rotation-failure task) was only in one
  owner's node rules.

Nothing changes for agents in a brain that already had these as owner rules; other brains gain
them.

## A. Amendment to `SMART-RULE-0028` (`/RULES.md`)

A new bullet after **Present a weekly review**:

> - **Show each learning with its risk, impact and suggestion.** Whenever an agent shows the owner a
>   learning – in the weekly review, a review of pending records, or a reply – each one states in
>   plain words: the risk (what can go wrong, and how likely it is to happen again), the impact
>   (high, medium or low, with one reason: what it would cost the owner, their business or their
>   customers), and the suggestion (what the agent proposes, or "nothing: accept the risk" with the
>   reason). A learning whose fix is already built says so and names the fix, so the owner is not
>   asked to decide it again. Learnings shown together are listed by impact, highest first.

`/shared/skills/learning-maintenance/SKILL.md`, where it describes the weekly review, gains one
sentence pointing to this bullet (ordinary change).

## B. New rule `SMART-RULE-0049` (`/RULES.md`)

Index row:

| `SMART-RULE-0049` | Fast project checks without reduced coverage | this file | setting up or changing a code project's checks, CI, test runner or pre-push hook; a check is slow |

Rule text:

> ## SMART-RULE-0049 – Fast project checks without reduced coverage
>
> - For every new code project, build these concepts into its validation setup. When an existing code project is next changed, review and apply the applicable concepts before handoff; record any justified incompatibility and remaining work in that project's state. Projects without executable code are assessed for applicable checks without adding an unnecessary build system.
> - Reuse dependencies only when an exact cache key covers all lockfiles, runtime version, platform/architecture and installation inputs. Verify completeness and integrity before reuse; a missing, corrupt or incompatible cache falls back to a clean install. Publish entries atomically, bound cache storage, and keep cleanup from deleting shared dependencies.
> - Tune test concurrency from measured runtime and reliability within the machine's capacity. Keep overrides available and retain full test coverage. Use two browser workers as the initial local default where browser tests exist; raise it only after repeat measurements show a reliable improvement. Adapt unit-test concurrency to the project and available cores rather than imposing one number everywhere.
> - Avoid duplicate checks only when successful results belong to the exact commit, comparison base and relevant configuration being validated. Restrict docs-only shortcuts to the project's explicit non-product definition; include both sides of renames, and run full checks when scope is unknown. Version and release-note checks still run where required; never skip executable documentation or generated-code inputs merely because of their location or extension.
> - Preserve validation of the exact committed tree, isolation from dirty working files, branch-movement protection, cleanup and all required checks. Unexpected failures or missing results block integration. Warn about local runtime differences from CI. Never use bypass flags or weaken tests to improve timings.
> - Validate cache keys, hit/miss/corruption paths and every skip condition. Record cold and warm per-step timings and concurrency comparisons with failures included. Keep one canonical project implementation of each check, and report which optimisations are active and which are inapplicable.

`/CORE-RULES.md` is regenerated by `core.py build` (one new table row).

## C. The credential policy (`/shared/skills/manage-credentials/SKILL.md`)

A new section `## Credential policy`, after `## Purpose`, holding the six groups of the owner's node
rules for credentials word for word – *Storage policy*, *Vault structure*, *Passphrase and
encryption*, *OAuth lifecycle*, *Portability and concurrency*, *Logging and failure* – with two
substitutions so it names nothing of one owner's:

- the vault path in the first storage bullet becomes "the vault file named under *Required inputs*";
- "the Portable AI Brain" becomes "the brain".

A skill's operating instructions are not protected governance (CONTRACT §13.2); the move is in this
proposal because the owner-layer copy it replaces is.

## Reason

On 9 November 2026 the owner asked whether a new owner rule belonged in the mechanics instead, and
for every owner rule that could. Each of these three passes the test of CONTRACT §3.4: free of
every owner specific once a name and a path are generalised, and useful to another owner as it
stands. The rest stay in the owner's memory (style, the owner's own systems and products).

## Scope and behavioural consequences

Every brain on these mechanics, including brains that follow them upstream (`SMART-RULE-0032`),
which take this change on their next merge. Agents show learnings in the new format, apply the
check rule when they touch a code project's checks, and read the credential policy in the skill.

## Risks, conflicts and migration

- An owner can add constraints to a mechanics rule but not relax it; none of the three takes away
  anything an owner would want to keep.
- `SMART-RULE-0049` may ask more of a small project than it needs; its first bullet already scales
  it ("applicable concepts").
- Migration: the owner-layer copies are retired by the companion memory proposal in the same
  change, so no rule exists twice.

## Rollback

Revert the commits in each repository; the companion memory proposal's rollback restores the
owner-layer copies.

## Validation

The repository preflight passes on each layer, `core.py build` leaves `/CORE-RULES.md` current,
and the personal-data check passes on the mechanics.
