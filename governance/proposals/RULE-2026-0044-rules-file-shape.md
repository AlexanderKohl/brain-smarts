---
id: RULE-2026-0044
title: How the root rule file is written
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-09-17T15:40:00+10:00
updated: 2026-09-17T17:30:00+10:00
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
project_refs:
  - /memory/projects/brain-development
---

# How the root rule file is written

This proposal mints two rules, `RULE-2026-0044` (how this file is written) and `RULE-2026-0045`
(look for the existing one first), and rewrites `/RULES.md` to the convention `0044` states. It is
one decision and takes one answer, at the owner's direction of 2026-09-17.

## Blocked: the `0045` tag is taken

**This proposal cannot be implemented as written.** It mints `RULE-2026-0045` for "Look for the
existing one first". On 2026-09-17T18:05 another session minted `RULE-2026-0045` for "A record says
what is true now, and something checks it", which is now `proposed` in this same directory.

Two proposals claim one tag. That is precisely the identity failure this proposal argues against,
arriving from the other direction: not a rule renumbered, but a number reused. It happened because
this proposal reserved a tag it had not yet been granted, and nothing in the store prevents a
second reservation.

Neither should be renamed by an agent. The options, for the owner:

1. **This proposal takes the next free tag** for the search rule, and `0045` stays with the record
   staleness rule, which is further along and already cites `0045` in its own text (recommended).
2. The staleness rule moves, which is worse: it is the more advanced proposal and would have to
   revise its own references.
3. The search rule is dropped from this proposal entirely, leaving the restructure to keep every
   existing tag and mint only `0044`.

Until that is settled, `RULE-2026-0044` stays `proposed` and nothing in it should be activated. The
rest of this record is unchanged and still accurate.

## Current problem

The owner's report: the numbering is confusing, and rules appear to get new numbers when they are
rewritten.

The second half of that is not happening. CONTRACT §13.2 and **Protected governance** both require
a rewritten rule to keep its ID, and `RULE-2026-0032` has been rewritten twice under its own. Only
two numbers were ever retired, `0014` and `0024`, both absorbed into `0017`, both before that
policy existed. What is actually wrong is three other things.

**The file has no stated order, and half of it has no order at all.** The 22 rules appear as
`0018, 0023, 0017, 0004, 0016, 0025, 0003, 0010, 0022, 0013, 0015`, then `0028` through `0042`
ascending. The first eleven are in a hand-made order nobody recorded; everything since has been
appended numerically. **Every list has a deliberate order** requires a list to state its order.
This one does not, so it reads as random.

**The gaps are unexplained.** `0005`–`0009`, `0011`, `0012`, `0014`, `0019`–`0021`, `0024`,
`0026`, `0027`, `0031`, `0036`, `0038` and `0041` are missing from root. Every one has a good
reason: a node rule, a contract clause, a superseded rule, or a proposal never accepted. Nothing
in the file says so, so it reads as though rules went missing.

**The ID is doing a job it is bad at.** `RULE-2026-0037` is a proposal-counter key serving as the
human name for "the rule about delegating work". It is precise and unmemorable, which is right for
a governance record and wrong for prose.

Separately, the file is 5,440 words, all of it read at every bootstrap by every session
(**Token-efficient operation**), and roughly a fifth of it is procedure that belongs in a skill.
Three rules open with the same duty stated three ways, and a closing section restates twelve
clauses of the contract that is read immediately before it.

## Current wording

The live `/RULES.md` at commit `04b448f`: 370 lines, 5,440 words of body, 22 rules, 29 em dashes
predating **An en dash, never an em dash**. The per-rule disposition below gives the exact
before-and-after for every one.

## Proposed wording or exact diff

Replace the body of `/RULES.md` below its front matter with the following. Front matter keeps its
`id`, `title`, `type`, `schema_version`, `contract`, `scope`, `status`, `created` and `owner`;
`updated` takes the implementation clock and `accepted_proposal` becomes `RULE-2026-0044`.

