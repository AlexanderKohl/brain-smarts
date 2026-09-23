---
id: RULE-2026-0037
title: Delegated parallel work
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-15T07:45:00+10:00
updated: 2026-09-15T08:19:04+10:00
accepted_by: brain-owner
accepted_at: 2026-09-15T08:19:04+10:00
implemented_at: 2026-09-15T08:19:04+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
skill_refs:
  - /shared/skills/delegate-work
---

# Delegated parallel work

## Current problem

Agents on every host can now launch other agents, and the owner wants one agent to hand work to
several others so they run in parallel. Nothing in the contract or root rules says how. The
existing rules touch the edges only: `RULE-2026-0010` says match a subagent's capability to the
job, `RULE-2026-0023` says the primary agent commits and subagents hand over changed paths,
`RULE-2026-0028` uses distinct models as reviewers, and the credential rules forbid parallel
processes each holding the passphrase.

Without a rule, the predictable failures are: a conductor copies its whole conversation into
each worker; workers write to `STATE.md` and `LOG.md` concurrently in one worktree; a worker
uses a credential or takes an external side effect nobody confirmed; work packets are filed as
`/tasks/` records with statuses the validator rejects; one vague request fans out into dozens of
agents; and a host that ran packets in sequence is reported as parallel.

The owner supplied a reference architecture on 2026-09-15 (conductor, durable queue, leases,
worker registry, scheduler, artifact store). The review recorded in the brain-development log
kept its packet and result design and rejected the runtime parts, because the brain has no
runtime: no daemon, queue, scheduler or database, and the only durable coordination layer is the
filesystem under Git. The operating procedure is now `/shared/skills/delegate-work/`. This rule
carries the behavioural minimum that must not be weakened by the skill.

## Current wording

None. This is a new root rule.

## Proposed wording or exact diff

Add to `/RULES.md`, after `RULE-2026-0035` and before the contract-restatement list:

```markdown
## RULE-2026-0037 – Delegated parallel work

- Delegate to another agent only work that is independent, bounded and consumable as a
  compressed result: one clear outcome, no back-and-forth with sibling workers, and a result
  the conductor can use without the worker's reasoning. Before dispatching, state in one line
  why parallel workers beat doing the work in sequence. Tightly coupled reasoning, sequential
  implementation and work that needs constant shared state stay with one agent.
- Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
  files rather than copying prose, and a result record the worker writes back. Packets and
  results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
  must outlive the session is an ordinary `/tasks/` record with `waiting_on` and `next_review`.
- Workers start isolated by default. A packet that forks the conductor's context states why.
- Workers do not write canonical repository files and do not commit. They return findings,
  artifacts inside their run folder, and every changed path with its validation result. A
  worker that must change code works in an isolated worktree or branch (`RULE-2026-0023`); the
  conductor merges, commits and reports.
- Workers use no credentials and take no external side effect unless the packet names a target
  the owner confirmed for this operation under CONTRACT §10.5. The default is none. A worker
  that needs an owner decision stops with status `blocked` and the question; it does not guess.
- Budget: depth one (workers do not delegate) and at most four workers per run, until a
  measured trial recorded under `/projects/brain-development/` justifies more.
- The conductor routes each result under CONTRACT §5 and §6, treats worker claims as
  unverified until checked, writes one `LOG.md` entry per run in the owning node, and does the
  Git accounting under `RULE-2026-0023`. Never claim parallel execution on a host that ran
  packets in sequence. Record the host and the model that actually ran each packet; never
  invent one.
```

