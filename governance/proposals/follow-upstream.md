---
id: PROPOSAL-follow-upstream
title: The owner decides in their own brain, and a brain can follow its original
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: accepted
owner: brain-owner
accepted_by: brain-owner
accepted_at: 2026-11-08T11:04:23+10:00
implemented_at: 2026-11-08T11:07:00+10:00
created: 2026-11-08T10:23:26+10:00
updated: 2026-11-08T11:07:00+10:00
rule_id: SMART-RULE-0032
previous_contract_version: 3.1.0
new_contract_version: 3.2.0
target_files:
  - /CONTRACT.md
  - /CORE.md
  - /CORE-RULES.md
  - /RULES.md
  - /SETUP.md
  - /CONTRIBUTING.md
  - /repository-manifest.json
  - /shared/skills/skill-exchange/SKILL.md
---

# The owner decides in their own brain, and a brain can follow its original

Read `/CONTRACT.md` first. Nothing here is active until the owner accepts it (CONTRACT §13.2).
`rule_id` is `SMART-RULE-0032` because part B amends that rule rather than adding a new one.

## Plain-language summary

Two things change for an invited person who sets up a brain from someone else's original, and
for the agents working in it:

- **A. Whose decision it is.** In your own brain every decision is yours, the owner named in
  `/memory/OWNER.md`. The upstream maintainer, who maintains the original, decides only whether a
  contribution you offer as a pull request is taken, and who may read a private original. An agent
  never works out who the owner is from a GitHub account, a remote address or the Git authors, and
  never sends you to the upstream maintainer for a decision about your own brain. When
  `/memory/OWNER.md` is missing or has no `owner_name`, the agent says so and resumes setup.
- **B. Follow upstream.** A new owner setting, `follow_upstream`, asked once during setup
  (suggested yes for a brain set up from an original). When on, each session start merges the
  original's `main` into your mechanics and skill library with the same safe merge used for
  `origin`, takes in rule changes the upstream maintainer has already accepted, records each one in
  your memory and tells you in the first reply. When off, nothing changes from today: you are told
  what changed and you decide.

## Current problem

An invited person set up their own brain with `/SETUP.md` step B3 option 1 (`origin` their own
copy, `upstream` the original with push disabled). Two things went wrong:

1. Their brain referred many questions to the original's maintainer by name. The mechanics and the
   library hold no owner name, so the name came from elsewhere. Likely causes: with
   `/memory/OWNER.md` missing or thin, the agent took "the owner" to be the account in a remote
   URL or the Git authors; or it read "the upstream maintainer" and "the original's owner" in
   `/CONTRIBUTING.md`, `/SETUP.md` and the skill-exchange skill as deciding more than
   contributions and access. CONTRACT §3.6 says who the owner is but not whose decisions are whose.
2. It never took in later changes to the original. That is by design: `SMART-RULE-0032` only
   reports upstream changes, and merging waits for the owner, who may not know to say yes.

## Current wording and exact diff

### CONTRACT §3.6 (add a paragraph at the end)

Current, last paragraph: "In mechanics files, the metadata value `owner: brain-owner` means the
person named in `/memory/OWNER.md`, and prose says "the owner". Where a concrete value is needed (a
local path, a timezone, an account), mechanics text says "see `/memory/OWNER.md`" instead of
repeating it. Memory files may name the owner directly."

Proposed, added after it:

> Every decision in a brain is its owner's: what to build, what to merge, which rules to accept and
> which skills to switch on. In a brain set up from someone else's original, the upstream
> maintainer (whoever maintains the original repositories) decides only two things: whether a
> contribution offered upstream as a pull request is taken, and who may read a private original.
> An agent never infers the owner from a repository's GitHub account, a remote URL or the Git
> authors in its history, and never sends the owner to the upstream maintainer for a decision about
> their own brain. When `/memory/OWNER.md` is missing, or its front matter has no `owner_name`, the
> agent says so and resumes `/SETUP.md` at the first step not done, instead of guessing who the
> owner is.

### CONTRACT §13.2 (add after "…each substantive change needs its own.")

Decision: the sentence is needed. §13.2 says acceptance covers one change, not later ones, so a
setting that admits future upstream changes would contradict it without an explicit exception.