```markdown
# Brain Root Rules

Read `/CONTRACT.md` first. This file does not repeat it.

A rule is referred to by its **name**. Its `RULE-2026-NNNN` tag is a governance key: permanent,
never reused and never renumbered, so that every proposal, log entry and commit message citing it
still means what it said. Rewriting a rule keeps its tag.

The tags are sparse because they come from one counter shared by every proposal ever written, not
from this file. A tag missing here is a node rule, a clause of the contract, a rule replaced by
another, or a proposal that was never accepted. Nothing is lost; look it up in
`/projects/brain-development/proposals/`.

Groups run in the order a session needs them: governance, then working with the owner, then what
the brain knows, then running a session, then building software, then committing and versioning.
Within a group, the rule that applies most often comes first.

Tags in this file: `0003`, `0004`, `0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`,
`0025`, `0028`, `0029`, `0030`, `0032`, `0033`, `0034`, `0035`, `0037`, `0039`, `0040`, `0042`,
`0044`, `0045`.

## Governance

### Protected governance
`RULE-2026-0003`, restating CONTRACT §13.2

- Do not activate a protected governance change without the owner's explicit acceptance under
  Contract section 13.2.
- Report accepted governance changes with their proposal ID, exact changed files, effective
  contract version and validation result.
- Small additive or clarifying changes to an existing numbered rule amend that rule in place and
  keep its tag. Mint a new `RULE-YYYY-NNNN` only for a distinct new rule, not a tweak, extra
  sentence or tighter constraint on an existing one. Record the amendment on the original
  proposal record; do not supersede a live rule with a new number.

### How this file is written
`RULE-2026-0044`

- A rule states a duty and the authority that comes with it. Procedure, field names, templates,
  formats and checklists live in the skill the rule names. The test: if an agent never opened the
  skill, would it fail to know the duty exists, or only carry it out clumsily? The first belongs
  here. The second belongs in the skill, which may implement a duty and may never expand it.
- Keep this file short. Every word is read at every bootstrap, by every session, forever
  (**Token-efficient operation**). A rule that has grown past its duty is trimmed the next time it
  is touched, and its procedure moved to a skill.
- Refer to a rule by name in prose, and reserve the tag for governance records, where identity
  must be exact. Do not restate another rule's duty; name it and let it stay in one place.
- Append a new rule to the group it belongs in, with the next tag from the shared counter. Do not
  reorder or renumber existing rules to make room.

## Working with the owner

### Communication efficiency
`RULE-2026-0018`

- In voice mode, when a clarifying question is required, ask one question at a time and wait for
  the answer before asking the next, unless the owner explicitly requests a grouped questionnaire.
  Outside voice mode, presenting a list of clarifying questions is acceptable, especially when
  scoping a software project. Do not invent questions when a safe default exists.
- Prefer a reversible default and proceed when multiple approaches are valid and the risk is low;
  state the chosen approach in one short line. Ask only for irreversible actions, secrets,
  material trade-offs, or when policy requires owner choice.
- Do not narrate process before acting ("I'll bootstrap.", "Let me check.", "I'll start by
  reading."). Run tools or answer; put status only in the final reply when the owner needs a
  result.
- Every question to the owner carries at least one concrete suggested answer, so the owner can
  reply "yes" or "ok". When several valid options exist, number them and mark the recommended one,
  so the owner can reply with a number. The owner may always answer with different instructions
  instead; a suggestion or a numbered list never limits the choice.

### Token-efficient operation
`RULE-2026-0004`

- Read and prompt with only the minimum context relevant to the current task; avoid loading
  unrelated files, restating unchanged context, or repeating information already available
  elsewhere.
- Structure nodes, files and skills so related content can be read independently in small,
  targeted pieces; split large or mixed-purpose files where that measurably improves token
  efficiency and response time.

### An en dash, never an em dash
`RULE-2026-0042`

- Everything this repository writes uses the en dash (`–`). The em dash (`–`) is never used: not
  in a document, a record, a comment, a commit message, a string a person reads on screen, or a
  reply in the conversation.
- Where an em dash would have been, an en dash takes its place with a space each side, or the
  sentence is split in two, which is usually better.
- A hyphen stays a hyphen: this rule is about the long dash, and changes nothing in a hyphenated
  word, a command-line flag, or a range written with a hyphen.
- Existing text is corrected when its file is next touched for another reason, in the same commit,
  and never in a pass of its own that buries a change of substance.

### Every list has a deliberate order
`RULE-2026-0040`

- Every list a person reads is put in an order chosen for that reader, never left in the order it
  was produced: dropdown options, table rows, report sections, check findings, reply bullets,
  index entries. Insertion order, capture order, map order and API order are not orders; they are
  accidents.
- The default is alphabetical by the label the reader sees, with numbers inside labels compared as
  numbers, so `1.2` precedes `1.10`. Another order replaces it only when the reader is better
  served and the code or the document says so: by time when they follow a sequence, by severity
  when they act on the worst first, by size when the largest matters, or by a fixed domain order
  such as pipeline stages. The chosen order holds across renders.
- A list shows what the reader can use. Items that cannot be used from it, such as a draft where
  only published items act, are left out or set apart under their own label, and the code says
  which.
- Reviews of a deliverable check its lists: an unordered list is a defect, not a style choice.

### Owner-facing shell includes cd
`RULE-2026-0013`

- Whenever giving the owner shell commands to run, always include an explicit `cd` (or equivalent)
  to the repository root `<brain_root>` (or the active absolute working directory if
  the command must run elsewhere) before the command, so the owner does not have to locate the
  correct folder.

## What the brain knows

### Internal-first then external lookup
`RULE-2026-0010`

- When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge,
  and other already-known canonical homes) with a **targeted** search. Do not run exhaustive
  repository grep theatre to prove absence.
- If the fact is absent or still uncertain after that internal check, use the authoritative
  external shared skill when one exists or is mandated (for example ABR Web Services for
  Australian Business Numbers and GST registration). After a verified external result, update the
  relevant durable brain record when the fact belongs in the repository.
- Do not delegate work to explore/repo-only subagents when the answer requires vault credentials,
  Gmail, or an external API. Match agent capabilities to the job, or do the lookup in-session.
- When the owner redirects to a different path (skill, external system, email), abandon or stop
  parallel searches that the redirect made obsolete; do not finish a doomed explore pass "for
  completeness."

### Per-API quirk knowledge base
`RULE-2026-0022`

- Every shared `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, one small
  file per confirmed or hypothesised piece of non-obvious behaviour for that system, scaffolded
  when the skill is created. A quirk found for a system with no skill yet gets the minimal skill
  folder and scaffold first, rather than no canonical home.
- Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external
  API, search that system's `knowledge/` folder first, by the conventions in its `_CONVENTION.md`.
  A `refuted` entry is a warning against repeating that hypothesis; a `deprecated` entry points to
  its `superseded_by` replacement and is not current fact.
- After resolving genuinely unexpected behaviour, write one entry from the template the convention
  names. This store is for quirks and workarounds, not a changelog: routine work that revealed
  nothing unexpected gets no entry.
- An entry is `pending` while its hypothesis is unconfirmed, and `confirmed` once a live probe or
  observed real use corroborates it. When later evidence contradicts an entry, never delete it:
  set `refuted` for a wrong hypothesis or `deprecated` for changed behaviour, and note what
  changed and when. Link the replacement with `superseded_by` when one exists, or leave it for the
  correcting entry to backlink via `refuted_by` once one does. An entry may be refuted or
  deprecated before any replacement exists.
- Promote, refute or deprecate opportunistically, the next time work touches that quirk, rather
  than deferring to a scheduled review that does not otherwise exist in this repository.

### Portable behavioural rules only
`RULE-2026-0015`

- Keep durable behavioural rules only in portable governance: `/CONTRACT.md`, root and node
  `RULES.md` files, and skill operating instructions. Do not create or maintain host-specific
  behavioural rule files that restate or extend how agents must behave.
- Host entry files may only point agents to portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`,
  `/AGENTS.md`, `/ONBOARDING_AGENT.md`) and must not carry independent behavioural policy.

## Running a session

### Context handoff checkpoint
`RULE-2026-0032`

- Write a handoff checkpoint before context runs out, preferring a **stage boundary** to a context
  threshold: immediately after a validated, committed increment and before starting a new stage,
  when the repository and the agent's understanding agree. Take it at whichever comes first, that
  boundary or roughly the last fifth of the context window.
- Never begin a stage the remaining context is unlikely to carry to a committed, validated state.
  Checkpoint and say so instead.
- A checkpoint updates, in the owning node: `STATE.md` with the position, what is in flight and
  the exact next action; `KNOWLEDGE.md` with facts a later session could not re-derive cheaply,
  especially external-system behaviour established by experiment; `LOG.md` with what happened and
  why; and `/tasks/` for anything outstanding.
- Record open questions with enough context to act: what is unknown, what was tried, what would
  settle it. Record negative findings and the evidence for them, which code never recovers.
  Distinguish **verified** from assumed, and name where uncommitted work lives outside this
  repository. A checkpoint must not present unfinished work as finished: report the actual state,
  including failures, blocked steps and anything skipped.
- The position lives under `## Handover` in the owning node's `STATE.md`, in the form
  `/shared/skills/delegate-work/` specifies, written before the prompt and kept current at every
  checkpoint. The `## Handover` of `/projects/brain-development/STATE.md` also names the **active
  conductor**, by session title and the time it took over, and the other live sessions it knows
  of; a new thread that finds an active conductor asks the owner which thread continues before
  dispatching anything.
- End with **one handover prompt**, a pointer and not a summary: the bootstrap files, the owning
  node's `STATE.md`, and the single next action. Ten lines at most, with nothing in it a file
  already says. Write it under `## Handover prompt` and repeat it last in the reply.
- Finish with the Git exit check under **Lightweight Git exit check**.

### Delegated parallel work
`RULE-2026-0037`

- Delegate only work that is independent, bounded and consumable as a compressed result: one
  outcome, no back-and-forth between workers, and a result the conductor can use without the
  worker's reasoning. State in one line why parallel beats sequential before dispatching. Tightly
  coupled reasoning and work needing constant shared state stay with one agent.
- Delegate through `/shared/skills/delegate-work/`. Packets and results are ephemeral
  instrumentation, not task records; work that outlives the session is a `/tasks/` record with
  `waiting_on` and `next_review`.
- Workers start isolated by default, and a packet that forks the conductor's context states why.
  Workers write no canonical file and do not commit. They return findings,
  artifacts in their run folder, and every changed path with its validation result. A worker that
  must change code works in an isolated worktree or branch.
- Workers use no credentials and take no external side effect unless the packet names a target the
  owner confirmed under CONTRACT §10.5. The default is none. A worker needing an owner decision
  stops with status `blocked` and the question.
- Budget: depth one, and at most four workers per run, until a measured trial under
  `/projects/brain-development/` justifies more.
- The conductor routes each result under CONTRACT §5 and §6, treats worker claims as unverified
  until checked, writes one `LOG.md` entry per run, and does the Git accounting. Never claim
  parallel execution on a host that ran packets in sequence, and never invent the host or model
  that ran a packet.

## Building software

Except where a rule says otherwise, every rule in this group applies to every software or
development project. **No real data in mock or sample data** and **Surface external-system
configuration mismatches before coding around them** are the two exceptions, and each states its
own wider scope.

### Look for the existing one first
`RULE-2026-0045`

- Before adding a function, a component, a write, a control-flow path, a pattern, an abstraction,
  a service or a dependency, search the active project for what already does that job, and reuse
  or extend it where it remains appropriate.
