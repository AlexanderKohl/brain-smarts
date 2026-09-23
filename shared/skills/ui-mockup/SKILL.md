---
name: ui-mockup
description: Build a UI mockup from a product's own stylesheets, measure it, and refine it with the owner before any of it is written into components or pushed. Use whenever a request changes what a screen looks like – layout, spacing, controls, wording in the interface – rather than only what it does.
metadata:
  id: skill-ui-mockup
  title: UI Mockup
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  external_system: none
  canonical_source: /shared/skills/ui-mockup
  skill_refs: []
  created: 2026-09-02T22:10:00+10:00
  updated: 2026-09-23T13:47:16+10:00
---

# UI Mockup

## Purpose

Show the owner what a screen will look like, in the product's own styling, **before** the change
exists in components – and settle questions of size, alignment and overflow by measuring the
rendered result rather than by eye.

This exists because a described layout and a rendered one are different things. "Filters move into
the column headings" reads as one idea and renders as a dozen decisions about width, wrapping and
which control sits where. Each round of guess-implement-deploy-look costs a deploy and a context
switch for the owner; a mockup costs neither.

## The rule this skill exists to enforce

**A mockup is refined with the owner before any of it is implemented in code, and before anything
is pushed.**

Concretely, and without exception:

1. Build the mockup and show it.
2. **Stop.** End the turn. The owner responds.
3. Change the mockup to match their response. Show it again. Repeat until they accept it.
4. Only then write it into components.
5. Only then commit, and only then push.

Do not run mockup → code → push inside one turn. Do not treat "looks good" on an earlier,
different mockup as acceptance of this one. Do not treat silence, or the absence of objection, as
acceptance – the owner must say something that identifies *this* mockup.

An owner instruction to skip the mockup ("just do it", "no need to show me") is theirs to give and
overrides this skill for that change. Nothing else does.

## Allowed operations

- Read a product's stylesheets and component source (read-only).
- Write one harness HTML file inside the working repository, and delete it afterwards.
- Open the Browser pane on that file, resize the viewport, screenshot, and run measurement
  JavaScript against the rendered page.
- Report findings and measurements to the owner.
- For screenshots kept as artifacts, render the same harness file with headless Chrome (`chrome --headless --screenshot --window-size=1400,900 file:///...`); the Browser pane downscales its screenshots to about 800 px, which is fine for measuring and too small to keep.

## Not allowed

- Editing product components, CSS, or any application source while acting as this skill. Mockup
  first, owner's response, then implementation as ordinary work.
- Pushing anything, to any branch, on the strength of a mockup the owner has not responded to.
- Presenting a mockup built from re-typed or approximated CSS as if it showed the real thing (see
  *Failure behaviour*).

## Required inputs

| Item | Value |
|---|---|
| Product stylesheets | The real `.css` files the screen loads, in load order |
| CSS custom properties | Whatever the app defines outside those files (e.g. `--brand-primary`); read them from the app's global stylesheet, do not invent values |
| Markup fragment | HTML matching what the components actually render – same classes, same nesting |
| Target viewport | The size the screen is really used at, not the pane default |
| Output path | Inside the working repository (see *Scripts*) |

## Data sources

The product repository itself. A mockup is only evidence if it is built from the same stylesheets
the running app loads; anything re-typed is a drawing of an intention, not a preview.

Record with any mockup: which stylesheet files were inlined, the viewport size rendered at, and
whether the markup was copied from the component or hand-written to match.

## Scripts

```bash
python shared/skills/ui-mockup/scripts/build_mockup.py \
  --css <product-repo>/src/app/admin/admin.css \
  --css <product-repo>/src/app/admin/admin-enhancements.css \
  --tokens <product-repo>/src/app/globals.css \
  --body temp/ui-mockup/links-table.html \
  --name links-table
```

Writes `temp/ui-mockup/<name>.preview.html` and prints the `file://` URL to open.

`--tokens` extracts `--*` custom properties from a stylesheet so the mockup inherits the app's real
palette. `--body` is the markup fragment; pass `-` to read it from stdin.

```bash
python shared/skills/ui-mockup/scripts/class_check.py   --css <product-repo>/src/app/admin/admin.css   --html temp/ui-mockup/links-table.preview.html   --borrow view --borrow mono
```

Prints every class the mockup uses that the product's stylesheet also styles, and exits 1 if there
is one, so a generator can fail on it. See *Method* step 2.

A mockup that reproduces the product's own shell – its rail, its page frame – borrows a dozen
classes legitimately. Keep that list **in the generator**, as a named set beside the check, rather
than as a dozen flags on a command line nobody will retype.