Append `0037` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0037`.

## Reason

- **Independence test first.** Anthropic's published experience with orchestrator-worker
  systems is that early orchestrators spawned dozens of agents for simple questions until
  explicit delegation heuristics were added, and that multi-agent runs cost many times the
  tokens of a single session. `RULE-2026-0004` already demands token efficiency; the one-line
  reason makes the trade visible.
- **References, not copies.** The brain's canonical-home principle (CONTRACT §3.3) already
  gives workers a way to retrieve exactly what they need. Copying a conversation into each
  worker duplicates context and spreads the conductor's assumptions.
- **Packets are not tasks.** CONTRACT §9.3 says do not create a task for work completed inside
  the interaction, tasks have one human-accountable owner, and the preflight validator rejects
  any status outside the eight defined. A minutes-long worker packet fits none of that.
- **Read-only workers by default.** Full bootstrap before durable writes (CONTRACT §1) costs
  about 1,200 lines per worker; concurrent appends to one `LOG.md` in one worktree corrupt it;
  `RULE-2026-0023` already makes the primary agent the committer. Workers that only read can
  use the scoped bootstrap tier and return results the conductor routes.
- **Fail closed on credentials and targets.** CONTRACT §10.5 and `RULE-2026-0034` already
  require a confirmed target and forbid guessing. A worker cannot ask the owner, so the only
  safe default is none and the only escalation is `blocked`.
- **Honest host reporting.** Not every host can run agents in parallel. Claiming otherwise
  would misstate what evidence a result rests on.

## Scope and behavioural consequences

Repository-wide, all agents and all hosts. It constrains how delegation happens; it does not
require delegation. Existing single-agent work is unchanged.

Consequences: conductors will sometimes decline to fan out and say why; workers will return
`blocked` more often than they guess; run folders will appear under `/temp/delegation/runs/`
and are safe to delete; each run adds one `LOG.md` entry to the owning node.

No `contract_version` change: a root rule, not contract behaviour, following the precedent of
`RULE-2026-0032`.

## Risks and conflicts

- **Under-use.** The four-worker, depth-one budget may be too tight for large research runs.
  Mitigated by naming the path to raising it: a measured trial recorded in brain-development.
- **Skill drift.** The skill could accumulate operational detail that weakens the rule.
  Mitigated by the final bullet of the rule making the rule the ceiling, as `RULE-2026-0028`
  does for the product-development skill.
- **Host claims.** Host notes in the skill describe facilities that change between releases.
  Mitigated by requiring the result to record what actually ran and by marking unverified hosts
  as such in the notes.
- Complements `RULE-2026-0010` (capability matching), `RULE-2026-0023` (commit ownership),
  `RULE-2026-0028` (multi-model review remains a review activity, not delegation) and
  `RULE-2026-0032` (the result sections mirror the handoff checkpoint). No conflict found with
  the credential rules: workers hold no credentials.

## Migration

None. Applies from activation. The skill, its script and tests, the `/temp/delegation/` folder
and the tracking task `TASK-2026-0032` exist before activation and are not protected governance.

## Rollback

Remove the `RULE-2026-0037` section from `/RULES.md`, drop `0037` from the root ID list,
restore `accepted_proposal` to its previous value, and set this proposal's status to
`reverted`. The skill can remain as an unmandated procedure or be deleted separately.

## Validation

- `python -m unittest discover -s shared/skills/delegate-work/scripts/tests` passes (22 tests
  at proposal time).
- Repository preflight before and after activation reports the same error count.
- Governance coverage is satisfied by this proposal once accepted, `target_files` naming
  `/RULES.md`.
- The Phase 3 trial run on Claude Code, recorded in the brain-development log, demonstrates the
  packet, result, validation and synthesis path end to end.

## Acceptance

**Question to ask:** Do you accept proposal `RULE-2026-0037`, adding the delegated parallel
work rule to `/RULES.md` with exactly the wording set out above?

**Accepted by the owner, 2026-09-15T08:19:04+10:00**, in the exact words "I accept RULE-2026-0037 implement it", after the plain-language summary and the exact wording above were presented in the conductor's reply of 2026-09-15 alongside the Phase 3 trial results.

## Implementation record

Implemented 2026-09-15T08:19:04+10:00. `RULE-2026-0037` added to `/RULES.md` with the accepted wording unchanged, placed after `RULE-2026-0035` and before the contract-restatement list. `0037` appended to the root ID list; `accepted_proposal` now reads `RULE-2026-0037`. `contract_version` unchanged at 0.9.0. Skill tests (22) pass; repository preflight passes with the same pre-existing warning set; manifest regenerated. `TASK-2026-0032` closed.
