---
id: product-feedback-triage-classification
title: Feedback triage – classification rules
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
owner: brain-owner
created: 2026-10-17T10:55:31+10:00
updated: 2026-10-17T16:52:24+10:00
---

# Feedback triage – classification rules

Read `/CONTRACT.md` first. The triage run reads this file second, after `brief.md` in this
folder. It decides the `outcome`, `card`, `confidence` and `evidence` of `result.json`; the brief
says how to write the title, the reply and the sketch.

## How to apply the rules

Apply the five rules in the order below. The first rule that fits, with a source, decides the
outcome; stop there. A source is a line in the product node (`KNOWLEDGE.md`, `STATE.md`, a release
note) or a file in the packet (`packet.json`, a screenshot, `transcript.txt`, `thread.jsonl`).
A rule that fits only on your own guess does not fit.

## The rules, in order

1. **Intent.** Before anything else, write one sentence for yourself: what the person tried, what
   they saw, and what they want. Use their words and the page's on-screen labels. Every later rule
   is tested against this sentence. Do not put it in the result.
   - With marks (brief section 2), read them as the timeline of what they pointed at and join each
     transcript line with the mark and screenshot nearest in time: the words at 0:12 are about the
     element marked at 0:11. The thing they mean is that mark, named by its on-screen label; with
     several marks, prefer it over `element`. Without marks, read `element` as before.
2. **Answer.** They ask how to do something or why something happens, and the product already does
   it, or behaves exactly as its knowledge, its release notes or the page's own text says.
   - A report that something is "broken" when the product is doing what its knowledge or release
     notes say it should is an answer: explain what it does and how to get what they want.
   - If they clearly want that documented behaviour changed, it is an idea (rule 4), not an answer.
   - No card.
3. **Bug.** What they saw differs from what should happen, and you can show both sides:
   - (a) what should happen comes from a line in the product's knowledge, state or release notes,
     or from the page's own text (a label, a hint, a total that should add up); or
   - (b) it is plainly broken whatever the documentation says: an error message on the page, a
     matching console error in the packet, a blank or frozen screen, lost input, wrong arithmetic,
     a dead link, or cut-off text.
   - The evidence names the expected source and the packet file where the fault is seen.
   - Already listed in the node's `STATE.md` or in an unreleased release note: it is still a bug.
     The reply says it is already being worked on; the card title stays the same as that item's
     wording where it can.
4. **Idea.** The product works as intended, and they want it different or want something new:
   wording, size, order, layout, a field, a step, an export, a rule.
   - An idea is **visual** when it changes what this page shows, using elements the packet
     captured (a mark, the picked element, or what is visible in its HTML; with marks, only marked
     elements). Only a visual idea gets a sketch (a mockup with grade `sketch`, brief section 6);
     any other idea has `mockup: null`.
   - A new page, a new report, a change to how numbers are worked out or a change behind the
     scenes is an idea, but not a visual one.
5. **Question.** None of rules 2 to 4 reaches confidence 0.6, because one fact is missing: which
   element they mean, what they expected to see, or which record it happened on.
   - Ask exactly one question, with your suggested answer and numbered options, so they can reply
     with a number or "yes", in the form and limits of the brief's section 5. The reply holds at
     most one short sentence of context and never repeats the question.
   - Never ask for something the packet already holds (the page, the element, a mark the words
     refer to, the screenshot, the note), for a password or other credential, or for personal data.

## Tie-breaks

In the order they are applied.

1. **One outcome per packet, nothing dropped.** When a packet holds more than one thing, bug
   beats idea and idea beats answer for the outcome and the card's title. The reply still takes
   every thing in turn, numbered in the order the person said them (a question answered, a bug
   or idea acknowledged), and the one card holds all of it; the conductor splits it when the
   builds differ. Never ask the person to send a thing again (the owner's decision of 17 October
   2026).
2. **Two rounds at most.** After two question rounds in the same thread, decide on the best
   reading you have, at lower confidence, and say in one short sentence what you understood.
3. **No product node.** When the prompt names no product node (`none`), a bug is possible only
   under rule 3(b). Answers rest on the page's own text alone; anything else is an idea or a
   question. The reply says so once, in at most four words: "No product notes checked."

## Confidence

- **0.9 to 1.0**: what should happen and what happened are both evidenced by a source.
- **0.6 to 0.9**: one of the two is inferred (for example the expected behaviour is plain from
  the page but no note states it).
- **Below 0.6**: do not decide; ask (rule 5). A `question` result carries the confidence of the
  best reading you had.

## The card

Set for `bug` and `idea`, `null` for `answer` and `question`.

- `title`: one line in the person's words, at most 100 characters, naming things by their
  on-screen labels.
  - A bug reads "X does Y instead of Z", for example "Total bed area stays at 0 m² instead of
    adding up the beds".
  - An idea reads "Let people …", for example "Let people find Save more easily: make it bigger
    and call it Save plan".
  - In a thread that continues the same issue, keep the title of the earlier result.
- `area`: the packet's `page.app`, or `unknown` when it is null.

## Evidence

`evidence` lists at least one source the outcome rests on, most decisive first:

- a repository-root path in the product repository, written `<repository>:<path>`, for example
  `<repository>:brain/KNOWLEDGE.md` or `<repository>:release-notes/unreleased/<slug>.md`;
- or a packet file name: `packet.json`, `shot-001.png`, `transcript.txt`, `thread.jsonl`.

## Worked cases

Fictional, on a garden planner; the matching packets and results are in `schemas/examples/` in
the extension repository.

1. "How do I copy last week's plan?", pointing at **Week options**; the node's knowledge says the
   week menu has **Copy from last week**. Rule 2: answer, confidence 0.95, no card.
2. "The total stays at 0 after adding beds", a screenshot showing three beds and **Total bed
   area 0 m²**, and a console error while the total is worked out. Rule 3(a) from the knowledge
   line that the total adds up the beds, and 3(b) from the console error: bug, confidence 0.9.
3. "Make Save bigger and say Save plan", pointing at the **Save** button, which works. Rule 4:
   idea, visual, because it changes the picked button; a sketch with two operations.
4. "This is wrong", pointing at nothing, on a page with three totals. No rule reaches 0.6: the
   reply holds at most one short sentence, and `question` alone asks "Which is it: 1. Total bed
   area, 2. Seeds needed, 3. Water per week? I think 1."
5. "The total stays at 0, and could the Save button be green?" Bug beats idea: triage the total;
   the reply asks for the colour as a separate feedback.