- When a new approach is genuinely required, say why in the change, and say whether the existing
  implementations should later converge on it.
- This is the software half of the duty that **Internal-first then external lookup** and
  **Per-API quirk knowledge base** state for facts. Search targeted, not exhaustively.

### Product-development process
`RULE-2026-0028`

- Before a non-trivial discovery, design, implementation, release or lifecycle-investment
  increment, follow this rule with `/shared/skills/product-development/` as its guide. Clearly
  non-material corrections, behaviour-preserving refactors and like-for-like repairs use ordinary
  proportionate discipline; a small reversible improvement may use the skill's light path.
- Establish whether the work is a new product, a baseline, a feature, an urgent repair or a
  lifecycle review; locate it at its current lifecycle position; reuse valid evidence; and reopen
  only the gates whose assumptions or downstream consequences are affected.
- Select light, standard or high-assurance depth by the skill's criteria. Always consider both
  internal-use and commercial routes, scaling the research to their plausible value.
- The acting agent researches, tests and presents the evidence and a recommendation for each
  applicable gate. The owner decides each gate unless an accepted rule explicitly delegates that gate
  and risk class. Record the decision and the exact next investment it authorises, in a canonical
  product-development record or equivalent project-native plan.
- At standard and high-assurance depth, use at least two distinct underlying models at material
  opportunity, design, delivery and release-readiness checkpoints, when proportionate, available
  and permitted. Protect secrets, and minimise personal, customer, security-sensitive and
  commercially sensitive context before review.
  Synthesise disagreements as evidence, not votes. If distinct models are unavailable, disclose
  the limitation and do not claim that multi-model review occurred.
- The mandatory semantics are contained in this rule.

### One canonical implementation, no duplicated side effects
`RULE-2026-0030`

- Prefer one canonical implementation and call it. Do not copy a working sequence into a second
  place, wrap the old path while leaving it live, or add a new write that repeats an existing side
  effect (the same field, file, API call, or state change).
- When a new path replaces an old one, remove the superseded code in the same change: leftover
  writers, leftover callers, and any second frontend or backend trip that only existed to do the
  same work.
- Extract a shared helper only when two or more live call sites need the same behaviour. Do not
  add an abstraction for a single use, and do not keep both the helper and the inlined original.
- Lean code means fewer live paths, not denser cleverness. Delete dead code. Do not preserve a
  known duplicate "for safety" when the remaining path already covers the cases.
- Distinct later stages may write the same field only when that stage has a different meaning (for
  example a later workflow step that must refresh it). Do not treat a second write at the same
  stage as a backup.

### Whole-system implementation review
`RULE-2026-0033`

- Optimise each change for the health of the whole system, not only the immediate task. Evaluate
  it against upstream and downstream code, shared services, data models, APIs, workflows, state
  transitions and integrations.
- Leave the architecture simpler, or at minimum no more complex than the requirement demands.
  Prefer the smallest clear implementation that fully satisfies it.
- When a requirement conflicts with an existing architectural, product or data-model decision,
  surface it to the owner and resolve it deliberately. Do not quietly create an exception. This
  extends **Surface external-system configuration mismatches before coding around them** to
  decisions inside the codebase.
- When a workaround is unavoidable, make it visible in the code and the project record, and say
  what would be required to remove it.
- Keep code understandable without reconstructing hidden assumptions: explicit data flows, clear
  responsibilities, predictable naming, straightforward control flow, focused modules. Do not use
  cleverness where a simpler implementation gives the same result.
- Before reporting a non-trivial change complete, run the whole-repository review in
  `/shared/skills/product-development/` and state its answers briefly. Clearly non-material
  changes may skip it.

### Security designed into every implementation
`RULE-2026-0034`

- Treat security, privacy and access control as part of the implementation, not a later review
  step. For each change that touches an endpoint, a query, a permission, stored or transmitted
  data, an integration or a log, consider: authentication, authorisation, tenant and account
  isolation, input validation and output encoding, secrets and credential handling, sensitive data
  in responses and logs, API permissions and scopes, and what the code does when a check fails.
- Apply least privilege. Request, store, transmit and expose the minimum sensitive data and the
  narrowest scopes the requirement needs.
- Do not rely on UI restrictions for security. Enforce important rules server-side at the trust
  boundary that owns them.
- Fail closed. When identity, tenant, scope or a required mapping is uncertain, stop the operation
  and report, rather than proceeding with a guess or a default.
- Scope every query, write and external call by the tenant, account or location it belongs to. Do
  not let a request for one tenant read or change another's data through a missing filter or an
  inferred identifier.
- Never log or return secrets, tokens, credentials or more personal data than the caller is
  entitled to. Treat a leaked identifier that grants access as a credential.
- When a change materially widens an externally reachable surface, adds an authentication or
  payment path, or handles sensitive data for the first time, escalate to at least standard depth
  under **Product-development process** and say so in the change.

### Tests demonstrate behaviour
`RULE-2026-0035`

- Tests must prove that the required behaviour works, not merely exercise the implementation. For
  each change, identify the important behaviours, invariants, boundary cases and failure
  conditions first, then make sure tests cover them.
