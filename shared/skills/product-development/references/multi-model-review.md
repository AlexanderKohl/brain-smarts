---
id: product-development-multi-model-review
title: Multi-model Product Review Protocol
type: process_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-03T14:05:35+10:00
updated: 2026-09-28T13:44:41+10:00
---

# Multi-model Product Review Protocol

Independent review is advisory evidence, not a gate vote or a substitute for customer evidence, representative users, specialists or the owner's decision. This is the canonical procedure for `SMART-RULE-0016`, used by every brain project conductor, including non-software work and a sole agent coordinating its own work.

## Suggestion and owner decision

At meaningful stage boundaries, consider whether a review could change a consequential decision and whether finding the issue later would cost materially more. Proactively suggest review when worthwhile. Name the decision or artifact, why this is a useful moment, the coverage, proposed independent reviewer, and likely time/token cost when estimable. State uncertainty rather than invent an estimate. Include one clarification exchange in the proposed scope unless the owner specifies otherwise.

The owner decides whether to run the review at every depth. A direct request for a review supplies approval for its stated scope; otherwise wait for an explicit answer. Do not launch automatically, interpret silence as approval, repeatedly ask after a decline without new evidence, or add review ceremony to routine low-value changes. Continue unrelated authorised work while the decision is pending, without crossing an unresolved gate.

- `Light`: suggest only when a particular uncertainty or consequence justifies the cost.
- `Standard`: consider the opportunity/build-versus-buy, scope/design and implementation/release boundaries; combine adjacent reviews when one package can answer them adequately.
- `High-assurance`: suggest each material opportunity, design and release checkpoint, with relevant specialist coverage. Owner approval is still required; record declined or deferred reviews and residual uncertainty without waiving other gate requirements.

For a feature iteration, review affected areas rather than repeat the lifecycle. A separate release review is useful when configuration, migration or rollout introduces risks not settled in code review. Post-launch reviews are triggered by evidence or investment decisions, not routine calendars. An urgent authorised repair prioritises safe restoration, with a review suggestion afterwards where useful.

## Stage-specific scope

Stages are ordered by lifecycle. Select applicable stages and tailor their depth; do not impose the software lifecycle on a non-software project.

| Stage | Review coverage | Clarification should resolve |
|---|---|---|
| Opportunity and market research, Gates 1–2 | Target users and buyers; problem severity and frequency; source quality, freshness and contradictions; alternatives; switching barriers; willingness to pay; acquisition channels; facts versus assumptions | Which conclusions have evidence? Which assumption could overturn the opportunity? What research would change the decision? |
| Build, buy and economics, Gate 2 | Credible alternatives including doing nothing; fair comparison; integration and migration effort; lifecycle cost; support burden; vendor dependency; commercial assumptions and sensitivity | Is custom development justified? Are costs or constraints missing? Would a smaller purchased or integrated solution deliver the outcome? |
| Product boundaries and scope, Gates 3–4 | Outcomes; scope and exclusions; business rules; permissions; data ownership; dependencies; acceptance criteria; primary and exception journeys; conflicting requirements | Could builders interpret this differently? Which decisions are implicit? What is necessary now and what can wait? |
| UX and interaction design, Gate 5 | Rendered screens and interactions; journey completeness; clarity; accessibility; product conventions; empty/loading/error states; cancellation and recovery; user effort | Can users understand the state and next action? What happens off the happy path? Does the design match agreed behaviour? What needs user observation? |
| Technical design and delivery, Gate 6 | Boundaries and responsibilities; data model and contracts; security and privacy; concurrency and retries; failure recovery; dependencies; migrations; observability; capacity assumptions; delivery sequence | Where are guarantees enforced? Which system owns each fact? What happens during partial failure? Is complexity justified? What needs an experiment before building? |
| Implementation, Gate 7 | Every code-review area below, against the agreed specification and relevant surrounding system | Is each finding a demonstrated defect, missing requirement, material risk or optional improvement? What evidence or test would settle it? |
| Release readiness, Gate 8 | Actual test results and gaps; production configuration; migration and compatibility; monitoring and alerting; rollout and rollback; restoration; support readiness; known limitations | What remains unverified? Can failure be detected and contained? Who responds? Can rollback recover both behaviour and affected data? |
| Marketing and launch, Phase 9 | Audience and positioning; evidence behind claims; differentiation; pricing and packaging clarity; objections; calls to action; onboarding; consistency with shipped capabilities and support commitments | What might customers infer? Is the promise substantiated? Is the offer understandable? Which uncertainty needs a market test? |
| Post-launch learning, Gate 10 | Outcomes against success criteria; adoption and retention; support evidence; operating cost; segment differences; alternative explanations; next-investment options | What explains the result? What evidence separates competing explanations? Should the project improve, investigate, reposition, maintain or stop? |

## Code-review coverage

Assess all 15 areas. Grouped order follows behaviour, structure, security/data, integration, verification and project fit. Mark each individual area `reviewed`, `not applicable` or `not assessed`, with reasons for material omissions. A narrow diff review must disclose limits on wider-system conclusions.

