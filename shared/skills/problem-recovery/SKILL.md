---
id: skill-problem-recovery
title: Problem Recovery
type: skill
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-09-17T17:14:19+10:00
updated: 2026-09-23T12:00:00+10:00
status: active
owner: brain-owner
scope: shared
---

# Problem Recovery

## Purpose

Implement SMART-RULE-0028: find relevant knowledge, recover proportionately and capture evidence without making every failure an owner interruption.

## Invocation and required inputs

Use on unexpected outcomes, repeated failure, conflicting evidence or blocked progress. Inputs: intended outcome, observed result, task permissions, relevant system/subject, approaches already tried and available effort.

## Data sources

Relevant API `knowledge/` and its `_CONVENTION.md`, the learning index, owning node KNOWLEDGE and focused evidence/history. Follow SMART-RULE-0005 internal-first lookup and SMART-RULE-0013 for API quirks. Scope/version matter: a matching keyword is not proof applicability.

## Allowed operations and permissions

Targeted read-only lookup, public research, bounded recovery within existing task authority, and separate learning artifacts through learning-maintenance. This skill grants no credentials, external-write permission, governance changes or product integration authority.

## Procedure

1. State the failure and what success would look like. Search the relevant canonical subject first; for an API start with its quirks. Read matching refuted/deprecated entries as warnings and follow current replacements and exceptions. Expand to the index, owning KNOWLEDGE and relevant LOG only as needed. No exhaustive search to prove absence.
2. Check applicability and evidence. Contradiction is an investigation, not a vote. Distinguish missing information from a disproven hypothesis.
3. Define a reversible attempt, success criterion and stop condition. Bound effort for the whole problem; a practical default is at most three materially different attempts, with a concrete time/effort ceiling chosen for the task. Stop sooner when further attempts have no evidence basis.
4. After meaningful investigation or implementation, research public authoritative experience proportionately, including successful approaches worth learning from. Do not send private context to search engines. Record source provenance separately from local results.
5. A failed attempt can lead to research, a materially different hypothesis, or a pending investigation. At the effort limit, preserve what was tried and the next useful action in an artifact/canonical task, and continue independent work. Do not silently abandon the requested outcome: explain a material blocker in the normal task report.
6. Contact the owner only when authority, consequential judgement, goal clarification or material impact on current work meets SMART-RULE-0028. Failure/disagreement alone does not qualify.

## Scripts or commands

None required; use the subject's existing tools within their permissions.

## Outputs

Recovered outcome or a precise unresolved finding: searched sources, attempts, negative evidence, assumptions and next useful action. Learning artifacts route through `/shared/skills/learning-maintenance/` and its single writer.

## Failure behaviour

An empty search is not proof no answer exists. Missing tools or denied permissions do not justify bypassing safeguards. Stop repeated identical attempts; preserve recoverable work and disclose material limitations without claiming success.

## Logging and state, knowledge and task updates

Capture meaningful learning at the natural checkpoint, using the subject's canonical home and avoiding duplicates. Provisional claims stay out of established KNOWLEDGE. Non-writers leave separate pending artifacts; the designated writer integrates and logs. Create or link a canonical task for unresolved work, keeping task state consistent. No routine-work changelog disguised as learning.
