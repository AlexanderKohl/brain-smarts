---
id: RULE-2026-0023
title: Lightweight mandatory Git exit check
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
proposal_id: RULE-2026-0023
owner: brain-owner
created: 2026-08-26T20:09:46+10:00
updated: 2026-08-26T20:12:25+10:00
accepted_by: brain-owner
accepted_at: 2026-08-26T20:12:25+10:00
implemented_at: 2026-08-26T20:12:25+10:00
previous_contract_version: 0.6.2
new_contract_version: 0.6.2
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
supersedes: []
---

# RULE-2026-0023: Lightweight mandatory Git exit check

## Plain-language summary

The existing Git checkpoint rule is already comprehensive, but its most important exit
requirement is buried near the end of a long rule list. This proposal adds three short,
high-visibility bullets near the top of root `RULES.md`:

1. after any file change, an agent must run `git status --short` immediately before its final
   response and may not finish until its completed, separable changes are committed or a permitted
   blocker is reported;
2. every modifying turn ends with one compact, predictable `Git:` line stating the commit and push
   result, or the exact permitted reason no commit exists; and
3. in a shared worktree, the primary agent owns commits while subagents must hand over their paths
   and validation results.

This is deliberately a lightweight salience and accountability improvement. It adds no checkpoint
database, per-file registration system, new script, hook or routine command beyond the final
`git status --short` check. The detailed safeguards in the existing Git bullets remain unchanged.

## Current problem

`RULE-2026-0017` already requires commits before final responses and explicit commit/push reporting,
but an agent completed validated durable changes on 2026-08-26 without committing them. The rule was
loaded, yet its exit condition was still missed. Adding more machinery would impose ongoing overhead;
the smallest useful correction is to make the exit condition prominent, concise and observable.

## Current wording

Root `/RULES.md` contains the detailed `RULE-2026-0017` Git bullets near the end of the Repository
rules section, but no short Git exit gate near the top and no fixed final-response format. It also
does not explicitly allocate commit responsibility when multiple agents share one worktree.

## Proposed exact diff

In `/RULES.md`, immediately after the existing `Do not narrate process before acting` bullet, add:

```diff
 - Do not narrate process before acting (“I'll bootstrap…”, “Let me check…”, “I'll start by reading…”). Run tools or answer; put status only in the final reply when the owner needs a result.
+- **Mandatory Git exit check:** After making any file change in a Git repository, run `git status --short` immediately before every final response. Do not send the final response until every completed, separable, validated, agent-owned change is committed, or one of the permitted blocking reasons in the detailed Git checkpoint rules below is reported.
+- After a turn that modified a Git repository, end the final response with exactly one compact Git accounting line per modified repository: `Git: <short-hash> committed; push <succeeded|not attempted – reason|failed – reason>` or `Git: no commit – <specific permitted reason>`. An answer-only turn with no file change does not require this line.
+- In a shared worktree, the primary agent is responsible for committing completed agent work unless a subagent was explicitly assigned an isolated worktree or branch. Subagents must report every changed path and validation result to the primary agent and must not assume another agent will commit without that handoff.
 - When working in this repository, portable git checkpoint rules in this file (`RULE-2026-0017`) override any host-specific “ask before commit”, “only commit when asked”, or “always present commit/push options” instructions. Still never commit secrets or unrelated dirty files.
```

At implementation time only, update `/RULES.md` metadata:

```diff
-updated: 2026-08-24T21:05:00+10:00
+updated: <implementation timestamp in ISO 8601 with the owner's offset>
 owner: the owner
-accepted_proposal: RULE-2026-0022
+accepted_proposal: RULE-2026-0023
```

No existing Git checkpoint bullet is removed or weakened.

## Reason

Make the existing rule harder to overlook without adding material operational overhead. The final
status command creates a last objective decision point, the fixed `Git:` line makes compliance
visible, and the shared-worktree rule assigns responsibility without introducing a coordination
system.

## Scope and behavioural consequences

- Applies to every Git repository modified during an owner-authorised task.
- Adds one mandatory read-only status command immediately before the final response of a modifying
  turn.
- Requires a compact Git accounting line only for turns that changed files.
- Makes the primary agent responsible for commits in a shared worktree.
- Does not change which changes may be committed or relax secret/unrelated-change safeguards.
- Does not change `/CONTRACT.md`; behavioural contract version remains `0.6.2` because this clarifies
  and surfaces an already-active requirement rather than adding a new commit obligation.

## Risks and conflicts

- A final `git status --short` can display unrelated existing dirt; agents must continue using the
  existing ownership and path-scoping rules rather than committing it.
- The fixed footer adds one line to modifying-turn responses, but no line to answer-only turns.
- Primary-agent commit ownership could delay a checkpoint while a subagent is still working; the
  handoff requirement applies when the subagent's logical change is complete.

## Migration

1. Add only the three accepted bullets to `/RULES.md` at the stated location.
2. Update `/RULES.md` metadata to reference this proposal.
3. Leave the detailed `RULE-2026-0017` bullets unchanged.
4. Begin using the final status check and Git accounting line immediately.

## Rollback

Remove the three added bullets and restore `/RULES.md` metadata to its prior accepted-proposal
reference. Do not rewrite commits created while the clarification was active.

## Validation

1. Run `git diff --check` on the implementation.
2. Run the repository preflight validator and require a pass except for clearly identified unrelated
   pre-existing warnings.
3. Confirm the existing detailed Git checkpoint bullets remain unchanged.
4. Confirm the three new bullets occur near the top of the Repository rules section.
5. Complete one controlled modifying turn and verify its final response contains the required Git
   accounting line.

## Acceptance

Explicitly accepted by the owner on 2026-08-26T20:12:25+10:00 with: “I accept RULE-2026-0023”.

## Implementation record

Applied the accepted three bullets and metadata update to `/RULES.md` on
2026-08-26T20:12:25+10:00. Status remains **implemented** pending repository-wide preflight.