## Outputs

- One harness file under `temp/ui-mockup/` while the design is still being argued about.
- **On acceptance the mockup is KEPT, not deleted**, and moved to the node's `design/` folder
  with the spec it belongs to named in the filename. The spec links it. See below.
- Screenshots, shown to the owner in the reply.
- Measurements, quoted as numbers in the reply – not "it fits now" but "content 511px against 570px
  of room at a 620px viewport, no scroll".

### An accepted mockup is the only record of what the owner approved

Rationale: a mockup deleted on acceptance, or left in `temp/`, which is gitignored and
disposable, cannot be named by the people who build the screen, because no one can safely point
at a path that might not exist. They build from spec prose instead - *three columns always*,
*one table, labels once* - and the result can look nothing like the design the owner approved,
with nothing in the repository able to say so sooner.

**A description of a screen is lossy in a way a description of a rule is not.** *One table,
labels once* is true of a dozen layouts, and the owner approved exactly one of them, often after
several rounds. Deleting the mockup keeps the lossy copy and throws away the original.

So, when the owner accepts a mockup:

1. **Move it to `/memory/projects/<node>/design/`**, named for the spec it settles -
   for example `13-compare-page.html`, `13-compare-states.html`. It is tracked, it survives a `temp/`
   clean-up, and a packet can name it knowing it will be there.
2. **Link it from the spec**, in the section it settles, so a reader of the design finds
   the picture without being told it exists.
3. **It is deleted only when the spec is superseded**, and then with the spec.

A mockup that stays in `temp/` is a decision the repository cannot remember.

## Permissions

Read-only against the product repository. The single harness file is the only thing written, and it
is temporary. No credentials, no network calls, no deploys.

## Method

**1. Build from the real stylesheets.** Inline the actual files. This is what catches the problems
worth catching – a `.admin-shell button` rule outranking a new `.sort-heading` class, a modal
`max-height` that clips content, a flex child that will not shrink. None of those appear in a
hand-drawn approximation, and all of them appear on the owner's screen.

**2. Check your class names against the stylesheet, mechanically, every time.** Step 1 is what
makes the mockup evidence; it is also what makes every class name you invent a coin flip against
rules you did not write. A collision is **silent** – the page renders, it just renders wrong. Ten
were found this way across one project's mockups and **not one was visible by eye**: `.flag` was an
uppercase pill that turned a step name into a shout, `.rail` had `height:100vh`, `.mk` was
`position:absolute;left:-19px`, `.jspine` carried `padding:4px 0 40vh 12px` and put half a screen of
white space under a list.

Run `scripts/class_check.py`, or the same set intersection inside your generator, **on every page it
writes**. Not once at the end, by hand: a check that stops being run lets the next collision
through – `.mk` is caught while it runs, and `.jspine` slips past once it stops. Prefix every class
you invent, and pass `--borrow` for the handful you are reusing from the product on purpose.

**3. Generate the page from a data table, do not hand-write the markup.** Put the rows in a list and
render them; the counts, totals and group headings then come from the same list the rows do and
**cannot disagree with it**. Hand-written plates get this wrong quietly – a heading saying 13
over twelve rows survives several rounds because nobody adds up a mockup.

It also makes revision cheap, which is the point: a design settles over five to eight rounds of the
owner's corrections, and regenerating from a changed list beats editing markup every time. Keep the
generator; it is the artefact the next round needs, not the HTML.

**4. Put the harness inside the repository.** The Browser pane renders a file outside the project
folder as a static snapshot it cannot screenshot. `temp/ui-mockup/` is gitignored along with the
rest of `temp/`.

**5. Render at the real viewport.** Resize before screenshotting. An app embedded as a custom page
inside a host application is often roughly 1400×620; the pane's own size is not that, and vertical space is usually the constraint the request
is about.

**6. Measure, do not squint.** The questions that actually get asked have numeric answers:

| Question | Measurement |
|---|---|
| Does it scroll? | `el.scrollHeight > el.clientHeight` |
| Is it aligned? | difference between two `getBoundingClientRect()` centres |
| Does it fit at the smallest real size? | `scrollHeight / 0.92` for a 92vh cap, against the viewport |
| Is the pinned thing still visible? | `rect.right <= innerWidth && rect.left >= 0` |
| Why is this box so tall? | its `getBoundingClientRect().height` against the **sum of its children's** |

Change the CSS in the product, re-inline, re-measure. Quote the before and after.

**Measure the parts, not only the whole.** Fit and alignment are the questions you expect; inherited
padding is the one that actually bites. A container measuring 736px whose five children sum to 229px
is a rule you did not write, and comparing the two numbers finds it in one call – that is how the
`.jspine` collision above was caught, after the class check had been skipped.