> One standing acceptance is allowed: an owner who turns `follow_upstream` on (`SMART-RULE-0032`)
> accepts each protected-governance change to the mechanics and the skill library that the upstream
> maintainer has already accepted on upstream `main`, for each upstream merge made while the setting
> is on. It covers nothing made locally, on another branch or offered upstream, and ends when the
> owner turns the setting off. Every change it admits is recorded in
> `/memory/governance/upstream-merges.md` and reported to the owner in the first reply.

### `/RULES.md`, `SMART-RULE-0032`

Current: "**Offer, never push.** A contribution to an upstream repository is a pull request from the
owner's own repository, carrying a proposal file without a rule number, the personal-data check's
result and passing tests, opened only after the owner says yes to that contribution."

Proposed: the same, followed by: "Whether it is taken is the upstream maintainer's decision; every
other decision in the owner's brain is the owner's (CONTRACT §3.6)."

Current: "**Hear upstream on a cadence.** At session start, when a check is due (default every
seven days), fetch `upstream` and tell the owner what changed in their `active_skills`, the core
skills, governance and new skills. Merging is the owner's decision; an upstream change to protected
governance is presented as a proposal (CONTRACT §13.2)."

Proposed:

> **Follow upstream, or hear it.** The owner's setting `follow_upstream` in
> `/memory/skills/skill-exchange/config/settings.json`, asked once at `/SETUP.md` step B4, decides
> how upstream reaches the brain. When it is on, at session start the agent fetches `upstream` and
> merges `upstream/main` into the mechanics and the skill library the way `SMART-RULE-0034` merges
> `origin`: a merge commit, never a rebase or a forced push; a conflicting hand-written file stops
> the merge and is put to the owner; the merged result passes the repository preflight before it is
> pushed to `origin`. The setting is the owner's standing acceptance of protected-governance changes
> the upstream maintainer has already accepted on upstream `main` (CONTRACT §13.2); each merge that
> brings one is recorded in `/memory/governance/upstream-merges.md` (upstream commit, files changed,
> contract version before and after) and reported in the first reply. When it is off or absent, at
> session start when a check is due (default every seven days) the agent fetches `upstream` and tells
> the owner what changed in their `active_skills`, the core skills, governance and new skills;
> merging is the owner's decision, and an upstream change to protected governance is presented as a
> proposal (CONTRACT §13.2).

The index row's `Applies when` becomes "… installing a skill from elsewhere; session start in a
brain with an `upstream`".

### `/SETUP.md`

- Line "…with no `upstream` until its owner grants access." becomes "…with no `upstream` until the
  upstream maintainer grants access."
- Line "…has no `upstream` until the original's owner grants read access." becomes "…has no
  `upstream` until the upstream maintainer grants read access."
- B4 step 6 gains, after the `settings.json` sentence: "When at least one upstream was recorded, ask
  once: "Follow the original automatically? 1. Yes: each session start merges the changes its
  maintainer has accepted, rules included, and tells you what came in (suggested). 2. No: you are
  told what changed and decide each time." Record the answer in the same file as
  `"follow_upstream": true` or `false`."

### `/CONTRIBUTING.md`

Current: "The maintainer decides on each proposal; a declined one can come back with new evidence."
Proposed: "The upstream maintainer decides whether each proposal is taken into the original; a
declined one can come back with new evidence. What runs in your own brain stays your decision
(CONTRACT §3.6)."

### `/shared/skills/skill-exchange/SKILL.md`

- Item 3, current: "**Hear about upstream** – on a cadence, the agent tells the owner what changed
  upstream that touches the skills and rules they use." Proposed: "**Follow or hear upstream** –
  with `follow_upstream` on, the brain merges the original's accepted changes at session start and
  reports them; otherwise, on a cadence, the agent tells the owner what changed upstream that
  touches the skills and rules they use."
- Configuration: the example gains `"follow_upstream": true`, explained as "the owner's choice at
  SETUP B4; absent means off (`SMART-RULE-0032`)".
- Section 4 opens with: "With `follow_upstream` on, `sync.py` merges upstream at session start and
  the digest below describes what was merged; the owner is not asked. With it off, as follows."
  The closing paragraph on governance gains: "…waits for explicit acceptance (CONTRACT §13.2),
  unless `follow_upstream` is on, which is that acceptance for changes already accepted on upstream
  `main`."