- When fixing a bug, add a test that would have failed before the fix, wherever practical. If it
  is not practical, say so in the change and why.
- Include negative and boundary cases where they materially affect correctness: the empty input,
  the missing permission, the second tenant, the failed external call.
- Prefer tests that remain valid if the internal implementation changes. Assert on observable
  behaviour and outputs, not on private structure or call sequences.
- Do not report an existing green suite as evidence for new or changed behaviour unless a test
  actually asserts that behaviour. State what the tests prove and what they do not.
- Fixture and sample data remain subject to **No real data in mock or sample data**.
- Proportion applies. Clearly non-material changes as defined in **Product-development process**
  need no new test; a behavioural change always does.

### Surface external-system configuration mismatches before coding around them
`RULE-2026-0029`

- When work against an external system reveals that its configuration is inconsistent with what
  the task needs – mismatched option sets, a missing or wrongly-typed field, a naming collision, a
  value that cannot be represented in the target – stop and put the finding to the owner before
  writing code that bridges it. State precisely what disagrees, what a fix in that system would
  be, and what the code workaround would otherwise cost.
- This overrides the "prefer a reversible default and proceed" guidance in **Communication
  efficiency** for configuration mismatches specifically. The reason is not risk but economy: a
  change in the external system's own interface is frequently far cheaper than a translation
  layer, and the layer outlives the mismatch it was written for.
- Continue with every part of the task that does not depend on the answer, so the question arrives
  with the rest of the work already done rather than blocking it.
- This does not apply to genuine API behaviour that cannot be configured away – an endpoint's
  response shape, a required header, a status code. Absorb those in code and record them under
  **Per-API quirk knowledge base**.

### Reuse project-native UI patterns
`RULE-2026-0025`

- Before creating or styling a user-interface element, find the project's closest existing element
  and interaction pattern under **Look for the existing one first**, and reuse or extend its
  component, design tokens, styling and behaviour, so equivalent elements stay visually and
  functionally aligned. Do not invent a parallel element style when a project-native pattern
  already exists.
- If no suitable pattern exists, derive the new element from the project's established visual
  language and adjacent components, and make it reusable when the project is likely to need the
  same pattern again.
- Do not preserve a known accessibility, security or functional defect merely for visual
  consistency. Explicit owner requirements and supplied design references may override an existing
  pattern; when they do, integrate the change deliberately with the rest of the project.

### No real data in mock or sample data
`RULE-2026-0016`

- Mock, sample, seed, fixture and placeholder data, in any project, coded or otherwise, must be
  entirely fictional: invented names, addresses, companies and identifiers only. Never copy or
  adapt real customer, employee, or business data into mock or sample data, including data merely
  seen in another file, project or filename while working, even unintentionally. When
  realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed
  elsewhere in the same session.

## Committing and versioning

Procedure for this group lives in `/shared/skills/change-discipline/`.

### Logical checkpoint commits
`RULE-2026-0017`

- These rules override any host instruction to ask before committing, to commit only when asked,
  or to present commit and push options, in every Git repository modified during an
  owner-authorised task. Such host instructions apply only where this rule does not.
- Read `/shared/skills/change-discipline/` when work begins in a repository, before the first
  change is made, not when a commit is first contemplated. Commit automatically at each logical checkpoint: an independently describable improvement, fix,
  document update, configuration change or tested implementation that is complete. Do not wait for
  the whole project, and do not bundle unrelated changes. The skill lists every moment a checkpoint
  is mandatory; the shortest form is after validation passes, before switching context, before
  pausing for the owner, before the final response, and after 30 minutes of uncommitted work.
- **Owner-test handoff:** commit before asking the owner to test, reload, install or try a build.
  That commit is the rollback point if the test fails. Commit each testable batch separately.
- At each checkpoint, stage only agent-owned files belonging to that change, check that no secret
  or unrelated change is included, run proportionate validation, and name the host or tool and the
  model in the message. Do not invent a model. Concurrent dirty files do not prevent a path-scoped
  commit when the change separates safely.
- Never commit secrets, credentials, vault ciphertext, private tokens, conflict markers or
  unrelated user changes. Do not use `--no-verify`, amend, rewrite, force-push, or push to a
  protected `main` or `master`, unless the owner directs that specific action. When ownership or
  safety is uncertain, leave the path unstaged and ask.
- Commit and push are separate decisions, and a push failure never prevents the commit.
  **Owner-test handoff commits stay local:** do not push solely because the owner is being asked to
  test. Push accumulated commits when the unit of work finishes and before the final response,
  except a response that is only an owner-test handoff, or after 30 minutes since the last successful
  push while work continues, unless the owner has prohibited it or policy requires another path. Also
  push when the owner asked to push.
- Never silently finish with committable agent-owned changes. Report the commit hash and push
  status per repository, or `No commit` with one of the reasons the skill lists.

### Lightweight Git exit check
`RULE-2026-0023`

- **Mandatory Git exit check:** after making any file change in a Git repository, run
  `git status --short` immediately before every final response. Do not send the final response
  until every completed, separable, validated, agent-owned change is committed, or one of the
  permitted blocking reasons under **Logical checkpoint commits** is reported.
