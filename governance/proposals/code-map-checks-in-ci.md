---
id: PROPOSAL-code-map-checks-in-ci
title: Code repositories run the code map's checks in their CI
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
created: 2026-10-01T10:13:16+10:00
updated: 2026-10-01T10:13:16+10:00
owner: brain-owner
previous_contract_version: 2.2.0
new_contract_version: 2.2.0
target_files:
  - /RULES.md
  - /shared/skills/code-map/SKILL.md
---

# Code repositories run the code map's checks in their CI

Read `/CONTRACT.md` first.

## Summary

A code repository the brain works on runs the code map's checks on every push, and a new finding
fails the push. The owner agreed to this on 1 October 2026 for the checks below, with the interface
check optional and the settings check report-only. This proposal is the rule's exact wording, so
it applies to every code repository and not only the first.

- **For agents:** a push that adds an import cycle, a UI call that reaches no route, an environment
  variable missing from the example file, a database column no model defines, or a code file over
  its size, fails in CI with the code map's message.
- **For the owner:** nothing to do. A repository's existing findings are recorded once when it
  adopts the checks and do not fail it.

## Current problem

The code map's checks run only when an agent remembers to run them. The trial of 28 September 2026
found real gaps this way (environment variables missing from the example file). And on 1 October,
splitting files made 45 UI calls in extract-bill-api look as if they reached no route; nothing ran
the check, so no one saw it until the code map was put in CI. Code map 0.5.1 fixed the cause.

## Current wording

None: no rule asks for the code map's checks. `SMART-RULE-0041` asks for its size check, or a test
reading the same record.

## Proposed wording

A new rule in `/RULES.md` (its number is given at acceptance):

> ## SMART-RULE-NNNN – Code repositories run the code map's checks
>
> - A code repository the brain works on runs the code map's checks in its CI on every push: no
>   import cycle among modules loaded at start-up, every UI call reaches a backend route, every
>   environment variable read is in an example env file, the code names only database columns its
>   models or tables define, and code files keep within their size (`SMART-RULE-0041`). A new
>   finding fails the push.
> - A repository adopts the checks by recording the findings it already has
>   (`code-map record --adopt`); those do not fail it, and each is fixed or kept as a known finding
>   on purpose.
> - The interface check is optional (a repository keeps an interface record only if it wants
>   one); the settings check reports and never fails.
> - CI takes the code map from the brain's mechanics at a fixed commit, raised on purpose, so a
>   change to the code map cannot break a repository's build unseen.
> - Agents may use the map to answer questions (`show`, `find`), but need not.

## Reason

The owner chose this on 1 October 2026 ("yes" to requiring cycles, http, env and columns in code
repositories' CI, interface optional, settings report-only). A check that runs only when remembered
is skipped, as the release-note check was.

## Scope and consequences

- Every code repository the brain works on; extract-bill-api already runs it (2.98.15), with every
  check passing.
- A repository's CI needs Node and a checkout of the public mechanics.

## Risks and conflicts

- **False findings** from code the map does not yet understand (as with the register functions on
  1 October): the finding is recorded as known while the code map is fixed, and the fix is tested.
- **No conflict** with `SMART-RULE-0041`: its size check is one of these checks.

## Rollback

Remove the rule from `/RULES.md`; repositories may keep or drop their CI job.

## Validation

- extract-bill-api: the job passes on `testing` (2.98.15); each check was shown failing on purpose
  in the code map's own tests.
- The repository preflight passes.

## Acceptance

Not yet accepted.
