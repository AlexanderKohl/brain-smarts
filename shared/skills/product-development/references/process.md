---
id: product-development-adapted-process
title: Adapted Product Development Process
type: process_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-03T14:05:35+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Adapted Product Development Process

This is the operational adaptation of a source product-development process; the owner's source record is kept in their memory. It adds proportional depth, internal/commercial dual consideration, existing-product and feature re-entry, delivery planning, earlier lifecycle constraints and independent AI review.

## Proportional depth

Select depth from the combined investment and consequence, not cost alone.

### Light

Use for low-cost, reversible work with limited users, familiar technology, small data exposure and low operational impact. Combine adjacent gates and use concise evidence. A small internal improvement may use one compact decision note in an existing canonical plan, feature specification or task and move from problem statement to tested release in one short cycle. Record only the affected gates; do not reconstruct the whole product lifecycle.

### Standard

The default for material features and ordinary software products. Produce enough evidence to challenge assumptions, design safely, test expected behaviour and make each investment decision deliberately.

### High-assurance

Use when failure could cause significant financial, legal, safety, privacy, security, reputational or operational harm; investment is substantial; decisions are difficult to reverse; architecture is novel; or many users and systems are affected. Require deeper evidence, explicit traceability, stronger testing and independent reviews at all specified checkpoints.

Depth may vary by workstream. For example, a commercially modest internal tool can still require high-assurance privacy and security work.

## Entry and iteration

### New product

Begin at Phase 0 and move through applicable gates.

### Existing product baseline

Build the minimum viable baseline needed for the decision. Map the affected phases and gates from existing evidence and reality, using `supported`, `partially supported`, `unsupported`, `superseded`, `not applicable` or `not assessed`. Leave unaffected areas `not assessed` with a reason unless the proposed investment depends on them. Start new work at the earliest gate whose unresolved assumptions materially affect the proposed investment.

### Feature or material change

Define the user outcome and affected assumptions, then reopen the relevant gates. Check effects on architecture, data, security, operations, documentation, pricing and product positioning even when those gates do not need full repetition.

### Urgent repair

When authorised, prioritise containment and restoration. Afterwards capture root cause, affected assumptions, missing tests or controls, and any gate that needs reopening.

### Lifecycle review

Start from production evidence and Gate 10. Reopen earlier phases when the evidence supports expansion, simplification, repositioning, component separation or retirement.

## Phase 0: Triage, strategic fit and investment

Establish:

- entry type and current lifecycle position
- intended outcome and strategic fit
- opportunity cost and relevant portfolio alternatives
- available capabilities, capacity and budget
- reversibility, uncertainty and consequence of failure
- depth level and why it is proportionate
- primary internal and commercial hypotheses

### Gate 0: How much investigation and investment is justified now?

Authorise only the next useful increment of discovery or delivery. Record its boundary.

## Phase 1: Opportunity discovery

Define the user, problem, job, current workaround, frequency, pain, expense and successful outcome. Distinguish observation from assumption.

For the internal route, examine time, cost, errors, quality, risk, employee experience, dependency reduction and strategic capability. For the commercial route, examine segments, workflows, alternatives, purchase criteria, objections, willingness to pay, distribution and reachable market.

Research should reshape the opportunity rather than validate a predetermined solution.

### Gate 1: Is the problem worth solving?

Require evidence of a meaningful problem, affected users, inadequate alternatives, likely adoption and plausible strategic or economic benefit.

## Phase 2: Existing solutions, route and economics

Research direct competitors, substitutes, open source, APIs, SaaS, marketplaces, libraries, frameworks, infrastructure and existing internal capabilities.

Compare build, buy, configure, integrate, extend and stop. Include total lifecycle cost, vendor reliability, security, contractual limits, lock-in, data portability, maintenance burden and exit options.

Test the internal benefit model and the commercial revenue model. For commercial possibilities, consider payer, willingness to pay, packaging, margins, support, commissions, acquisition cost, lifetime value and an economical path to customers. Do not confuse willingness to use with willingness to pay.

### Gate 2: Build, buy, integrate, investigate further or stop?

Proceed with custom development only when its additional value justifies its lifecycle cost and risk.

## Phase 3: Product and service boundaries

Decompose independent capabilities. Decide whether each is a product feature, shared platform capability, independently useful service, third-party service, external integration, future product or unnecessary.

Logical boundaries do not require separately deployed services. Separation is justified by genuine differences in lifecycle, ownership, reuse, scaling, reliability or security.

### Gate 3: Is this the simplest architecture boundary that adequately meets the validated requirements and risks?

Reject both avoidable coupling and separation performed only for architectural neatness.

## Phase 4: Product definition

Define users, use cases, core scope, non-goals, MVP or increment boundary, constraints, dependencies and measurable success. Capture business rules, permissions, edge cases, integrations, data ownership, failure behaviour and commercial assumptions.

Design primary, alternate, empty, failure, cancellation, retry, permission, concurrent-change and unusual-input journeys. Identify legal, regulatory and accessibility obligations early enough to change scope and architecture.

