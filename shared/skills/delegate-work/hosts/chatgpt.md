---
id: delegate-work-host-chatgpt
title: Dispatching packets on ChatGPT
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-22T10:47:07+10:00
updated: 2026-11-22T10:47:07+10:00
owner: brain-owner
---

# Dispatching packets on ChatGPT

Read `/CONTRACT.md` first and `/shared/skills/delegate-work/SKILL.md` for the protocol.

Written from the vendor's documentation on 22 November 2026; not run on the owner's machine. The
first session on this host records what actually happened and corrects this note.

## What ChatGPT is, for the brain

- **Chat** answers; **Work** is "an agent designed for longer, multi-step work and finished
  deliverables"; **Codex** is for software work (G2). The earlier agent mode "is no longer
  available" (G3); Work replaces it.
- A project keeps chats, files and instructions together, and a Work chat can start from a
  project (G2).
- The desktop app can open a local folder and use the files a task needs, with permission; Work
  on the web and on a phone cannot reach the computer (G2). Whether desktop Work can run shell
  commands is not stated.
- Every write to the brain needs Python and Git (the preflight, the tasks script, delegation). So:
  - **Codex, app or CLI, is the route for brain work on a ChatGPT plan.** It draws on the same
    allowance (G5) and is covered by `hosts/codex.md`.
  - ChatGPT on the web or a phone answers from files the owner uploads and cannot write the
    brain: it is an answer-only host.
  - ChatGPT desktop Work is usable for writes only once someone has confirmed that it runs
    `python` and `git` in the brain root.

## Pointer

A project's instructions apply only inside that project and override the global custom
instructions (search summary of the vendor's help centre, not verified). Put the pointer there:
"Work in `<brain_root>`; read `<brain_root>/CONTRACT.md` first." Nothing documents that Chat or
Work read an `AGENTS.md` by themselves.

## Subagents and the ladder

- Work runs subagents in the vendor's hosted environment; they are read-only in the sidebar, with
  no stop or steer controls, and custom agent files are not covered (G4). Most levels need an
  explicit request; the highest level may delegate by itself (G4), which breaks depth one: never
  run a conductor or a worker at that level.
- No model or effort per subagent is documented for Work (G4). Packets therefore run at
  `model: inherit`, and the ladder of SKILL.md (*Choosing a worker's model and effort*) chooses
  the session's model and level instead:

| Ladder rung | ChatGPT choice | Source |
|---|---|---|
| no judgement, rework only | Work with GPT-6 Luna where the picker offers it; in Chat, GPT-6 at Instant | G2, G1 |
| bounded judgement, or a person sees the result | Work with GPT-6.2 Sol, default reasoning; in Chat, GPT-6 at Medium | G2, G1 |
| open judgement, or data, money, security or production | Work with GPT-6.2 Astra at a high reasoning setting; in Chat, GPT-6 at High or Extra High, on the plans that offer it | G2, G1 |
| specialised, allowance healthy | GPT-6 Pro, on the plans that offer it | G1 |

Which models appear depends on the plan, the seat and the workspace settings (G2). Check the
picker; never assume, and record the model that actually ran.

- Where the session cannot run `delegation.py` (no shell), it runs packets in sequence in one
  session, each reading only its packet, and records `--parallel no` when a host that can run the
  script closes the run.

## Reading the allowance

Work and Codex share the plan's included allowance, then credits (G2, G5). Desktop app: Settings >
Usage (G5). Chat shows when an allowance resets, with no counter of what is left (G1). The model
can read none of these: the conductor asks the owner, or records that it could not read the
figure.

## Reading the context size

No context meter is documented for Chat or Work. Pass
`--context-unknown "ChatGPT reports no context size"` and drain (SKILL.md, *When to stop
dispatching*) at the first sign of the conversation being summarised or after the fourth run in
the thread, whichever comes first.

## Compaction hooks

None documented. The compaction marker and `checkpoint-done` cannot run; the conductor drains
early and tells the owner itself.

## Known limits

- No local transcripts: a transcript logger captures nothing from ChatGPT.
- A session that cannot run the brain's scripts cannot start a session copy (`SMART-RULE-0038`),
  so it does not write the brain at all.

## Sources

Read on 22 November 2026.

- G1: `https://help.openai.com/en/articles/20001354-gpt-6-and-other-models-in-chatgpt`.
- G2: `https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex`.
- G3: `https://help.openai.com/en/articles/11752874-chatgpt-agent`.
- G4: `https://learn.chatgpt.com/docs/agent-configuration/subagents.md`.
- G5: `https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan`.
