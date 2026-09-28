---
id: product-development-project-record
title: Product Development Project Record Specification
type: process_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-03T14:05:35+10:00
updated: 2026-09-28T13:44:41+10:00
---

# Product Development Project Record Specification

Use an existing canonical product plan if it can represent this state without duplication. A low-risk light change may instead use a compact entry in an existing canonical plan, feature specification or task containing the outcome, depth reason, affected gates, evidence, decision and next action. Otherwise create `/memory/projects/<project>/PRODUCT-DEVELOPMENT.md` with standard Markdown metadata and these sections.

## Required metadata

Use the contract's standard fields plus:

```yaml
type: product_development_record
status: active
owner: brain-owner
development_mode: new_product | existing_product_baseline | feature_or_change | urgent_repair | lifecycle_review
process_depth: light | standard | high-assurance
current_phase: 0
current_gate: 0
source_refs: []
```

`current_phase` and `current_gate` may be `null` when a product is paused, stopped or only being baselined.

## Required sections

### Product and outcome

Identify the product, users, intended outcome and strategic relationship to its project.

### Current lifecycle position

For each phase and gate needed for the current investment decision, record one of `not assessed`, `supported`, `partially supported`, `unsupported`, `superseded` or `not applicable`, with links to existing evidence. For an existing product, leave unaffected phases `not assessed` with a reason rather than performing a forensic reconstruction that cannot change the decision.

### Current increment

Describe the product, feature, change or review presently moving through the process and the assumptions it affects.

### Proportional depth

Record the selected level and the investment, uncertainty, reversibility, user, security, privacy and operational reasons. Note any workstream whose assurance level differs.

### Internal and commercial routes

Give each route one disposition: `primary`, `secondary`, `future option` or `not currently justified`. Record the evidence and when the classification should be revisited.

### Evidence register

For each material item record:

- claim or decision it supports
- source or artefact
- collection date
- scope and limitations
- confidence
- freshness or expiry concern

Link canonical Brain sources rather than copying them.

### Assumptions and open questions

Distinguish verified facts, working assumptions, contradictions and questions requiring owner judgement. Batch related owner questions at the next useful decision point unless delay creates material risk.

### Gate decisions

Use the common gate record from the adapted process. Never overwrite history; add a new decision entry when a gate is reopened.

### Independent reviews

Record each worthwhile review suggestion, its rationale, scope, proposed reviewer, time/token estimate or uncertainty, and the owner's decision (`approved`, `declined` or `deferred`); an unanswered suggestion is pending, not approved. Retain decisions across handovers and re-suggest only when material new evidence changes the case.

For an approved review, link the brief, artifact revision and evidence, actual author/reviewer model identities, coverage and access limits, findings, clarification answers and final dispositions (`adopted`, `rejected`, `deferred` or `unresolved`) with reasons. Include remaining owner questions, authorised discussion boundary, and actual time/tokens when available; never invent usage. Update the canonical specification or artifact to reflect accepted changes. Use a compact entry in the existing plan for small work rather than duplicate records.

### Delivery and validation

Track only the current milestone, key dependencies, acceptance criteria and validation results here. Detailed engineering work may remain in project-native systems, with links.

### Next action

Name the next evidence-gathering action or gate decision, its owner and any task reference.

## Update boundaries

- Current lifecycle truth belongs in this record and relevant `STATE.md` summaries.
- Durable product facts belong in project `KNOWLEDGE.md`.
- Significant decisions belong in `LOG.md` as well as the gate history.
- Outstanding actions belong in canonical `/memory/tasks/`.
- Do not duplicate code-repository issue tracking; link it where appropriate.