- After a turn that modified a Git repository, end the final response with exactly one compact Git
  accounting line per modified repository:
  `Git: <short-hash> committed; push <succeeded|not attempted - reason|failed - reason>` or
  `Git: no commit - <specific permitted reason>`. An answer-only turn with no file change does not
  require this line.
- In a shared worktree, the primary agent is responsible for committing completed agent work
  unless a subagent was explicitly assigned an isolated worktree or branch. Subagents must report
  every changed path and validation result to the primary agent, and must not assume another agent
  will commit without that handoff.

### Version every change, and show it
`RULE-2026-0039`

- Every software or development project carries one version of three numbers, `first.middle.last`,
  in the project's own version field and nowhere else. `/shared/skills/change-discipline/` is read
  before work starts on a change that will reach a build, not at the moment of the bump.
- Each logical change reaching a build a person can load, run or deploy bumps exactly one number
  in the same commit, the highest that applies: **first** when something that worked before no
  longer works the same way without action by someone, **middle** when a person can see or do
  something they could not before, **last** for everything else. The skill holds the full test.
- Below `1.0.0` a breaking change bumps the **middle** number instead, while still being named as
  breaking in its commit message and the node's `LOG.md`. `1.0.0` is set once, deliberately, when
  the owner declares the product released.
- Every build embeds its version, the commit it was built from, the build time and, off the main
  branch, the branch name; a build from a dirty tree is marked as such. The version is shown where
  a person looks first, and the rest is one step away, in the places the skill lists.
- A test fails when a commit changes the product without changing the version, so nothing reaches
  a build unnumbered. Commit messages, task records and log entries name the version a change
  lands in.
- When asking the owner to reload, test or deploy, state the version and build identity they
  should see, so a stale build is recognised at a glance.

```

## Reason

Four changes, each with its own reason.

**Names as headings, tags as keys.** The tag stays exactly as it is: permanent, never reused,
never renumbered. It is referenced 1,291 times across 327 files, and 105 of those are in git
commit messages, which cannot be rewritten. Renumbering to `Rule 1`, `Rule 2`, `Rule 3` would make
every historical acceptance point at a rule it did not accept, which is the one failure a
governance system cannot recover from. Making the *name* the handle gets the readability without
touching identity.

**A stated order, and an explanation of the gaps.** Both are one paragraph each, and together they
retire the two questions the file currently provokes every time it is read.

**Mechanism into skills.** The same split applied to `RULE-2026-0043`, with the test written down
in `0044` so it is applied consistently from now on: if an agent never opened the skill, would it
fail to know the duty exists, or only carry it out clumsily? The first stays in the rule.

**One duty, one home.** **Reuse project-native UI patterns**, **One canonical implementation, no
duplicated side effects** and **Whole-system implementation review** each opened by telling the
agent to search for what already exists. Three statements of one duty is how an agent follows none
of them precisely, so `0045` states it once and the three rules keep only what is theirs.

## Scope and behavioural consequences

Repository-wide, every agent, from acceptance onward.

**No rule is retired, renumbered or loses a duty.** All 22 tags survive, two are added, and the
disposition below accounts for every word removed.

| Tag | Rule | Before | After | Change |
|---|---|---:|---:|---:|
| 0017 | Logical checkpoint commits | 593 | 383 | -210 |
| 0039 | Version every change, and show it | 485 | 263 | -222 |
| 0032 | Context handoff checkpoint | 487 | 321 | -166 |
| 0022 | Per-API quirk knowledge base | 353 | 246 | -107 |
| 0033 | Whole-system implementation review | 312 | 182 | -130 |
| 0028 | Product-development process | 319 | 230 | -89 |
| 0037 | Delegated parallel work | 312 | 246 | -66 |
| 0040 | Every list has a deliberate order | 239 | 188 | -51 |
| 0030 | One canonical implementation | 219 | 189 | -30 |
| 0025 | Reuse project-native UI patterns | 144 | 131 | -13 |
| 0034 | Security designed into every implementation | 249 | 245 | -4 |
| 0023 | Lightweight Git exit check | 157 | 155 | -2 |
| 0003, 0004, 0010, 0013, 0015, 0016, 0018, 0029, 0035, 0042 | unchanged but for the tag line | 1,196 | 1,213 | +17 |
| 0044 | How this file is written | new | 182 | +182 |
| 0045 | Look for the existing one first | new | 91 | +91 |
| | Contract restatements | 153 | 40 | -113 |
| | Header and group headings | 116 | 330 | +214 |
| | **Total** | **5,440** | **4,624** | **-816** |

**Where the removed text goes.** Nothing is deleted; each item lands somewhere an agent doing that
work already reads.

| From | What moves | To |
|---|---|---|
| 0017 | The enumerated mandatory-checkpoint triggers, the staging procedure, the permitted `No commit` reasons | `/shared/skills/change-discipline/` (new) |
| 0039 | The three number tests in full, the list of places build identity is displayed | `/shared/skills/change-discipline/` (new) |
| 0032 | The full contents of `## Handover`: runs, workers, packets, branches, pending results, builds, owner steps, open decisions, the reminder that a worker's completion notice reaches only the launching thread, and the cross-node pointer convention | `/shared/skills/delegate-work/`, which already holds the handover procedures |
| 0037 | Packet and result format, the `/temp/delegation/runs/` layout | `/shared/skills/delegate-work/` |
| 0028 | The depth-selection criteria enumeration, the canonical-record minimum fields | `/shared/skills/product-development/` |
| 0033 | The seven whole-repository review questions | `/shared/skills/product-development/` |
| 0022 | Filename convention, `Glob`/`Grep` search patterns, required frontmatter fields, template paths | Each `knowledge/_CONVENTION.md`, which **already carries all of it verbatim** and already points back here for the duties |
| Contract restatements | Twelve restated clauses | `/CONTRACT.md`, which is read immediately before this file |

