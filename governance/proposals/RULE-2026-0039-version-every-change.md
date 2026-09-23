---
id: RULE-2026-0039
title: Version every change, and show the version where a person can read it
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-15T14:05:00+10:00
updated: 2026-09-15T20:16:29+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T14:40:00+10:00
implemented_at: 2026-09-15T14:40:00+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# Version every change, and show the version where a person can read it

## Current problem

The owner's browser extension sat at `0.3.0` through weeks of changes, including today's test plan,
storage stage four, the Changes view and the search probes. When the owner reloaded the
extension and ran the storage test, the report came from the old code and nothing on screen
said so; the conductor had to infer it from the wording of one line. Every product this brain
develops has the same exposure: a build loaded in a browser, a service deployed to staging, a
script run from a checkout, with no number that says which change it contains.

## Current wording

None. `RULE-2026-0017` governs commits and `RULE-2026-0028` governs the development process;
neither says a change must carry a version or that the version must be visible.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0037` and before the contract-restatement list:

```markdown
## RULE-2026-0039 – Version every change, and show it

- Every software or development project carries one version of three numbers,
  `first.middle.last`, kept in the project's own version field (`package.json`,
  `manifest.json`, `pyproject.toml` or the equivalent) and nowhere else. Each logical change
  that reaches a build a person can load, run or deploy bumps exactly one number in the same
  commit, chosen by these tests, taking the highest that applies:
  - **First number, breaking.** After the change, something that worked before no longer
    works the same way without action by someone: stored data needs a migration or is read
    differently, an interface that others call or read changes its shape or meaning, or a
    procedure a person follows changes its steps. Bumping the first number resets the other
    two. There is no exception for versions below `1.0.0`: the first breaking change takes a
    `0.x` product to `1.0.0`.
  - **Middle number, feature.** A person can see or do something they could not before, or
    something visible behaves differently on purpose without breaking what depended on it: a
    new view, a new setting, a new record kind, a changed layout. Resets the last number.
  - **Last number, small change.** Everything else: a fix, a wording change, a refactor, a
    performance or reliability change, a test-only or build-only change that ships in the
    product. Nothing a person relied on changes.
  When one commit carries changes at several levels, bump the highest once.
- Every build embeds the version together with the commit it was built from, the build time
  and, when not on the main branch, the branch name; a build from a tree with uncommitted
  changes is marked as such. This build identity is shown where a person looks first: an
  extension's popup and its browser card, a page's footer, a service's health or about
  endpoint, a CLI's `--version`. In local, testing and staging environments the full identity
  is shown; in production the semantic version is shown and the rest is one step away.
- A test in the project's check fails when a commit changes the product without changing the
  version, so a change cannot reach a build unnumbered. Commit messages, task records and log
  entries that describe a change name the version it lands in.
- When asking the owner to reload, test or deploy, state the version and build identity they
  should see, so a stale build is recognised at a glance.
```

Append `0039` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0039`.

## Reason

A number that changes with every change is the cheapest way to know what is running. The
build identity turns "did the reload take" from an inference into a glance, and the failing
check makes forgetting impossible rather than discouraged. Showing the full identity only
outside production keeps commit hashes and branch names away from customers while keeping
them for everyone who tests.

## Scope and behavioural consequences

Every software project the brain works on, from the next change onward. The owner's browser extension
is the first: `0.4.0` (a feature bump: several new views and settings, nothing broken) with a build stamp in the popup, the browser card, the extension's page footer
and the storage-test report, and a version check in `npm run check`. Other projects adopt it
the next time they are changed. Agents state the expected version when handing a build to the
owner.

No `contract_version` change: a root rule, not contract behaviour, following `RULE-2026-0032`.

## Risks and conflicts

- **Bump noise.** Every commit that touches the product bumps at least the patch number;
  accepted, that is the point.
- **Merge conflicts on the version field** when two branches bump the same number; resolved by
  taking the higher and bumping once more, which the check will demand anyway.
- Complements `RULE-2026-0017` (the bump lives in the same commit as the change) and
  `RULE-2026-0028` (release readiness names a version). No conflict found.

## Migration

Projects keep their current numbers until their next change, then bump from there. The owner's
extension moves from `0.3.0` to `0.4.0` on activation, one minor bump covering today's features.

## Rollback

Remove the `RULE-2026-0039` section from `/RULES.md`, drop `0039` from the root ID list,
restore `accepted_proposal`, and set this proposal to `reverted`. Version checks already added
to projects can stay or be removed per project.

## Validation

- Repository preflight before and after activation reports the same error count.
- The owner's browser extension's `npm run check` fails on a fixture commit that changes `src/` without
  a version bump, and passes on the bump commit.

## Acceptance

Reworded 2026-09-15T14:30:00+10:00 at the owner's request: the three levels are defined by tests (breaking, feature,
small change), the pre-1.0 exception is removed, and the highest applicable level is bumped
once per commit.

**Question to ask:** 1. Accept `RULE-2026-0039` with the reworded levels (recommended); 2. accept
without the failing-check bullet; 3. reject.

**Accepted by the owner, 2026-09-15T14:40:00+10:00**, in the word "accepted" after the reworded levels were presented with the numbered question (option 1).

## Implementation record