### Gate 4: Is the next releasable increment clear and testable?

Development does not start while behaviour that materially affects investment remains ambiguous.

## Phase 5: Experience, system and delivery design

Create sufficient prototype fidelity to test the important workflow. Observe representative users rather than relying only on stated preferences.

Define system boundaries, components, data flows, APIs, events, entities, relationships, constraints, migrations, retention and ownership. Address authentication, authorisation, tenant isolation, secrets, abuse, supply-chain risk, privacy, failure modes, configuration, environments, observability, audit needs and product analytics.

Do not log sensitive previous and new values by default; use redaction, hashing or field-level change records where appropriate.

Define delivery milestones, dependencies, sequencing, responsibility, capacity, budget, technical-debt decisions and release strategy. Document material architectural and product decisions.

For AI-enabled behaviour also define evaluation data, acceptable failure, human oversight, prompt-injection and data-leakage controls, provenance, model/vendor change handling, latency/cost limits and ongoing quality/drift monitoring. Apply the additional high-risk requirements below when the capability can materially affect people, money, access, sensitive data, legal obligations or production systems.

#### Additional requirements for high-risk AI

Before Gate 6, define measurable evaluation thresholds, representative and adversarial evaluation sets, prohibited autonomous actions, human approval and override points, auditability, provider/data boundaries and a safe degraded mode or kill switch.

Before Gate 7, test prompt injection, data exfiltration, unsafe tool use, permission bypass, hallucination-sensitive decisions, model unavailability and cost/latency limits. Record residual failures against the release thresholds.

Before Gate 8, establish production quality sampling, regression detection after model or prompt changes, incident response, rollback or disablement, accountable human ownership and a schedule or trigger for renewed evaluation.

### Gate 5: Does the proposed experience solve the problem for representative users?

Return to product definition when the workflow is not understood or does not deliver the intended outcome.

### Gate 6: Is the design and delivery plan sufficiently complete and proportionate to build safely?

Assess architecture, security, privacy, accessibility, failure modes, operations, delivery dependencies and unresolved decisions.

## Phase 6: Acceptance-led implementation

Define acceptance criteria and a proportionate test strategy across unit, integration, contract, database, security, regression, end-to-end and performance concerns. Write tests before implementation where that improves design or risk control; avoid test-first ceremony where it adds little value.

Prepare fictional fixtures, sandboxes, mocks and edge cases. Implement the minimum coherent change and continuously run relevant tests, static analysis, type checks, security checks and build verification.

### Gate 7: Does the implementation meet the agreed specification and quality threshold?

Code completion alone is insufficient. Required behaviour, tests, security, observability and documentation must be satisfied.

## Phase 7: Release validation

Deploy the intended production artefact to a production-like isolated environment. Run relevant integration, end-to-end, security, smoke and migration tests.

Define and conduct UAT with representative users. Automate stable critical journeys identified through acceptance work. Validate performance, security, accessibility and browser/device behaviour.

Confirm monitoring, alerts, backups, restoration, feature flags, rollout controls, rollback, support, migrations and production access.

### Gate 8: Is the product ready for controlled production exposure?

State release criteria, rollback triggers and who responds if they are breached.

## Phase 8: Controlled release

Release to internal users, design partners, selected customers or a small traffic segment. Observe errors, behaviour, drop-off, performance, support demand and unexpected use. Use feature flags, canarying or other gradual controls where proportionate.

For internal products, include workflow change, training, adoption ownership and retirement of the previous process.

### Gate 9: Expand, correct, reposition, reprice or withdraw?

Base the decision on actual use and operational evidence.

## Phase 9: Commercial or organisational launch

For commercial products, finalise evidence-based pricing and packaging, terms, privacy, billing, cancellation, refunds, support commitments, positioning, sales materials, demonstrations and onboarding.

For internal products, finalise ownership, training, support, operating procedures, access, adoption communications and process transition.

Create a canonical knowledge base from the actual specification, known issues and support procedures. Derive AI support prompts from that source rather than allowing a contradictory support description to evolve.

## Phase 10: Production operation and learning

Monitor availability, errors, performance, integrations, security, usage, cost, value and–where applicable–revenue and customer behaviour. Operate incident ownership, communication, diagnosis and recovery.

Continuously combine analytics, support cases, interviews, requests, churn and sales or internal-adoption feedback. Compare actual outcomes with the original success criteria. Maintain dependencies and planned technical debt, and provide data export, migration and deprecation paths when retiring capabilities.

### Gate 10: Continue investing?

Decide whether to continue, increase investment, maintain, simplify, split, integrate, sell, deprecate or shut down. Sunk cost is not evidence for continuation.

## Common gate record

Each gate records:

- decision owner
- date and lifecycle context
- depth level
- question and recommendation
- evidence and freshness
- internal and commercial route disposition
- assumptions, confidence and unresolved risks
- independent reviews required and completed
- decision: `proceed`, `revise`, `pause` or `stop`
- rationale and conditions
- exact next investment authorised
- review trigger or expiry of the decision