The `0022` row is the proof the split works: that convention file already says "See root
`/RULES.md` for when to create, promote, refute or deprecate an entry", which is the division this
proposal generalises.

**On the size, and on how the figure kept moving.** The reduction is **15.0%**: 5,440 words to
4,624. Three earlier figures were wrong, and the pattern in them is worth stating plainly, because
it is the argument against judging this change by its word count at all.

| Reported | Figure | Why it was wrong |
|---|---|---|
| In conversation, before the file was worked through | ~50% | Assumed about half the file was procedure. The real figure is about a fifth |
| After the first draft | 19.5% | Taken before any semantic audit |
| After the first audit | 17.2% | Five thinned or broadened duties cost 125 words to repair |
| After the second review | **15.0%** | Four more losses, including the group scope sentence, cost a further 118 |

Every correction moved in the same direction, and each was found by reading rather than counting.
Existing rules now lose 1,089 words, the two new rules add 273, and the header and group headings
add 214. Cutting further would thin duties rather than move procedure, and **Security designed into
every implementation** is left at full length deliberately: it applies to every change, including
the trivial ones that never open a skill.

### Semantic-preservation audit

Every duty, exception, scope limit and grant of authority in the current 22 rules was compared
against its destination, bullet by bullet. Five were thinned or broadened in the first draft and
are restored in the text above. They are listed here because a reviewer should check the repair,
not take it on trust.

| Rule | What the first draft lost | Restored as |
|---|---|---|
| 0017 | `Owner-test handoff commits stay local: do not push solely because the owner is being asked to test`, the `except a response that is only an owner-test handoff` carve-out, and `Also push when the owner asked to push` | All three, in the commit-and-push bullet |
| 0039 | Scope broadened: `Every software or development project` had become `Every project` | Original scope wording |
| 0032 | `Report the actual state, including failures, blocked steps and anything skipped` | Appended to the unfinished-work duty |
| 0037 | `A packet that forks the conductor's context states why` | Returned to the isolation bullet |
| 0028 | `Protect secrets` and `security-sensitive` from the context-minimisation duty | Both returned |

**A second round of review found four more, including one this audit had wrongly reported as
clean.** They are recorded here rather than quietly fixed, because the way the first one happened
matters more than the loss itself.

| Rule | Second-round loss | Restored as |
|---|---|---|
| group scope | **The `## Building software` heading and its scope sentence were absent from the replacement**, so `0025`, `0028`, `0030`, `0033`, `0034`, `0035` and `0045` lost the software boundary each previously stated for itself. The first audit claimed this group carried their scope. It did not; the claim was made from the drafted text and never re-checked against the file | Group heading and scope sentence restored, with `0016` and `0029` named as the two rules that keep a wider scope of their own |
| 0022 | `set superseded_by or leave it for the correcting entry to backlink via refuted_by once one exists` had become `link the replacement`, removing the allowance to refute or deprecate before any replacement exists | Full allowance restored, and stated explicitly |
| 0017 | `since the last push` had dropped `successful`, so a failed attempt would reset the 30-minute interval | `last successful push` |
| 0032 | The active conductor's session title, the time it took over, and the other live sessions it knows of had moved to the skill, while the skill draft said they stay in the rule | Returned to the rule, so destination and audit agree |

**How the group heading was lost, because it bears on how the rest should be reviewed.** The
tightening pass replaced each rule body by splitting the file on `### ` headings. The
`## Building software` heading and its scope sentence sat inside the body that followed
**Delegated parallel work**, so replacing that body deleted them. A word count cannot see this: the
group heading is twelve words. Only reading the resulting file against the original finds it, which
is what the second review did and what the first audit should have done.

One check does come back clean, and was verified against the file this time rather than the draft.
No rule lost a grant of authority: the host-instruction override in `0017`, the maintenance
permissions, the delegation budget and the gate-decision reservation to the owner all appear in the new
text unchanged.

Each skill that now holds a moved obligation has an explicit invocation trigger in the rule that
sent it there, so the obligation is reachable: `change-discipline` is read before the first commit
of a session and before the first version bump in a project; `delegate-work` is named as the route
for every delegation and as the form the `## Handover` takes; `product-development` is named as the
guide for every non-trivial increment and as the home of the whole-repository review.

## Risks and conflicts

- **Heading anchors.** Preflight resolves a `file.md#anchor` in metadata by requiring a heading to
  begin with the anchor token, so an anchor of the form `/RULES.md#RULE-2026-0037` would break.
  None exists: a repository-wide search outside `/temp/` returns no anchor link into `/RULES.md`.
  After this change such an anchor must use the name.
