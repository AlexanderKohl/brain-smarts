---
id: PROPOSAL-worker-model-default
title: Implementation packets run on a worker type that pins an Opus-class model at medium effort
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
rule_id: SMART-RULE-0024
accepted_by: brain-owner
accepted_at: 2026-10-14T19:50:39+10:00
implemented_at: 2026-10-14T19:50:39+10:00
created: 2026-10-14T19:38:30+10:00
updated: 2026-10-14T19:50:39+10:00
previous_contract_version: 2.4.0
new_contract_version: 2.4.0
target_files:
  - /shared/skills/delegate-work/SKILL.md
  - /shared/skills/delegate-work/hosts/claude-code.md
  - /shared/skills/delegate-work/templates/packet.template.md
  - /.claude/agents/worker-opus-medium.md
  - /.claude/agents/worker-fable-medium.md
---

# Implementation packets run on a worker type that pins an Opus-class model at medium effort

Read `/CONTRACT.md` first. This proposal changes the delegation skill's section *Choosing a
worker's model*, adds an `effort` field to the packet, and adds two worker definitions for the
Claude Code host that pin a model and an effort level regardless of the conductor's own setting.
It changes no contract wording; it changes an operating rule the owner accepted with the
delegation skill, so it is put to the owner rather than applied.

## Summary in plain language

Today every packet inherits the conductor's model and, on Claude Code, the conductor's effort
level, and the skill says a smaller model may be named only packet by packet, never as a standing
rule. The owner's trial found that effort, not model, set the clock: at maximum effort a one-minute
card took the Opus worker thirteen minutes and the Fable worker ten, and single requests ran up to
nine minutes; at medium effort both finished in about a minute with the same result. It also found
that Opus 5.5 at medium effort matched Fable 5.1 on every implementation card tried, at two and a
half times less per token. Under this proposal an implementation packet that leaves no judgement
goes to a worker type that pins Opus 5.5 at medium; the conductor stays on its own model and
effort; packets that need more judgement name the Fable worker type or inherit.

## Current wording

`/shared/skills/delegate-work/SKILL.md`, *Choosing a worker's model*:

> **`inherit` is the default and stays the default**. Name a smaller model only for a packet whose objective
> leaves no judgement, and decide that packet by packet, never as a standing rule for a class of
> work.
>
> A packet leaves no judgement when every decision is already made in it: the files are named,
> the change is spelled out, the acceptance is a command that passes or fails, and nothing in it
> asks the worker to weigh evidence, choose between two reasonable shapes, or decide whether
> something could be verified. If the objective contains the words *decide*, *judge*, *check
> whether*, *if you cannot verify*, or an option for the worker to choose between, it does not
> qualify.
>
> The reason for the caution is arithmetic, not taste: a worker that misreads a packet costs a
> full re-run plus the conductor's merge time, which is more than the saving on the first run.
> The result records what actually ran, so a packet that named one model and a worker that
> reports another shows up at validation.

`/shared/skills/delegate-work/hosts/claude-code.md`, the mapping rows for `model`:

> | `model: inherit` | omit the model parameter |
> | `model: <name>` | the `model` parameter, only from the host's offered list; the result must record what ran |

## Proposed wording

`/shared/skills/delegate-work/SKILL.md`, *Choosing a worker's model*, first paragraph becomes:

> **A packet that leaves no judgement names the implementation worker type; every other packet
> inherits.** The implementation worker type is the host's definition that pins the current
> Opus-class model at medium effort (on Claude Code, `worker-opus-medium`); a packet that needs
> more judgement than that but less than the conductor names the judgement worker type
> (`worker-fable-medium`); a packet that needs the conductor's own model and effort keeps
> `inherit`. The conductor decides packet by packet, by the test below, and the result records
> what actually ran.

The second and third paragraphs are unchanged. A fourth is added:

> A packet carries an `effort` field beside `model`: `inherit` (default) or one of the host's
> effort levels. A worker type's pinned effort overrides it; the host note says how each host
> honours it.

`/shared/skills/delegate-work/hosts/claude-code.md`, the two mapping rows become three:

> | `model: inherit` | omit the model parameter; the subagent runs at the conductor's model and effort |
> | `model: worker-opus-medium` or `worker-fable-medium` | the `subagent_type` parameter; the definition in `/.claude/agents/` pins the model and medium effort whatever the conductor's setting |
> | `model: <other name>` | the `model` parameter, only from the host's offered list; effort follows the conductor's session; the result must record what ran |

and a paragraph under *Known limits*:

> A subagent inherits the conductor's effort level unless its definition pins one. At maximum
> effort an implementation card that takes a minute at medium can take ten or more, so a packet
> that does not name a worker type runs at whatever the conductor is set to. A definitions folder
> created during a session is watched only from the next session.

`/shared/skills/delegate-work/templates/packet.template.md`: the control fields gain
`effort: inherit`.

`/.claude/agents/worker-opus-medium.md` and `/.claude/agents/worker-fable-medium.md` are added to
the mechanics repository, each with front matter `model`, `effort: medium` and the six tools an
implementation worker uses (Read, Write, Edit, Bash, Glob, Grep), and a body that states the
worker's duties and report format as the delegation skill defines them.

## Reason

Measured on 14 October 2026 by the owner's conductor (recorded in the memory's project nodes):
on an implementation card with every decision fixed, Opus 5.5 at medium took 1.0 minute with no
fix, Fable 5.1 at medium 1.5 minutes, both passing every test and probe; at maximum effort the
same workers took 13.7 and 10.1 minutes for the same result, with single requests of 556 and 405
seconds. Opus 5.5 costs $4 and $20 per million input and output tokens against $10 and $50 for
Fable 5.1 at the time of writing. The tool schemas were 34,000 of a worker's 39,000 first-request
tokens; six tools cut that to 5,400, which the worker definitions' tool list applies to every
worker.

## Scope and consequences

- The conductor's own model and effort are untouched. The change moves no judgement to a cheaper
  model: the packet test that already exists decides which packets qualify.
- Any host that offers no worker types falls back to the `model` parameter and the session's
  effort, which the host note records.
- The skill's statement "never as a standing rule for a class of work" is replaced by a standing
  rule for one class, packets that leave no judgement, which the trial measured.

## Risks and migration

- A worker type pins a named model; when the current Opus-class model changes, the definition
  changes with it, as an ordinary change.
- Workers at medium effort may think less on a hard packet. The test for "leaves no judgement"
  is the guard; a packet that fails it inherits.
- No migration: existing packets have no `effort` field and are read as `inherit`.

## Rollback

Revert the commit that applies this proposal; delete the two definition files. Packets then
inherit as before.

## Validation

- The repository preflight passes on the mechanics; the personal-data check passes on the two
  definition files.
- The next delegation run dispatches at least one packet to `worker-opus-medium`, and its result
  records that model and passes `validate-result`.

## Acceptance

The owner accepts or declines `PROPOSAL-worker-model-default` as one answer. On acceptance the exact
wording above is applied and the acceptance is recorded in the memory's governance proposals.

## Implementation

Accepted by the owner on 14 October 2026 ("1. accept 2. accept 3. ok") and applied the same evening, exactly as worded above. Validation: the repository preflight passed on the mechanics, the skill library and the memory after the change. Tool: Claude Code desktop, Claude Fable 5.1.
