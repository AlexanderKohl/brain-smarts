---
id: skill-product-development
name: product-development
title: Product Development
description: Guide new and existing software products, internal tools and feature changes through evidence-based, investment-proportionate discovery, design, implementation and lifecycle gates.
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
owner: brain-owner
created: 2026-09-03T14:05:35+10:00
updated: 2026-09-23T12:00:00+10:00
source_refs:
  - /memory/sources/source-71ae7cca6b7a-product-development-process.md
---

# Product Development

## Purpose

Guide anything the owner and an AI agent build together through a proportionate product-development process. The agent performs the research, analysis, drafting, testing and evidence collection that are safely possible, then presents a concise decision pack so the owner can make informed gate decisions.

Use this skill for:

- a new software product or internal tool
- assessment of an existing product
- a feature, integration or material change to an existing product
- a decision about whether to build, buy, integrate, continue or stop
- planning, designing, implementing, releasing or reviewing software

Clearly non-material work needs ordinary engineering discipline, not a ceremonial product review. Examples include copy or formatting corrections, mechanical refactors with no intended behaviour or interface change, and like-for-like repairs already bounded by accepted behaviour and tests. Use a compact light-path note for a small reversible behavioural improvement, such as an internal saved filter. Escalate to standard or high-assurance depth for new workflows, integrations, customer-facing or commercially positioned capabilities, authentication, payments, sensitive data, autonomous AI actions or other material investment and risk.

## Required inputs

- the opportunity, project or proposed change
- the active Brain project node, creating one only when the contract's node threshold is met
- known constraints, prior decisions and available evidence
- an initial estimate of investment and consequence; refine this during triage

## Allowed operations

- Classify the entry, choose the depth, and create or update the product-development record.
- Research, test, prototype and prepare evidence and gate decision packs for the owner.
- Run independent-model reviews within the permissions of the models available.
- Record decisions, state, tasks and log entries under the contract. Nothing here authorises an external write, purchase, deployment or publication.

## Data sources

- The owning project's `README.md`, `STATE.md`, `KNOWLEDGE.md`, `LOG.md`, plan or product record, and `/memory/tasks/`.
- The process references under `references/` (process, project record, multi-model review).
- Project source material under the project's `sources/` and `/memory/sources/`, and evidence gathered during the stage.

## Scripts or commands

None. This skill is a process. It uses the project's own tooling and the shared access skills as the work requires.

## Core operating rules

1. Treat the process as iterative. A failed gate sends work to the relevant earlier stage; it does not merely halt a linear checklist.
2. Reuse valid prior evidence and decisions. For an existing product or feature, establish its current position first and traverse only the affected gates.
3. Always consider both internal and commercial routes. Record each as `primary`, `secondary`, `future option` or `not currently justified`; do not force full commercial research for a clearly low-investment internal change.
4. Scale the work to investment, uncertainty, reversibility, affected users, security/privacy exposure, operational criticality and potential blast radius. Read [the adapted process](references/process.md) for depth levels and gates.
5. Research before questioning the owner when the answer can be established safely. When several owner inputs would materially improve the same decision, ask them together in a clearly grouped questionnaire, with evidence and a proposed default where useful.
6. The agent owns evidence gathering and presentation. The owner owns each gate decision unless an accepted active rule explicitly authorises autonomous passage for that gate and risk class.
7. A gate decision must be explicit and recorded. Do not interpret silence, implementation momentum or previous spending as approval.
8. Keep the process record current rather than generating disconnected planning documents. A low-risk light change may use a compact entry in an existing canonical plan, feature specification or task instead of creating a dedicated lifecycle document. Read [the project record specification](references/project-record.md) when creating or updating it.
9. Use independent model reviews at the stages and depth defined in [the multi-model review protocol](references/multi-model-review.md). Different prompts to one model are useful lenses but are not represented as independent-model review.
10. Preserve authorization boundaries. Research and recommendations do not authorise external writes, purchases, deployments, publication or production access.
11. **Hand over a decided specification, never an open one.** A research or design increment settles every outstanding decision with the owner before the work passes to whoever builds it, and records the answers in the canonical specification with the date. Say which answers changed the design rather than confirming it, correct the spec's own prose where they did, and flag any decision the owner deliberately left open with who decides it and when. The task record carries the signal: `ready` with `waiting_on: null` means dispatchable. Procedure in `/shared/skills/delegate-work/SKILL.md`, *Research and design threads: clarify, then hand back*. Rule adopted 16 September 2026.

## What a day of shipping taught, 17 September 2026

Eleven versions and nine defects in one session of a browser-extension product. Four rules came out of it
that are not about that product. Each names the incident, because a rule without its reason is
optimised away by the next reader.

12. **An instrument that cannot fail is not an instrument, and one that fails silently is worse than
    none.** In one session: a graph builder that dropped a finding's references without a word when
    it could not resolve a node; a probe printed at a console level Chrome hides by default; a
    harness assertion that read a CSS default and matched the code **by coincidence**, so it would
    have passed whatever the code said; and a mark written to a custom property nothing read, which
    logged *marked* while painting nothing. So: **before trusting a new check, make it fail on
    purpose once** - change the value it asserts and watch it go red. **Anything a check declines to
    do, it says out loud**: a silent drop, a skipped item, an unresolved reference. A defect can only
    be found in the place the product admits to it.