- **`RULE-2026-0043` is pending and touches the same file.** Whichever is accepted second adapts
  to the first. If `0043` lands first, its section is carried into the restructure under **What
  the brain knows** and its tag joins the list. If `0044` lands first, `0043` is inserted as a
  named rule in that group. Neither changes the other's wording.
- **The skill that does not yet exist.** `/shared/skills/change-discipline/` is created by this
  implementation and must exist before the trimmed `0017` and `0039` point at it. Until it does,
  those rules would name a missing path. The migration orders it first for that reason.
- **A duty could be thinned by accident.** The disposition table is the check, and the validation
  below requires a bullet-by-bullet comparison rather than a word count.
- **`0045` is a new number for text that already existed.** It is a distinct new rule under
  CONTRACT §13.2, not a rename of `0025` or `0030`, both of which keep their tags and their own
  content. No ID is superseded by this proposal.
- **One large diff.** This is the largest single edit `/RULES.md` has had and it touches every
  rule, which makes review harder than a series of small ones. The disposition table and the
  full replacement text are both given so the change can be checked either way.

## Migration

1. Create `/shared/skills/change-discipline/` with `SKILL.md` under CONTRACT §10.2, holding the
   git-checkpoint and versioning procedure listed in the disposition table. Register it in the
   `/shared/skills/README.md` folder list and the shared-skill table in `/ONBOARDING_AGENT.md`.
2. Move the `0032` and `0037` detail into `/shared/skills/delegate-work/`, and the `0028` and
   `0033` detail into `/shared/skills/product-development/`, in each case checking first whether
   the skill already says it. Do not duplicate.
3. Replace the body of `/RULES.md` with the text above, keeping the front matter fields named
   there. The 29 em dashes are corrected by the replacement, satisfying **An en dash, never an em
   dash** for this file in the same commit.
4. Update `/ONBOARDING_AGENT.md` where it refers to rules by tag alone, so the index and the file
   agree on names.
5. Run the repository preflight validator and the duty comparison in Validation.
6. **Order, if more than one proposal is accepted.** Implement this restructure first, then
   `RULE-2026-0043`, then amendment A3 to `RULE-2026-0032`. Learning's supporting skills are built
   and reviewed before its rule is made active, so the rule never names a skill that does not yet
   carry its procedure.
7. **Review the final combined diff explicitly before committing, A3 included.** Replacing the
   whole root file is the one operation that can silently erase an amendment accepted between this
   proposal being written and being implemented. Read the diff for every rule, not just the ones
   this proposal set out to change, and confirm that any amendment accepted in the meantime is
   present in the replacement before it is written.

No change to `/CONTRACT.md`, protected schemas, `/BOOTSTRAP.md` or the preflight validator is
authorised here.

## Rollback

Do **not** restore a whole-file snapshot of `/RULES.md`. A snapshot would silently discard every
rule accepted or amended after this implementation, which is the same identity failure this
proposal exists to avoid.

Roll back rule by rule. For each of the 22 rules this proposal rewrote, restore its previous
wording from its own proposal record under `/projects/brain-development/proposals/`, which is the
canonical source for that rule's text. Leave untouched any rule accepted, amended or added since,
including `RULE-2026-0043` if it has landed. Then remove the `RULE-2026-0044` and `RULE-2026-0045`
sections, drop `0044` and `0045` from the tag list, restore `accepted_proposal`, and set this
proposal to `reverted`.

The restored file keeps the group structure or returns to a flat list, at the owner's choice; the
structure is not what a rollback is for. The skills keep the procedure they received, which is
harmless: it becomes detail repeating the restored rules rather than replacing them, and can be
trimmed separately.

No ID moved, so no other record needs correcting.

## Validation

- **Duty comparison, bullet by bullet.** For each of the 22 existing rules, every duty and every
  grant of authority in the current text has a counterpart in the new text or a named destination
  in the disposition table. This is the real check; the word counts are not.
- Repository preflight before and after reports the same result. Baseline at `04b448f`:
  **PASS, 0 errors, 4 warnings.**
- `grep -c "–" RULES.md` returns **`1`**, not `0`. The single remaining em dash is the character
  itself, quoted inside **An en dash, never an em dash**, which cannot state its rule without
  naming the mark it forbids. The earlier `0` in this section was wrong and would have failed.
- Read the replacement against the current file section by section, not by word count. The group
  heading lost in the first draft was twelve words and invisible to every numeric check.
- Every skill path named in the new text resolves to a directory containing a `SKILL.md`.
- Every rule name used in bold cross-reference matches a heading in the file exactly.
- The tag list in the header matches the tags actually present, read from the file rather than
  assumed. This is the error made and caught during the `RULE-2026-0042` implementation.
- No metadata anchor anywhere in the repository points into `/RULES.md`.

## Acceptance

**Question to ask:** 1. Accept `RULE-2026-0044` and `RULE-2026-0045` and the rewritten `/RULES.md`
as written (recommended); 2. accept the restructure, names, order and gap explanation, but leave
every rule body at its current length; 3. accept with wording changes to particular rules;
4. reject.

Not yet requested at the time of writing. Do not treat silence, adjacent approval or general
agreement as acceptance.

## Implementation record

Not implemented. This proposal is `proposed` only, and `/RULES.md` has not been changed.