### Generated and version files

`/CORE.md` and `/CORE-RULES.md` are rebuilt by `core.py` (§3.6 and §13 are in the core);
`contract_version` 3.1.0 becomes 3.2.0 in `/CONTRACT.md` and the manifests.

## Reason

The owner of a brain must never be redirected to another person for their own decisions, and
nothing in the mechanics stops an agent inferring the owner from repository metadata. A brain set
up from an original falls behind silently when merging depends on a yes the owner does not know to
give.

## Scope and behavioural consequences

- Every brain: agents route all decisions to the person in `/memory/OWNER.md` and resume setup when
  it is missing, instead of guessing. Minor version: compatible with existing content.
- Brains with `follow_upstream` on: upstream `main` arrives at session start, governance included,
  with a record and a first-reply report. Brains without the setting behave as today.
- The original's own brain has no `upstream` and is unaffected.

## Risks and conflicts

- **Trust.** Upstream scripts run with the owner's credentials without being read first. Mitigated:
  the setting is opt-in and per brain; the report names changed scripts; turning it off restores
  review. `SMART-RULE-0032` *Record provenance* covers installs from other brains, not the original.
- **Preflight coverage.** The protected-change check may refuse governance commits arriving by
  merge, or fall outside the seven-day window of upstream's proposal. The preflight must treat an
  upstream-merge record as coverage, or the merge stops at preflight and is reported (safe failure).
- **Owner-layer conflicts.** An upstream rule can conflict with `/memory/RULES.md`; the owner layer
  still only adds constraints, and `SMART-RULE-0036` raises the conflict.
- **Local governance edits** in the owner's mechanics conflict on merge and stop for the owner.

## Migration

Existing brains have no `follow_upstream` key and stay off. On the next session start in a brain
with `upstreams` but no `follow_upstream`, the agent asks the B4 question once.

## Rollback

Revert the commit on `main` and restore `contract_version` 3.1.0. Owners set `follow_upstream` to
`false`; merges already made stay and can be reverted one by one from the record.

## Code changes after acceptance (not built here)

- `sync.py`: for the mechanics and the library, when `follow_upstream` is true and `upstream`
  exists, fetch it, merge `upstream/main` in a session copy with the `SMART-RULE-0034` routine,
  run the preflight, push to `origin`, fast-forward the shared checkout, append the record to
  `/memory/governance/upstream-merges.md` and print a summary line.
- The session-start hook (being built separately) prints that summary for the first reply.
- `skill_exchange.py`: reuse the digest to describe a completed merge; skip the "due" question when
  following.
- Preflight: accept protected changes arriving through a recorded upstream merge.
- `core.py`: rebuild the core parts.

## Validation

- Preflight passes on the proposal branch; `core.py check` passes after the rebuild.
- Personal-data check: no owner or maintainer name in any target.
- Tests for `sync.py`: following on, a clean merge, a hand-written conflict that stops, a failing
  preflight that pushes nothing; following off, nothing merged.
- A before-and-after scenario: an invited person's brain with `/memory/OWNER.md` missing must
  resume setup, and with it present must never name the upstream maintainer for an owner decision.

## Acceptance

Accepted by the owner at 2026-11-08T11:04:23+10:00, answering "Accept" to "Accept PROPOSAL-follow-upstream as written?".

## Implementation record

Implemented at 2026-11-08T11:07:00+10:00 (contract 3.1.0 to 3.2.0). Files changed: `/CONTRACT.md` (section 3.6, section 13.2, `contract_version`), `/RULES.md` (`SMART-RULE-0032` and its index row), `/SETUP.md`, `/CONTRIBUTING.md`, `/shared/skills/skill-exchange/SKILL.md`, `/CORE.md` and `/CORE-RULES.md` (rebuilt by `core.py`), `/repository-manifest.json`, `/shared/templates/library-skeleton/repository-manifest.json`, the manifests of the memory and library checkouts, and this proposal. The code changes (the `sync.py` upstream merge and the rest of "Code changes after acceptance") are built by a separate packet.
