---
id: product-development-multi-model-review
title: Multi-model Product Review Protocol
type: process_reference
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-03T14:05:35+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Multi-model Product Review Protocol

Independent AI review broadens the search for missed assumptions and failure modes. It is advisory evidence, not a gate vote and not a substitute for representative users, specialists or the owner's decision.

## Required checkpoints

At `standard` depth, use independent-model review when it is materially useful at:

1. after opportunity and build-versus-buy analysis: contrarian problem, substitute, distribution and economics review
2. before Gate 6: product, UX, architecture, privacy, security and failure-mode review
3. before Gate 8: implementation, test coverage, migration, operations and rollback review

At `high-assurance` depth, perform all three and add relevant specialist lenses. At `light` depth, use one independent review at the highest-uncertainty gate when its likely value justifies the cost; otherwise record why it was omitted.

For a feature iteration, review only the affected checkpoint unless its consequences reopen other stages.

## Independence

- Use at least two distinct underlying models for required standard and high-assurance reviews when available and permitted, preferably from different model families or providers. Record the reason when fewer are used.
- Give reviewers the same evidence package and question, but do not reveal other reviewers' conclusions during the initial pass.
- Ask each reviewer to identify missing evidence, challenge the recommendation, rank material risks and suggest cheaper or simpler alternatives.
- Record model/provider and version when known, review date, prompt or brief, evidence supplied and tool/data-access limits. Never invent model identity.
- A second prompt, persona or agent running the same underlying model may supply another lens, but label it accurately; it does not satisfy an independent-model requirement.

## Review-package safety

Before sharing evidence with another model or provider:

- confirm that the provider and tool are permitted for the material
- exclude credentials, tokens and private keys without exception
- minimize or redact personal, customer and employee data
- omit or summarize exploitable security details and commercially sensitive material unless they are necessary and explicitly authorised for that provider
- give each reviewer only the evidence required for its lens
- record material redactions or access limitations so the review is not overstated

## Synthesis

The primary agent must:

- verify factual claims against authoritative evidence where proportionate
- separate shared findings from model-specific suggestions
- highlight substantive disagreements rather than averaging them away
- assess whether a critique changes scope, depth, risk or recommendation
- include unresolved disagreements in the gate decision pack
- record which suggestions were adopted, deferred or rejected and why

Do not select a recommendation by majority vote. Models can share the same blind spot or repeat weak source material.

## Clarifying questions for the owner

After research and initial reviews, combine related value judgements and material trade-offs into one structured questionnaire when bulk questioning will produce a better decision. For each question include:

- why the answer matters
- relevant evidence or disagreement
- available options
- the agent's proposed default, if one is safe

Do not burden the owner with questions that research, project evidence or a reversible default can answer.

## Unavailable models

If independent models or providers are unavailable, state this in the gate pack. Use separate critical lenses as a fallback, but do not claim that a multi-model review occurred. Ask whether to proceed when the missing independence materially affects a high-assurance decision.