13. **A symptom that survives one fix forbids a second theory.** Get evidence before changing
    anything. Two plausible causes were built and shipped against one symptom before anybody looked
    at the actual DOM; the third attempt printed what it saw instead, and the answer was neither.
    **A refuted hypothesis is a result** - a worker that proves the conductor wrong and stops has
    done the job, and building the fix anyway would have hidden the cause under a change that looked
    like progress.

14. **A real account is evidence; a fixture is coverage.** A capture from the customer's own system
    tells you what is true there and nothing else: on 16 September a whole asset kind was missing from
    a page for weeks, and the reference account **could not have shown it**, because that account
    holds none of that kind. Report numbers from the real account - they are what the owner
    recognises - and cover the space with a fixture that reaches everything the code can emit.
    Neither substitutes for the other.

15. **The second copy is the defect.** Five faults in one week had one shape: two things that had to
    agree with nothing keeping them in step - two view lists, an exception list and the dialogs built
    after it, one id built two ways, an export table copied by hand into a harness, and two stores
    over one storage key, which erased a person's work. **When a second copy of anything is
    introduced - a list, an id, a table, a store - the test that compares the two ships in the same
    commit.** A comment asking the next person to remember is what the first four had.

**And one about reporting, which is the owner's interest rather than the work's.** Say the number
that contradicts the hope: *the width you asked for did not shorten the page, and here is why*;
*the tallies did not move, because the defect never reached your screen*. A report that only
contains good news has to be read twice, and the second reading is the expensive one.

## Workflow

### 1. Classify the entry

Classify the work as one of:

- `new_product`
- `existing_product_baseline`
- `feature_or_change`
- `urgent_repair`
- `lifecycle_review`

For an existing product, reconstruct the current lifecycle position from code, documentation, observed operation, user evidence and prior Brain decisions. Mark unknowns; do not pretend earlier gates were passed merely because software exists.

For a feature or change, identify which product assumptions and system boundaries it affects. Reopen only the necessary gates, while checking downstream consequences through release and operation.

For an urgent repair, restore safe operation first when authorised, then perform the smallest useful retrospective review. Do not use this exception to disguise planned feature work.

### 2. Choose proportional depth

Choose `light`, `standard` or `high-assurance` using the criteria in the adapted process. Record the reasons. Increase depth whenever new evidence exposes greater risk or investment; decreasing depth requires a recorded reason.

### 3. Establish or update the process record

Prefer the project's existing canonical product plan when it can hold the required state. For a low-risk light change, a compact section in an existing canonical plan, feature specification or task is sufficient; record the outcome, depth reason, affected gates, evidence, decision and next action without reconstructing the entire lifecycle. Otherwise create `/memory/projects/<project>/PRODUCT-DEVELOPMENT.md` using the specification. The record must show what is known, current phase, affected gates, decisions, evidence freshness, open questions and next action.

### 4. Perform the applicable work

Work through the adapted phases and gates at the selected depth. The agent should proactively:

- inspect relevant Brain context and project artefacts
- research authoritative external sources when needed
- compare existing products, components, APIs and internal capabilities
- analyse internal value and commercial potential
- draft scope, journeys, prototypes, architecture, risks, tests and release plans
- perform permitted validation and collect results
- expose uncertainty, contradictory evidence and assumptions
- maintain tasks and project state under the contract

### 5. Run stage reviews

At required checkpoints, obtain independent reviews using the multi-model protocol. Synthesize agreements and disagreements; never substitute a vote count for evidence or the owner's decision.

### 6. Present a gate decision pack

Every decision pack contains:

- decision requested
- recommended decision and why
- investment authorised by a `proceed` decision
- evidence, with source and freshness
- internal-use and commercial-route conclusions
- assumptions and confidence
- material risks and mitigations
- independent-review findings and disagreements, when applicable
- questions that require the owner's judgement
- options: `proceed`, `revise`, `pause` or `stop`
- proposed next phase, depth and actions

Ask related clarification questions in bulk when that helps the owner reason about the gate. Separate essential decisions from questions for which the agent has a safe proposed default.

### 7. Record and continue

After the owner decides, record the decision, rationale, conditions and authorised next investment. Update current state and tasks. Continue without repeating already settled questions unless evidence has materially changed.

## Outputs

- current project-development record
- evidence and source references
- prototypes, plans, designs, tests or implementation appropriate to the stage
- gate decision packs and recorded decisions
- independent-model review records when required
- updated project state, tasks and significant-event log entries

## Permissions and failure behaviour

- Read and analyse project and source material within normal permissions.
- Create or update Brain planning, source, state, task and log records as allowed by the contract.
- Obtain separate approval for actions that otherwise require it, including protected governance changes and consequential external side effects.
- If evidence is unavailable, label the gap and its decision impact. Do not manufacture confidence.
- Before sending evidence to another model or provider, check that the provider is permitted and remove secrets and unnecessary personal, customer, security-sensitive or commercially sensitive material. Obtain approval when sharing the necessary context would exceed existing authorization.
- If independent models are unavailable, disclose that limitation and use clearly separated review lenses only as a fallback.
- If the applicable project, decision owner or risk boundary is genuinely ambiguous, stop before the affected gate and ask the owner.

## Repository updates

- Put durable product facts in the owning project's `KNOWLEDGE.md` and current lifecycle state in `STATE.md`.
- Record material gate decisions and releases in the project's `LOG.md`.
- Put outstanding actions in canonical `/memory/tasks/` records.
- Keep detailed evolving process evidence in the project-development record rather than bloating state or knowledge.
- Do not modify active governance merely because a gate suggests a useful future rule; use the protected proposal process.
