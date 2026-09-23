---
name: ui-implementation
description: Build an interface that never destroys the work or the choices of the person using it. Use whenever implementing or changing a live screen - a page that repaints on new data, a dialog that holds typed work, a list a person reads down, a control that changes state, or an overlay drawn on someone else's page.
metadata:
  id: skill-ui-implementation
  title: UI Implementation
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: none
  canonical_source: /shared/skills/ui-implementation
  skill_refs:
    - /shared/skills/ui-mockup
  created: 2026-09-16T13:35:00+10:00
  updated: 2026-09-23T18:00:00+10:00
---

# UI Implementation

## Purpose

Keep a live interface from taking a person's work or their choices away from them, and keep the
rules that prevent it in places where the next author cannot fail to inherit them.

`ui-mockup` settles what a screen should look like before it is built. This skill governs what the
screen must never do once it is real and data is arriving underneath it.

Every rule below carries its reason, because a rule whose reason is missing gets optimised away by
the next person who reads it. Owner-specific accounts of what taught a rule belong in
`/memory/skills/ui-implementation/NOTES.md`, not here.

## The rules

### 1. A renderer removes only what it made

Name what you remove, never what you spare. An exception list - *remove everything except that
one* - is a list the next dialog cannot know it needs to be on, so every surface built afterwards
inherits the exact bug the exception was added to fix.

> **Rationale.** A renderer that clears every backdrop on the page destroys whatever a person has
> typed into a dialog. Sparing that dialog by name fixes it once; the next dialog, built after the
> exception list, is closed mid-sentence the same way, because nobody thought to add it.

Mark what you create, remove only what carries your mark, and leave the rest alone.

### 2. A refresh updates what a person sees, never what they chose

New data may change the content. It may not reset a filter, a scroll position, a focused item, an
open panel, a search box, a sort or an expanded row. Carry every choice through the repaint, check
each one against the new data, and fall back only where what was chosen no longer exists.

Two things are never dropped even when they no longer resolve, because losing them loses work
rather than a choice: half-typed text, and a half-made decision the person has not committed.

### 3. Work in progress outranks freshness

While a surface holds unsaved work, a repaint waits. When the last such surface closes, whatever
arrived in the meantime runs at once - deferred, never dropped, never silently coalesced into
nothing.

Hold with a counter rather than a flag, so two open surfaces cannot free each other.

### 4. Put the rule where it cannot be forgotten

Prefer a mechanism that follows the fact over a convention every future author must remember.

> *Each dialog holds the repaint* is three lines that must be written into every dialog anyone ever
> builds, and the bug returns the first time someone forgets. *While any dialog is open the
> repaint waits* is written once and covers dialogs nobody has designed yet.

Where a rule genuinely cannot be mechanised, make a test fail when it is forgotten, and say in the
test name what was forgotten.

### 5. Unsaved text survives the tab

Keep a draft in memory and in the browser's own storage, keyed by the context it belongs to, and
clear it when the work is saved or when it says nothing. Wrap every read and write, because storage
throws in a private window and returns nothing in a cleared one; the surface must render correctly
when it comes back empty.

### 6. A label names the relationship it actually has

A control labelled for the wrong relationship is indistinguishable, to a reader, from a control
that is not there.

> **Rationale.** *Fix in <workflow>* is right when the link goes somewhere else. Pointed at the very
> workflow the finding names, it reads as fixing a thing inside itself, and a reader asks for a link
> that is already on the screen. *Open*, the word used everywhere else for going into a place, is
> the right label there.

One word for one thing, across the interface, the code, the stored data and the conversation.

### 7. Every list has a deliberate order, and it serves the batch being worked

Root `SMART-RULE-0027` requires the order to be chosen. This skill adds what to choose it for: the
way the reader batches the work.

Two axes usually compete. Grouping by **question** makes one judgement serve a run of rows.
Grouping by **place** makes one context switch serve a run of rows. Neither is better in general,
so where both are real, the reader says which they are doing, and the default is the one they do
most. Sort stably to the last key, so two rows that look alike do not swap places between repaints.