| Group | Individual areas |
|---|---|
| Behaviour and resilience | Correctness and expected behaviour; Error handling and edge cases; Backwards compatibility |
| Structure and clarity | Readability and maintainability; Architecture and separation of concerns; Dead code, duplication and unnecessary complexity |
| Security and data | Security and permissions; Data validation and integrity |
| Efficiency and integration | Performance and scalability; API and database usage; Dependencies and configuration |
| Verification and operation | Tests and test coverage; Logging and observability |
| Project fit | Documentation and comments; Consistency with project standards |

For each material finding identify its location, consequence, supporting evidence and suggested remedy or next verification step. Distinguish confirmed defects, unverified risks and optional improvements. Do not assert a defect solely because an alternative style is preferred. Report all material findings; there is no three-question or other numeric findings cap. An area marked reviewed is not a guarantee of correctness.

## Independence and evidence package

- One author plus one reviewer using a different underlying model is sufficient. Two additional reviewers are not required. Another provider or model family can improve diversity but does not establish correctness. Another prompt, persona or session using the same model is not independent-model review.
- Record actual author/reviewer model and provider, version when known, review date, artifact revision, brief, evidence and tool/access limits. Never invent identity or claim independence when it cannot be established.
- Give the reviewer the goal, constraints, accepted requirements and decisions, relevant artifact and source evidence, applicable stage checklist, open assumptions and approved discussion boundary. Use compact context with access to relevant originals, not the entire conversation or a summary stripped of decisive evidence.
- For design, supply rendered screens and relevant interactions. For research, supply sources and conflicting evidence rather than only the author's conclusions. For code, supply the diff/base, relevant callers and contracts, and test evidence. Disclose unavailable artifacts.
- Let the reviewer form its initial assessment without other reviewers' conclusions or unnecessary persuasive framing. Do not hide constraints, accepted decisions or evidence needed for a fair assessment.
- Ask for missing evidence, consequential questions, ranked material risks and simpler alternatives where relevant. No material findings or questions is a valid result.

## Clarification and stopping

1. The reviewer returns the independent initial assessment, coverage and material questions, ordered by severity and decision impact. Each question identifies the ambiguity, why it matters and what would change with the answer. Group related questions without suppressing material ones.
2. The conductor obtains answers from the author or available evidence, using proportionate inspection, research or tests within existing permissions. Distinguish accepted decisions from assumptions. When the author is another worker, relay the questions through the conductor; do not start sibling debate.
3. In the one normally authorised clarification exchange, send those answers and any precise questions about the critique back to the reviewer. Ask it to confirm, narrow, revise or withdraw its findings and identify remaining consequential uncertainty. Resume the reviewer session when supported, or supply the prior findings and relevant answers; do not pretend a fresh session remembers them.
4. The conductor verifies and disposes of findings as adopted, rejected, deferred or unresolved, with reasons. Apply confirmed changes only within existing task authority, update the canonical artifact and run appropriate checks. A review recommendation does not authorise a scope change or an owner trade-off.
5. Suggest further exchanges, a fix-verification pass or another reviewer only when consequential unresolved issues or new evidence make the extra cost worthwhile; obtain owner approval before running them. Review changed areas rather than restart the whole assessment.
6. Stop discussion when no new decision-relevant evidence is being added. If evidence is missing, name the experiment, research or owner decision needed. A cost/time limit never makes a finding resolved. Preserve material disagreement rather than forcing consensus.

Owner priorities, acceptable trade-offs, promises and gate decisions belong to the owner. Customer demand needs customer evidence; model agreement cannot supply it. Combine unresolved owner questions into a concise decision pack with why each answer matters, evidence, options and a recommended answer where safe. Do not ask the owner what research, a test or an existing decision can establish.

## Review-package safety

Before sharing evidence with another model or provider:

- confirm that the provider and tool are permitted for the material
- exclude credentials, tokens and private keys without exception
- minimize or redact personal, customer and employee data
- omit or summarize exploitable security details and commercially sensitive material unless necessary and explicitly authorised for that provider
- supply only evidence needed for the agreed scope and record material redactions and access limits

Reviewers return findings and do not edit canonical artifacts by default. Existing permissions, external-action approval, testing, gate decisions and release controls continue to apply.

## Recording and handover

Use the existing canonical project plan or review record, not parallel copies. Record suggestion and rationale, scope, owner's approval/decline/deferral, brief and artifact revision, model identities, coverage limits, findings, clarification answers, dispositions and reasons, unresolved owner questions, and the next action. Record actual elapsed time and tokens when available; mark unavailable usage rather than estimate it as fact. Carry the owner's decision and remaining authorised discussion into conductor handovers.

At later natural checkpoints, use consequential findings adopted, questions resolved without owner interruption, actual cost and later missed defects to judge whether these reviews are useful. Comment count and model agreement are not measures of success.

## Unavailable models

If a different underlying model or permitted provider is unavailable, disclose this before running the review. A same-model critical pass is a labelled fallback, not independent review, and the owner decides whether to use it. Preserve the unmet review scope and residual uncertainty in the gate pack.
