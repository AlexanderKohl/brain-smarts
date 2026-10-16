---
id: PROPOSAL-worker-model-and-effort-chosen-per-packet
title: The conductor chooses each worker's model and effort from the packet
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: draft
owner: brain-owner
created: 2026-10-16T15:23:32+10:00
updated: 2026-10-16T15:23:32+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.5.0
new_contract_version: 2.5.0
target_files:
  - /shared/skills/delegate-work/SKILL.md
  - /shared/skills/delegate-work/hosts/claude-code.md
  - /shared/skills/delegate-work/scripts/delegation.py
  - /shared/skills/delegate-work/templates/packet.template.md
---

# The conductor chooses each worker's model and effort from the packet

Read `/CONTRACT.md` first. The delegate-work skill is not protected governance (CONTRACT §13.2);
this file records the change because it changes how every conductor works, and the owner asked to
see it before it applies.

## Current problem

*Choosing a worker's model* ties kinds of work to models: a packet that leaves no judgement goes
to the implementation worker type, every other packet goes to the judgement worker type (on Claude
Code a pinned, specialised model) or inherits the conductor. In practice almost every code packet
needs some judgement, so almost every worker ran on the one specialised model and spent its
allowance, while the cost of a wrong result, the reading load and the allowance left were never
weighed. Effort was fixed by the worker type and never raised before the model was.

## Current wording

`/shared/skills/delegate-work/SKILL.md`, *Choosing a worker's model*, first two paragraphs: "A
packet that leaves no judgement names the implementation worker type; every other packet inherits.
… a packet that needs more judgement than that but less than the conductor names the judgement
worker type (`worker-fable-medium`); a packet that needs the conductor's own model and effort keeps
`inherit`." and the definition of "leaves no judgement".

## Proposed wording or exact diff

Replace the section *Choosing a worker's model* up to (not including) "A read-only packet lets the
worker use the scoped bootstrap tier" with:

```markdown
### Choosing a worker's model and effort

**The conductor chooses a model and an effort for every packet from what that packet needs, and
writes the choice and a one-line reason on the packet** (`--model`, `--effort`, `--model-reason`).
No kind of work is tied to one model.

It weighs, in this order:

1. **What a wrong result costs.** Rework only; something a person sees; stored data, money,
   security or production.
2. **How much judgement the packet leaves.** None: the files, the change and the acceptance are
   spelled out. Bounded: one area, a few reasonable choices. Open: design, trade-offs, research
   that must weigh evidence.
3. **How much the worker must read.** A large reading load favours the model that is cheapest per
   token at the quality the first two need.
4. **The allowance left.** The conductor reads the host's usage before dispatching (the host note
   says how). A model past 75 % of its period's allowance is chosen only when no other fits, and
   the reason says so.

The ladder, lowest first; the host note maps it to model names:

| Packet | Model and effort |
|---|---|
| no judgement, rework only | the cheapest model that writes code reliably; low or medium effort |
| bounded judgement, or a person sees the result | the current Opus-class model; medium effort |
| open judgement, or data, money, security or production | the Opus-class model at high effort, or the conductor's own model and effort (`inherit`) |
| open judgement where a specialised model is known to do better, and its allowance is healthy | that model; the reason names why |

**Effort rises before the model does:** the next step up for a packet is the same model at a
higher effort, then the next model. A worker that comes back weak is resumed or re-run one step up
the ladder, and the run's log says so. Repeated step-ups for one kind of packet are a learning
(`SMART-RULE-0028`) and move that kind's default up the ladder.

The reason for weighing cost first is arithmetic: a worker that misreads a packet costs a full
re-run plus the conductor's merge time, which is more than the saving on the first run. The
result records what actually ran, so a packet that named one model and a worker that reports
another shows up at validation.
```

`hosts/claude-code.md`, the mapping table: the rows for `model: worker-opus-medium or
worker-fable-medium` and `model: <other name>` become:

```markdown
| `model` and `effort` | the Agent tool's `model` (`haiku`, `sonnet`, `opus`, `fable`) and `effort` parameters on a `general-purpose` worker; the pinned types (`worker-opus-medium`, `worker-fable-medium`) remain shortcuts for their pair. Ladder on Claude Code: `sonnet` medium; `opus` medium; `opus` high or `inherit`; `fable` only for open judgement with its allowance healthy |
| allowance | `get_usage` (`plan.windows`, per-model weekly percentages) before every `new-run` and `new-packet` |
```

`scripts/delegation.py` and `templates/packet.template.md`: `new-packet` takes `--model-reason`,
required whenever `--model` is given, and writes it into the packet's front matter as
`model_reason`; a test covers the refusal without it.

## Reason

The owner, 16 October 2026: "I want the conductor to actively decide which model and effort workers
should use based on the task they need to do. However, pushing everything that needs some judgment
to fable is not the correct approach for that." The earlier owner-layer draft
(`PROPOSAL-workers-on-opus-medium`, one fixed model for all workers) was withdrawn as too
prescriptive.

## Scope and behavioural consequences

Every conductor on every host: one more decision per packet, written down with its reason; most
code packets land on the Opus-class model at medium effort; the specialised model is used when a
packet earns it and its allowance allows. Validation still compares the model named with the model
that ran.

## Risks and conflicts

A conductor may under-choose to save allowance; the step-up rule and the learning record catch a
kind of packet that keeps failing. No conflict with `SMART-RULE-0024`, which only requires that the
model that ran is recorded.

## Migration

None. Running workers finish on their model. The pinned worker types stay.

## Rollback

Restore the section from Git history; drop `--model-reason` (or make it optional).

## Validation

`python -m unittest discover -s shared/skills/delegate-work/scripts/tests` passes with the new
test; `preflight.py` passes; the next run's packets carry `model_reason`.

## Acceptance

Not yet requested. Ask one direct question that identifies this proposal.

## Implementation record
