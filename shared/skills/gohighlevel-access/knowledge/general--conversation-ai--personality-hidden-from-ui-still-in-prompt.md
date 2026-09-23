---
id: ghl-general-conversation-ai-personality-hidden-from-ui-still-in-prompt
title: A conversation AI agent's personality is no longer shown in the UI but stays in the record and the prompt
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: GET /ai-employees/employees/{id}
status: pending
superseded_by: null
refuted_by: null
discovered: 2026-09-15
verified: null
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--conversation-ai--personality-hidden-from-ui-still-in-prompt.md
created: 2026-09-15T11:30:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# A conversation AI agent's personality is no longer shown in the UI but stays in the record and the prompt

## Behaviour

The agent record returned by the internal `GET /ai-employees/employees/{id}` carries
`personality`, `instructions`, `goal`, `steps` and `fullPrompt`. `fullPrompt` is the
prompt as HighLevel assembles it, and it opens with the `personality` text under a
`## Personality` heading. The HighLevel UI for a conversation AI agent no longer has a
place where `personality` can be seen or edited; the field is set only on agents
configured before that page changed.

## Why it's non-obvious

An operator reviewing the agent in HighLevel sees instructions and goal and believes
that is the whole prompt. Text they cannot see, and could not change without
recreating the agent, is still sent to the model on every conversation. In the
reference account three of six live agents carry it, one of them naming a custom value
that is itself marked for deletion.

## Evidence

Owner observation of the HighLevel UI against the 14 September 2026 sweep of Example
Co, 15 September. `personality` populated on `Appointment Assistant`, `Chat Current
Project Assistant` and `Triage Email Assistant`; `fullPrompt` on each begins with that
text. **Pending**: the claim that no UI surface shows the field rests on the owner's
inspection, not on a recorded route or an API answer, and HighLevel could restore or
move the page.

The two voice agents in the same sweep (`GET /voice-ai/agents/{id}`) carry
`agentPrompt`, `agentWelcomeMessage` and `agentSettings`, and none of `personality`,
`instructions`, `steps` or `fullPrompt`. Whether any voice-agent field is orphaned the
same way is not established; on this account there is no such field to orphan.

## Applies to

Conversation AI agents (`ai-employees`) read through the internal per-agent endpoint.
ExampleDocs raises `ai_agent.hidden_configuration` on a live agent whose `personality` is
populated and shows every populated field in full, so the owner can decide whether to
recreate the agent or keep it.
