---
id: brain-rules-software-checks
title: Rule pack: software-checks
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-24T18:28:13+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: software-checks

Generated from `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim, the rules of one
situation, so that they are read together. Each rule's canonical home stays `/RULES.md`.

Read the whole file before: creating a code repository or giving one its remote; setting up or changing a code repository's CI, checks, test runner or pre-push hook; a check fails or is slow.

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0042` | Code repositories run the code map's checks | this file; `/shared/skills/code-map/` | creating a code repository or giving one its remote; setting up or changing a code repository's CI; when a code-map check fails |
| `SMART-RULE-0049` | Fast project checks without reduced coverage | this file | setting up or changing a code project's checks, CI, test runner or pre-push hook; a check is slow |

## SMART-RULE-0042 – Code repositories run the code map's checks

- A code repository the brain works on runs the code map's checks in its CI on every push: no
  import cycle among modules loaded at start-up, every UI call reaches a backend route, every
  environment variable read is in an example env file, the code names only database columns its
  models or tables define, and code files keep within their size (`SMART-RULE-0041`). A new
  finding fails the push.
- A repository adopts the checks by recording the findings it already has
  (`code-map record --adopt`); those do not fail it, and each is fixed or kept as a known finding
  on purpose.
- The interface check is optional (a repository keeps an interface record only if it wants
  one); the settings check reports and never fails.
- CI takes the code map from the brain's mechanics at a fixed commit, raised on purpose, so a
  change to the code map cannot break a repository's build unseen.
- CI is part of creating the repository, not a later task. When a code repository gets its
  remote, the commit that first puts code in it, or the one straight after, adds the CI run: the
  project's tests, even while there is only one, and the code map's checks, adopted while there
  is nothing yet to adopt. Feature work begins once that run has passed. A repository the brain
  starts work in that has code and no CI gets it before the next feature, and the agent says so
  instead of filing it as a task for later.
- Agents may use the map to answer questions (`show`, `find`), but need not.

## SMART-RULE-0049 – Fast project checks without reduced coverage

- For every new code project, build these concepts into its validation setup. When an existing code project is next changed, review and apply the applicable concepts before handoff; record any justified incompatibility and remaining work in that project's state. Projects without executable code are assessed for applicable checks without adding an unnecessary build system.
- Reuse dependencies only when an exact cache key covers all lockfiles, runtime version, platform/architecture and installation inputs. Verify completeness and integrity before reuse; a missing, corrupt or incompatible cache falls back to a clean install. Publish entries atomically, bound cache storage, and keep cleanup from deleting shared dependencies.
- Tune test concurrency from measured runtime and reliability within the machine's capacity. Keep overrides available and retain full test coverage. Use two browser workers as the initial local default where browser tests exist; raise it only after repeat measurements show a reliable improvement. Adapt unit-test concurrency to the project and available cores rather than imposing one number everywhere.
- Avoid duplicate checks only when successful results belong to the exact commit, comparison base and relevant configuration being validated. Restrict docs-only shortcuts to the project's explicit non-product definition; include both sides of renames, and run full checks when scope is unknown. Version and release-note checks still run where required; never skip executable documentation or generated-code inputs merely because of their location or extension.
- Preserve validation of the exact committed tree, isolation from dirty working files, branch-movement protection, cleanup and all required checks. Unexpected failures or missing results block integration. Warn about local runtime differences from CI. Never use bypass flags or weaken tests to improve timings.
- Validate cache keys, hit/miss/corruption paths and every skip condition. Record cold and warm per-step timings and concurrency comparisons with failures included. Keep one canonical project implementation of each check, and report which optimisations are active and which are inapplicable.
- **A failed test is rerun once, alone, and stays named.** A check that runs before integration (a pre-push hook or CI) runs each failed test once more, on its own, after every other step has finished, so nothing else competes with it for the machine. A test that passes then counts as passed and is named in the check's output; one that fails again fails the check. Only the failed tests rerun, never the whole suite, and never more than once. A step with more failures than a small limit the project sets (5 unless it chooses another) is not rerun: that many failures is a fault. Each rerun is recorded outside the repository's tracked files, and the check warns when the same test has needed a rerun in 3 of its last 20 runs; such a test is reported to the owner and fixed, never left to the rerun.
- **Rolling push.** A conductor that merges several workers' branches pushes as soon as a merge is ready and no push is running. While a push's check runs, nothing is merged into the branch being pushed. Branches that finish during a push are merged when it returns and go out together in the next push. No push waits for a batch to be complete, and none is held back to save a check or a deployment.