A layout the mockup cannot hold is the same kind of finding: a detail panel that has to open inside
a 270px column will never fit two value columns, and knowing that **before** the owner sees it saves
a round.

**7. Screenshot so the owner can read it.** The pane downscales to about 800px wide, so a 1400px
viewport renders text too small to read. Screenshot at a narrower viewport, or scroll and take two,
when the owner needs to read labels rather than judge proportion.

**8. Read your own mockup against five questions before you show it.** Nearly every correction
an owner makes is one of these, and all five are answerable without them. Asking them yourself is
the difference between five rounds and eight.

**Say it once, where it belongs.** Every name, count and value appears on the screen **one** time,
in the place it makes the most sense, and nowhere else. This is the most common correction there
is: a workflow named in the table row and again in the list heading a hand's width below it; a
check named on its row and again as the heading of the panel opening beneath it; an account named
in every column of every table on the page; the same button in two places in two colours. Each one
survived a round because each looked like helpfulness.

When two places both want a value, the one that keeps it is the one a reader is looking at when
they need it, and the other says nothing. A panel that opens directly under its row does not repeat
the row. A column headed with an account does not repeat the account in its cells. A trail that
says where you are is not restated by a *back to* link beside it.

**Every number: what population does it count?** Two numbers of two populations, drawn alike and
sitting near each other, will be read as one. A page once carried five numbers of three populations
– a tile counting workflows, a tab counting checks, a menu counting *its own options*, a table
counting checks again, and a second table counting cases – and the complaint it produced was
"too much data, I don't know where to look", which sounds like density and is not. If a count must
mean something different from its neighbours, draw it differently and say so.

**Every colour: how many meanings does it carry?** One drawing, one meaning. Amber once meant the
category *in both, different*, **and** "this value differs", **and** "this row is open", with a
fourth colour for "moved" – so inside a column where everything was already different, an amber
cell said nothing and the open row read as a difference. Where a category already fills a region,
mark a difference by **dimming what matches** instead, and leave colour to the category.

**Every figure: what does the reader do about it?** A dashboard number nobody can act on is
decoration that costs attention. Two survived several rounds on one page: a count that was five
hard-coded strings, identical for every account forever, and a warning about uncovered items that
were all things the owner had already chosen to ignore. Before drawing a number, finish the sentence
*"and so you would…"*. If you cannot, cut it.

**Every control: does it appear twice?** Same button, same action, two places, often two colours
– usually because one sits with its cause and one sits with the other actions. Keep the one in
the action row; let the cause state the fact and stop.

**9. Show, stop, and wait.** See *The rule this skill exists to enforce*.

## Failure behaviour

- **A stylesheet cannot be read** – say so and name the file. Do not substitute approximated CSS
  and present the result as a preview of the real thing.
- **The screenshot comes back empty or unscreenshottable** – check the harness is inside the
  project folder before anything else.
- **The layout comes back collapsed** – a sidebar stacked above the content, columns turned into
  rows – the pane's own width tripped one of the product's media queries. Set an explicit
  viewport before judging anything about the layout; the pane is not a phone and the page should not
  be told it is.
- **The page is taller than the pane and the screenshot only crops** – scale the document rather
  than the viewport, so the media queries still see the real width:
  `document.documentElement.style.transform='scale(0.62)'`, with `transformOrigin='0 0'` and an
  explicit `width`. Lighter than the headless-Chrome route above, and it keeps the layout honest.
- **A measurement contradicts the screenshot** – trust the measurement, and say which one the
  owner is looking at.
- **The owner's request is ambiguous in a way the mockup would answer** – build both and show them
  side by side rather than asking them to imagine the difference.

## Logging behaviour

Nothing routine. When a mockup round settles a decision that outlives the conversation – a layout
rule, a constraint discovered by measurement, a rejected alternative and why – record it in the
owning project's `STATE.md`, and the decision itself in its `LOG.md`, as ordinary governance work.

## State, knowledge and task updates

- A mockup accepted but not yet implemented is an open task. Create or update it under `/memory/tasks/`
  with what was agreed, so the agreement survives the session.
- A measured constraint that will bind future work – an iframe's usable height, a cap that forces a
  layout – belongs in the project's `KNOWLEDGE.md`, not only in a commit message.
- Nothing here is a governance change; this skill's rule binds work done through this skill. To
  bind UI work repository-wide, propose an addition to root `RULES.md` under the change protocol in
  `/CONTRACT.md` §13.2 and obtain explicit owner acceptance.