### 8. Controls are grouped by what they do, and sit in the same place on every row

Everything that only takes you somewhere on one side; everything that changes state on the other.
A person learns one place to look. Never draw a second way into somewhere a row already reaches.

### 9. Nothing drawn on someone else's page covers it

An overlay on a host application sits in free space near the thing it belongs to, never over a
control, a label or a card. Say in code what happens when there is no free space - shrink, move
out, or do not draw - because guessing is what puts a badge over a Save button.

Never intercept, disable or delay the host's own controls. Restore exactly what was changed, and
leave the host's own signals alone: check what the page already says in the place you are about to
write, or your warning will be read as theirs.

### 10. Measure the layout; do not judge it by eye

Assert the layout in a browser harness at several viewports, including a short window: no
horizontal scroll, room left for the content under any pinned block, and the counts that form a
contract. When a change alters one of those contracts deliberately, change the assertion in the
same commit and say why in the message.

### 11. Count the meanings each visual device carries, in a render

One weight, one colour, one shape: one meaning.

> **Rationale.** A navigation rail can end up with four meanings in one number style, an accent
> colour with three, and a backlog colour reused to mean *you are here*. Collisions like these are
> found only by rendering the screen and looking at it - never by reading the code, because each
> device is locally reasonable.

So it is a check rather than a rule about a particular colour. On a rendered screen, list every
device that carries meaning - fill, weight, border, badge, dash, icon - and for each, name every
meaning it carries. Two meanings on one device is a defect whoever drew it will not see, because
they added the second meaning in a different week from the first.

The same applies to the reverse: one meaning drawn two ways is a reader learning two things for one
fact.

## Allowed operations

- Read the product's own source, stylesheets and specifications.
- Implement interface changes in the product repository.
- Run and extend the product's own browser harness; record its measurements.
- Update the specification section that governs the screen, in the same change.

## Required inputs

- The screen or surface being changed, and the specification section that governs it.
- What arrives underneath it while a person is using it: which events repaint, and how often.
- What the person can have in progress on it: typed text, uncommitted choices, an open panel.
- The product's version rule (root `SMART-RULE-0026`) and its harness command.

## Data sources

- The product repository: components, stylesheets, view-state carrier, harness scripts.
- The node's `spec/` for the screen's own contract, and its `LOG.md` for what a rule cost.
- This skill's rules, which are the general form of those lessons.

## Scripts or commands

None of its own. Use the product's own check and harness commands, and `ui-mockup` when what the
screen looks like is in question rather than how it behaves.

## Outputs

- The implemented change, with the tests that fail when a rule above is broken.
- Harness measurements at the viewports the product supports.
- A specification section updated in the same commit as the behaviour.
- A line in the node's `LOG.md` naming the rule the change protects, where one was at risk.

## Permissions

No credentials, no external calls. This skill touches a product repository and the brain's own
records, nothing else. Pushing and merging follow the node's own rules.

## Failure behaviour

- **A rule here conflicts with what the owner asked for:** the owner's instruction wins for that
  change; say in one sentence what it costs and record it against the rule.
- **A repaint cannot be held** (the surface is not in this code's control): say so rather than
  building a half-hold, and keep the draft, which is the fallback that saves the work anyway.
- **The harness cannot reach the surface:** say what was measured by hand and at which sizes,
  rather than reporting a measurement that was not taken.
- Never make a rule pass by weakening the assertion that checks it.

## Logging behaviour

A change governed by this skill writes one `LOG.md` entry in its node naming: what broke or what
was at risk, which rule above it belongs to, and the version it shipped in. An incident that
teaches a **new** rule is added to this file as a neutral rule with a short rationale; the dated
account, in the owner's words where they gave them, goes to
`/memory/skills/ui-implementation/NOTES.md`.

## State, knowledge and task update behaviour

- `STATE.md` of the node carries the version shipped and anything left open for the owner.
- `KNOWLEDGE.md` takes the general form of a lesson when it outlives the screen that taught it.
- A defect found while implementing but out of scope becomes its own task rather than a comment.
- A rule in this file that a second incident contradicts is amended here, not worked around in the
  product.
