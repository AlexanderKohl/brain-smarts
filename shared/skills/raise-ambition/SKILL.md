---
name: raise-ambition
description: At the intake of any request, name the outcome behind it and check whether a bigger version would serve the user better – one that reaches higher (an outcome kept true, not a task done), deeper (an expert's methods and a harder target) or wider (other fields and roles). When it would, offer that version as the first, recommended option of the clarifying question, beside the request as asked. Never widen the work without the user's yes.
metadata:
  id: skill-raise-ambition
  title: Raise Ambition
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: core
  owner: brain-owner
  version: 0.1.0
  canonical_source: /shared/skills/raise-ambition
  created: 2026-10-23T07:28:25+10:00
  updated: 2026-10-23T08:06:02+10:00
---

# Raise Ambition

Read `/CONTRACT.md` first. `SMART-RULE-0044` in `/RULES.md` requires this skill at the intake of every request.

## Purpose

People ask AI models for far less than the models can do. They ask for the task in front of them
– fill this template, fix this crash, write this post – when the thing they want is the outcome
behind it. This skill makes the agent notice the bigger version of a request and offer it, so the
user chooses the size of the work deliberately instead of by habit. The user is the person whose
request it is: the owner, or a collaborator working in a shared project.

It is a way of working, not a script. It runs at intake, before any plan, and costs a few lines of
the reply.

## The four kinds of ambition

| Kind | The question it asks | A small request and its bigger version |
|---|---|---|
| **Altitude** – aim at the outcome, not the task | What should be true after this? What goal sits behind that goal? Could the work be kept true over time instead of done once? | "Fix this crash" → "keep the app crash-free, with a check that catches the next one" |
| **Depth** – work as the best expert would | What raw material, methods and checks would a top specialist use? What target would they set? | "Make the page load in 5 seconds" → "200 milliseconds, measured by an outside tool" |
| **Range** – borrow from other fields | Recast the work as verbs: which other fields do those verbs well? Which roles – analyst, editor, adversarial reviewer – would a team bring? | "Write the plan" → "a panel of specialists drafts it, a red team attacks it, the plan that survives is the one we use" |
| **Speed** – do it faster | Can parallel workers, automation or a template remove the waiting? | Usually understood already; mention it only when it is the real lever |

Behind all four sits **self-efficacy**: specific, hard goals framed as achievable outperform "do
your best". The agent states the bigger goal as something the user and the agents can actually
reach, with the first step named.

## Procedure

1. **Name the outcome.** In one line, say what the request is for: the result the user wants
   after it is done, and the goal behind that.
2. **Climb one rung on each kind.** For altitude, depth and range, ask whether a bigger version
   exists that serves that outcome better. Most requests have one worth offering; a genuinely
   self-contained request (a typo, a lookup, an answer to a factual question) has none, and the
   agent says nothing.
3. **Run the expert meta-prompt on anything substantial.** Before planning, ask: what would the
   best expert in this field do here, what would they start from, which methods would they use,
   and how would they check the result? Rewrite the plan to match.
4. **Offer it in the clarifying question.** When the agent asks the user anything about the
   request, the bigger version is option 1, marked recommended, with what it takes (time,
   allowance, the user's inputs) in one line; the request as asked is option 2. When no question is
   otherwise needed, the agent does what was asked and adds one line: "Bigger version: …".
5. **Make it concrete and hard.** A bigger version names a measurable target and a first step,
   never "think bigger". "Raise booked jobs from reactivation from 3 % to 10 % of the list, starting
   with a test on 200 dormant contacts" is an offer; "be more ambitious with reactivation" is not.
6. **Build in an outside judge.** A bigger version says how its result will be checked by
   something other than the agent that made it: real data held back, an outside tool, an
   adversarial reviewer, the user's own figures.
7. **Ask for decisions, not decks.** Where the request is a report or a review, the bigger version
   usually ends in the few decisions that matter most, with the case for and against each.

## Guardrails

- **The user decides the size.** The agent never widens the work without the user's yes. The
  request as asked is always a valid choice and is done well when chosen.
- **Once per request.** A bigger version the user declined is not offered again for the same
  request unless new evidence arrives.
- **Short.** The suggestion takes a few lines, not a lecture. No suggestion is better than a vague
  one.
- **Costs stated.** A bigger version that needs much more allowance, money or the user's time says so,
  with an estimate or an honest "unknown".
- **Every other rule still applies.** Safety, side effects, external targets, credentials and
  governance acceptance are unchanged by a bigger ambition.

## Allowed operations

- Reading the request, the active node's state and knowledge, and the user's goals where recorded.
- Proposing a bigger version in a reply or a clarifying question.

## Required inputs

- The user's request.
- Where available, the active node's `STATE.md` and `KNOWLEDGE.md`, so the outcome behind the
  request is named from the user's own goals rather than guessed.

## Data sources

The request and the brain's own records. No external system.

## Scripts or commands

None. The skill is applied by the agent's own reasoning at intake.

## Outputs

- One line naming the outcome behind the request (when useful to the user).
- A bigger version as option 1 of a clarifying question, or a one-line "Bigger version: …" note.

## Permissions

No writes and no external access of its own.

## Failure behaviour

When the agent cannot name the outcome behind a request with reasonable confidence, it asks the
user as part of its clarifying question, with a suggested answer, instead of guessing.

## Logging behaviour

None for ordinary use. A bigger version the user accepts is recorded where the work it starts is
recorded.

## State, knowledge and task update behaviour

None of its own. When the user accepts a bigger version that outlives the session, the agent
creates or updates the task or node for it under CONTRACT §9.

## Provenance

The four kinds of ambition, the expert meta-prompt and the self-efficacy point paraphrase Felix
Rieseberg, "How to be more ambitious: a tutorial for humans with models",
https://felixrieseberg.com/how-to-be-more-ambitious-a-tutorial-for-humans-with-models/, read on
23 October 2026. The procedure and guardrails are the brain's own.