Implemented 2026-09-15T14:40:00+10:00. `RULE-2026-0039` added to `/RULES.md` after `RULE-2026-0037` with the accepted wording unchanged; `0039` appended to the root ID list; `accepted_proposal` set to `RULE-2026-0039`. Contract version unchanged at 0.9.0. The owner's browser extension already carries the practice at 0.4.0 with `scripts/check-version.mjs` in `npm run check`; other projects adopt it on their next change. Preflight run after the change.

## Amendment A1 (2026-09-15T15:35:00+10:00): the version on screen, the identity one step away

**Status of this amendment: accepted and implemented (2026-09-15T16:30:00+10:00).** Owner direction of 2026-09-15 on seeing 0.4.0: "remove
the ID and timestamp from the UI, we want to keep it clean". The accepted second bullet says the
full identity is shown in local, testing and staging; the owner wants the version alone shown
everywhere and the rest reachable. A small change to a live rule keeps its ID.

### Exact diff

In `/RULES.md` under `RULE-2026-0039`, replace the sentence

> In local, testing and staging environments the full identity is shown; in production the
> semantic version is shown and the rest is one step away.

with

> The version is what is shown; the commit, build time and branch are one step away in every
> environment: a tooltip on the version, an about panel, the extensions card, a health
> endpoint's body or a `--version --verbose` flag.

### Reason

A commit hash and a UTC timestamp on every screen is noise for the person testing; the rule's
purpose, telling a stale build from a fresh one, is met by the version alone when every change
bumps it, and the identity stays available for the cases where two builds share a version.

### Rollback and validation

Restore the sentence. Preflight unchanged. Applied already in the extension at 0.4.1 under the
owner's direct instruction; the wording follows.

### Acceptance

**Question to ask:** 1. Accept amendment A1 to `RULE-2026-0039` as written (recommended);
2. accept with wording changes; 3. reject. **Accepted by the owner, 2026-09-15T16:30:00+10:00**, with the answer "1a". Implemented the same minute: the sentence replaced in `/RULES.md` verbatim; `accepted_proposal` set to `RULE-2026-0039`. Contract version unchanged at 0.9.0.

## Amendment A2 (2026-09-15T20:07:44+10:00): below `1.0.0` a breaking change rides the middle number

**Status of this amendment: accepted and implemented (2026-09-15T20:16:29+10:00).** Owner
direction of 2026-09-15, on being told that stripping the options page would take the extension
extension to `1.0.0`: "let's stick with 0.14.0 as we are still in development phase". A small
change to a live rule keeps its ID (CONTRACT §13.2).

### Exact diff

In `/RULES.md` under `## RULE-2026-0039`, in the **First number, breaking** bullet, replace:

```markdown
    two. There is no exception for versions below `1.0.0`: the first breaking change takes a
    `0.x` product to `1.0.0`.
```

with:

```markdown
    two. While a product is still in development its version stays below `1.0.0`, and a
    breaking change there bumps the **middle** number instead: nothing outside the team
    depends on it yet, so the first number would say nothing a reader could use. `1.0.0` is
    set once, deliberately, when the owner declares the product released, and from that
    version on the first number follows the test above. A breaking change before `1.0.0` is
    still named as breaking in its commit message and in the node's `LOG.md`, so the history
    says what changed even where the number does not.
```

### Reason

The rule's own test for the first number is about what a reader can rely on. Before a product
is released nobody outside the team relies on it, so the first number carries no information
and spending it costs the one signal that says "this is finished". The honesty the rule wants
is kept by naming the break in the commit and the log, which is where a person looks when
something they had stops working.

This reverses the sentence added when `RULE-2026-0039` was first reworded, at the owner's
request on the same day. The reason it went in was that a `0.x` product can still break its
owner; the reason it comes out is that the owner is the only one it can break, is told in the
log, and would rather keep `1.0.0` for the release. Recorded so the next reader sees both.

### Scope and behavioural consequences

Every product the brain versions. The owner's browser extension is the first: the options-page change of
today, which removes stored settings and a configured destination folder, lands at `0.14.0`
and its commit says it is breaking. The extension reaches `1.0.0` when the owner says it is
released.

No `contract_version` change: a root rule, not contract behaviour.

### Risks and conflicts

- **A long `0.x` life.** A product can accumulate breaking changes at the middle number for
  months; the log is then the only record of them. Accepted: the log entry is required.
- **Two products at different phases.** The rule is per product, so one can be released and
  another in development without conflict.

### Rollback and validation

Restore the replaced sentence. Preflight unchanged. Validation is the next breaking change:
its commit message names the break and the middle number moves.

### Acceptance

**Question to ask:** 1. Accept amendment A2 to `RULE-2026-0039` as written, with `1.0.0`
reserved for the owner's own declaration that a product is released (recommended); 2. accept
but tie `1.0.0` to a fixed trigger instead of a declaration, such as the first user outside
the team; 3. reject, and the extension goes to `1.0.0` today.

**Accepted by the owner, 2026-09-15T20:16:29+10:00**, in the words "1. accept" (option 1). Implemented the same minute: the sentence replaced in `/RULES.md` verbatim; `accepted_proposal` set to `RULE-2026-0039`. Contract version unchanged at 0.9.0. First application: the owner's browser extension's options cleanup, breaking by the test, shipped as `0.14.0`.
