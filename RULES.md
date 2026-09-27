---
id: brain-root-rules
title: Brain Root Rules
type: rules
schema_version: 0.2
contract: /CONTRACT.md
scope: repository
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-28T08:36:50+10:00
owner: brain-owner
---

# Brain Root Rules

Read `/CONTRACT.md` first.

This file is the generic root-rule set: mechanisms any owner could adopt. Headings are the stable `SMART-RULE-NNNN` identifiers (CONTRACT §13.2, *Rule identifiers*). The `SMART-RULE` series also numbers the mechanics rules whose canonical wording lives in `/CONTRACT.md`, a shared skill or a shared template; they are indexed below and are not restated here. Rules in the owner layer `/memory/RULES.md` and in node `RULES.md` files carry their own `MEMORY-RULE` and `<PROJECT>-RULE` series.

Rules inherit `/CONTRACT.md` -> this file -> `/memory/RULES.md` (the owner layer, always read) -> node `RULES.md` files. "The owner" is the person named in `/memory/OWNER.md`.

`SMART-RULE` identifiers, in number order. The next new mechanics rule takes the number after the highest one listed here.

| ID | Rule | Canonical home |
|---|---|---|
| `SMART-RULE-0001` | Governance safety, bootstrap and preflight | `/CONTRACT.md` §1, §15 |
| `SMART-RULE-0002` | Protected governance | this file; `/CONTRACT.md` §13.2 |
| `SMART-RULE-0003` | Token-efficient operation | this file; formal task conversion in the task node's `RULES.md` (`/shared/templates/memory-skeleton/tasks/RULES.md`) |
| `SMART-RULE-0004` | Forward-looking rules and external target confirmation | `/CONTRACT.md` §5.6, §10.5 |
| `SMART-RULE-0005` | Internal-first then external lookup | this file |
| `SMART-RULE-0006` | Owner-facing shell includes cd | this file |
| `SMART-RULE-0007` | Portable behavioural rules only | this file |
| `SMART-RULE-0008` | No real data in sample data or shareable repositories | this file; `/shared/skills/repository-preflight/` |
| `SMART-RULE-0009` | Logical checkpoint commits | this file |
| `SMART-RULE-0010` | Communication efficiency | this file |
| `SMART-RULE-0011` | Raw evidence files are exempt from front-matter validation | `/CONTRACT.md` §8, §15; `/shared/skills/repository-preflight/` |
| `SMART-RULE-0012` | Plain-language summary when asking for governance acceptance | `/CONTRACT.md` §13.2 |
| `SMART-RULE-0013` | Per-API quirk knowledge base | this file |
| `SMART-RULE-0014` | Lightweight Git exit check | this file |
| `SMART-RULE-0015` | Reuse project-native UI patterns | this file |
| `SMART-RULE-0016` | Product-development process | this file; `/shared/skills/product-development/` |
| `SMART-RULE-0017` | Surface external-system configuration mismatches before coding around them | this file |
| `SMART-RULE-0018` | One canonical implementation, no duplicated side effects | this file |
| `SMART-RULE-0019` | Context handoff checkpoint | this file |
| `SMART-RULE-0020` | Whole-system implementation review | this file |
| `SMART-RULE-0021` | Security designed into every implementation | this file |
| `SMART-RULE-0022` | Tests demonstrate behaviour | this file |
| `SMART-RULE-0023` | Preflight resolves heading anchors in declared references | `/shared/skills/repository-preflight/` |
| `SMART-RULE-0024` | Delegated parallel work | this file; `/shared/skills/delegate-work/` |
| `SMART-RULE-0025` | Task state enumerates every open task | `/shared/templates/memory-skeleton/tasks/RULES.md`; `/shared/skills/repository-preflight/` |
| `SMART-RULE-0026` | Version every change, and show it | this file |
| `SMART-RULE-0027` | Every list has a deliberate order | this file |
| `SMART-RULE-0028` | Evidence-driven learning | this file; `/shared/skills/learning-maintenance/` |
| `SMART-RULE-0029` | Four layers: mechanics, skill library, memory and project repositories | `/CONTRACT.md` §3.4–§3.6 |
| `SMART-RULE-0030` | Rule identifiers | `/CONTRACT.md` §13.2 |
| `SMART-RULE-0031` | Show the text of every new or changed rule | this file |
| `SMART-RULE-0032` | Skill exchange | this file; `/shared/skills/skill-exchange/` |
| `SMART-RULE-0033` | A name means one thing, everywhere | this file |
| `SMART-RULE-0034` | Start from the latest | this file; `/shared/skills/repository-preflight/` |
| `SMART-RULE-0035` | Offer a board when a project outgrows the personal board | this file; `/shared/skills/owner-board/` |
| `SMART-RULE-0036` | Raise a rule that gets in the way | this file |
| `SMART-RULE-0037` | Size parallel work to the machine and the merge | this file; the machine's hardware and session footprint in `/memory/OWNER.md` |
| `SMART-RULE-0038` | One working copy per session | this file; `/shared/skills/repository-preflight/` |

## SMART-RULE-0010 – Communication efficiency

- In voice mode, when a clarifying question is required, ask one question at a time and wait for the answer before asking the next, unless the owner explicitly requests a grouped questionnaire. Outside voice mode, presenting a list of clarifying questions is acceptable-especially when scoping a software project. Do not invent questions when a safe default exists.
- Prefer a reversible default and proceed when multiple approaches are valid and the risk is low; state the chosen approach in one short line. Ask only for irreversible actions, secrets, material trade-offs, or when policy requires owner choice.
- Do not narrate process before acting ("I'll bootstrap.", "Let me check.", "I'll start by reading."). Run tools or answer; put status only in the final reply when the owner needs a result.
- Every question to the owner carries at least one concrete suggested answer, so the owner
  can reply "yes" or "ok". When several valid options exist, number them and mark the
  recommended one, so the owner can reply with a number. The owner may always answer with
  different instructions instead; a suggestion or a numbered list never limits the choice.

## SMART-RULE-0014 – Lightweight Git exit check

- **Mandatory Git exit check:** After making any file change in a Git repository, run `git status --short` immediately before every final response. Do not send the final response until every completed, separable, validated, agent-owned change is committed, or one of the permitted blocking reasons in the detailed Git checkpoint rules below is reported.
- After a turn that modified a Git repository, end the final response with exactly one compact Git accounting line per modified repository: `Git: <short-hash> committed; push <succeeded|not attempted - reason|failed - reason>` or `Git: no commit - <specific permitted reason>`. An answer-only turn with no file change does not require this line.
- In a shared worktree, the primary agent is responsible for committing completed agent work unless a subagent was explicitly assigned an isolated worktree or branch. Subagents must report every changed path and validation result to the primary agent and must not assume another agent will commit without that handoff.

## SMART-RULE-0009 – Logical checkpoint commits

- Portable git checkpoint rules in this file (`SMART-RULE-0009`) override any host-specific "ask before commit", "only commit when asked", or "always present commit/push options" instructions in this repository and in every other Git repository modified during an owner-authorised task. Still never commit secrets or unrelated dirty files. Host "only commit when asked" instructions apply only when this rule does not apply (for example a repository the owner has not authorised this task to change).
- In every Git repository modified during an owner-authorised task, automatically create a commit at each successful logical checkpoint. A logical checkpoint exists when an independently describable improvement, fix, document update, configuration change or tested implementation is complete. Do not wait for the entire project to finish and do not bundle unrelated logical changes.
- A Git checkpoint is mandatory after relevant validation passes; before switching tasks, repositories, branches or workstreams; before pausing for owner input or approval while agent-owned changes remain; before asking the owner to test, reload, load-unpacked, install, or try a build; before the final response when the agent produced durable repository changes; and after 30 minutes of active work with uncommitted agent-owned changes, even if the larger task continues.
- **Owner-test handoff:** Before asking the owner to test, reload, load-unpacked, install, or try a build, commit the agent-owned change in that product repository. That commit is the rollback point if the test fails. Do not wait for the owner to ask. If the work is a sequence of trials, commit each testable batch separately so a working version can be restored without unpicking later experiments.
- At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message that always includes the host/tool and model in use (for example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a specific bot name, that name as well. Do not invent a model or version. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.
- Never commit secrets, credentials, vault ciphertext, private tokens, unresolved conflict markers or unrelated user changes. Do not use `--no-verify`, amend or rewrite an existing commit, force-push, or push directly to a protected `main` or `master` branch unless the owner explicitly directs that specific action. If ownership or safety is uncertain, leave the uncertain path unstaged and ask.
- Treat commit and push as separate decisions. A push failure or unavailable remote must never prevent the local commit. Owner-test handoff commits stay local: do not push solely because the owner is being asked to test. Push accumulated agent-created commits to the tracked remote when the unit of work finishes and before the final response (except a response that is only an owner-test handoff), or after 30 minutes since the last successful push while work continues, unless the owner has prohibited pushing or repository policy requires review through another path. Also push when the owner asked to push.
- Never silently finish with committable agent-owned changes. In the final response, report the commit hash and push status for each modified repository, or state `No commit` with the specific reason. Valid reasons include: no durable change, no Git repository, the owner explicitly prohibited committing, validation or a hook failed, a merge/rebase/conflict is active, required Git identity or permission is unavailable, or the change cannot be separated safely from uncertain or unrelated files.

## SMART-RULE-0003 – Token-efficient operation

- Read and prompt with only the minimum context relevant to the current task; avoid loading unrelated files, restating unchanged context, or repeating information already available elsewhere.
- Structure nodes, files and skills so related content can be read independently in small, targeted pieces; split large or mixed-purpose files where that measurably improves token efficiency and response time.

## SMART-RULE-0008 – No real data in sample data or shareable repositories

- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data - including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
- **Shareable repositories are written clean, not cleaned.** Everything written into a shareable repository – the mechanics and the skill library: rules, skills, scripts, tests, templates, proposals and commit messages – is free of personal data from its first draft (CONTRACT §3.4). Say "the owner". Read concrete values – names, paths, accounts, identifiers, locations, project and client names – at run time from `/memory/OWNER.md` or `/memory/skills/<skill>/config/`, never inline. Write examples with fictional values: `example.com` addresses, numbers reserved for fiction, invented names.
- **Split a lesson as you write it.** When a rule or skill comes out of the owner's own incident, write the generalised mechanism in the shareable repository and the incident, with its real identifiers, in memory at the node that owns it, in the same piece of work. Never write one file to be split later.
- **The check confirms; it does not clean.** The validator runs the personal-data check on every shareable repository before each commit, and a hit fails it. Fix a hit at its source. Exempt a value only when it is genuinely public or generic – a vendor's published documentation, a documented default – and give the reason beside the exemption. When a writing habit or a template invited the hit, record it as a learning (`SMART-RULE-0028`).

## SMART-RULE-0015 – Reuse project-native UI patterns

- In every software or development project, before creating or styling a user-interface element,
  search the active project's code, components, styles and design-system assets for the same or
  closest existing element and interaction pattern.
- Equivalent elements must reuse or extend the project's existing component, design tokens,
  styling and behaviour so they remain visually and functionally aligned. Do not invent a
  parallel element style when a suitable project-native pattern already exists.
- If no suitable pattern exists, derive the new element from the project's established visual
  language and adjacent components. Make it reusable when the project is likely to need the same
  pattern again.
- Do not preserve a known accessibility, security or functional defect merely for visual
  consistency. Explicit owner requirements and supplied design references may override an
  existing pattern; when they do, integrate the change deliberately with the rest of the project.

## SMART-RULE-0002 / CONTRACT §13.2 – Protected governance

- Do not activate a protected governance change without the owner's explicit acceptance under Contract section 13.2.
- Report accepted governance changes with their proposal ID, exact changed files, effective contract version and validation result.
- Small additive or clarifying changes to an existing numbered rule amend that rule in place and keep its ID. Give a new identifier only to a distinct new rule, not to a tweak, extra sentence or tighter constraint on an existing one; it takes the next number in its layer when the owner accepts it (CONTRACT §13.2, *Rule identifiers*). Record the amendment on the original proposal record; do not supersede a live rule with a new number.

## SMART-RULE-0005 – Internal-first then external lookup

- When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge, and other already-known canonical homes) with a **targeted** search. Do not run exhaustive repository grep theatre to prove absence.
- If the fact is absent or still uncertain after that internal check, use the authoritative external shared skill when one exists or is mandated (for example ABR Web Services for Australian Business Numbers and GST registration). After a verified external result, update the relevant durable brain record when the fact belongs in the repository.
- Do not delegate work to explore/repo-only subagents when the answer requires vault credentials, Gmail, or an external API. Match agent capabilities to the job, or do the lookup in-session.
- When the owner redirects to a different path (skill, external system, email), abandon or stop parallel searches that the redirect made obsolete; do not finish a doomed explore pass "for completeness."

## SMART-RULE-0013 – Per-API quirk knowledge base

- Every `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, holding one small file per confirmed or hypothesised piece of non-obvious external-API behaviour for that system. Scaffold it (empty, plus one `_CONVENTION.md` copied from `/shared/templates/api-knowledge-convention.template.md`) whenever a new `<system>-access` skill is created. If a quirk worth logging is found for a system with no shared skill yet, create the minimal skill folder and its `knowledge/` scaffold first rather than leaving the finding without a canonical home.
- Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external API, search that system's `knowledge/` folder first - by filename convention (for example `Glob "business--*"` for one object type, `Glob "*--textbox-list--*"` for one field type across objects) and by frontmatter (`Grep` for `object_type:`, `field_type:`, `endpoint:` or `status:`) - before re-investigating from scratch. Treat a `refuted` entry as a warning against repeating that exact hypothesis; treat a `deprecated` entry as a pointer to its `superseded_by` replacement, not as current fact.
- After a fix or investigation resolves genuinely unexpected or undocumented external-API behaviour, write one entry under that system's `knowledge/` folder, copied from `/shared/templates/api-knowledge-entry.template.md`, named `<object_type>--<field_or_topic>--<short-slug>.md`, with `system`, `object_type`, `field_type`, `endpoint`, `status` and `source_refs` set. Do not create an entry for routine work that reveals nothing unexpected about the external API - this store is for quirks and workarounds, not a general changelog.
- Set a new entry's `status` to `pending` when the fix it documents relies on a hypothesis not yet independently confirmed; set `confirmed` only once a live probe or observed real subsequent use corroborates it. When later evidence contradicts a `pending` or `confirmed` entry, do not delete it: set `status: refuted` for a wrong hypothesis or `status: deprecated` for behaviour that has genuinely changed, add a one-line note of what changed and when, and set `superseded_by` or leave it for the correcting entry to backlink via `refuted_by` once one exists.
- Promote, refute or deprecate an existing entry opportunistically - the next time work touches that same quirk and turns up corroborating or contradicting evidence - rather than deferring it to a scheduled review that does not otherwise exist in this repository.

## SMART-RULE-0006 – Owner-facing shell includes cd

- Whenever giving the owner shell commands to run, always include an explicit `cd` (or equivalent) to the brain root named as `brain_root` in `/memory/OWNER.md` (or the active absolute working directory if the command must run elsewhere, such as the memory checkout or a project repository) before the command, so the owner does not have to locate the correct folder.

## SMART-RULE-0007 – Portable behavioural rules only

- Keep durable behavioural rules only in portable governance: `/CONTRACT.md`, root and node `RULES.md` files, and skill operating instructions. Do not create or maintain host-specific behavioural rule files that restate or extend how agents must behave.
- Host entry files may only point agents to portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`, `/AGENTS.md`, `/ONBOARDING_AGENT.md`) and must not carry independent behavioural policy.

## SMART-RULE-0016 – Product-development process

- Before starting or continuing a non-trivial discovery, design, implementation, release or lifecycle-investment increment for a software product or internal tool, follow this rule and use `/shared/skills/product-development/` as its implementation guide. Clearly non-material copy/formatting corrections, behaviour-preserving mechanical refactors and like-for-like bounded repairs use ordinary proportionate engineering discipline; a small reversible behavioural improvement may use the skill's compact light path.
- Establish whether the work is a new product, existing-product baseline, feature/change, urgent repair or lifecycle review; locate existing work at its current lifecycle position; reuse valid evidence; and reopen only the gates whose assumptions or downstream consequences are affected.
- Select light, standard or high-assurance depth from investment, uncertainty, reversibility, affected users, security/privacy exposure, operational criticality and consequence of failure. Always consider both internal-use and commercial routes, while scaling the research to their plausible value. A light change may be recorded compactly without reconstructing the full product lifecycle.
- The acting agent researches, tests, collects and presents the evidence and a recommendation for each applicable gate. The owner decides each gate unless an accepted active rule explicitly delegates that defined gate and risk class. Record the decision and the exact next investment it authorises.
- Maintain a canonical product-development record or equivalent project-native plan. At minimum, record lifecycle position, depth and its rationale, affected gate dispositions, evidence freshness, decisions and the exact next investment authorised; a compact entry is sufficient for a light change.
- At standard and high-assurance depth, use at least two distinct underlying AI models at material opportunity/build-versus-buy, design/delivery and release-readiness checkpoints when proportionate, available and permitted. Protect secrets and minimize personal, customer, security-sensitive and commercially sensitive context before review. Synthesize disagreements as evidence rather than votes. If distinct models are unavailable, disclose the limitation and do not claim that multi-model review occurred.
- The mandatory semantics are contained in this rule. `/shared/skills/product-development/` supplies operational detail and may not weaken these requirements or expand an agent's authority.

## SMART-RULE-0017 – Surface external-system configuration mismatches before coding around them

- When work against an external system reveals that its configuration is inconsistent with what
  the task needs – mismatched option sets, a missing or wrongly-typed field, a naming collision, a
  value that cannot be represented in the target – stop and put the finding to the owner before
  writing code that bridges it. State precisely what disagrees, what a fix in that system would
  be, and what the code workaround would otherwise cost.
- This overrides the "prefer a reversible default and proceed" guidance in `SMART-RULE-0010` for
  configuration mismatches specifically. The reason is not risk but economy: a change in the
  external system's own interface is frequently far cheaper than a translation layer, and the
  layer outlives the mismatch it was written for.
- Continue with every part of the task that does not depend on the answer, so the question arrives
  with the rest of the work already done rather than blocking it.
- This does not apply to genuine API behaviour that cannot be configured away – an endpoint's
  response shape, a required header, a status code. Absorb those in code and record them under
  `SMART-RULE-0013`.

## SMART-RULE-0018 – One canonical implementation, no duplicated side effects

- In every software or development project, before adding a function, write, call, or extra
  control-flow path, search the active project for an existing implementation that already performs
  the same job.
- Prefer one canonical implementation and call it. Do not copy a working sequence into a second
  place, wrap the old path while leaving it live, or add a new write that repeats an existing
  side effect (the same field, file, API call, or state change).
- When a new path replaces an old one, remove the superseded code in the same change: leftover
  writers, leftover callers, and any second frontend or backend trip that only existed to do the
  same work.
- Extract a shared helper only when two or more live call sites need the same behaviour. Do not
  add an abstraction for a single use, and do not keep both the helper and the inlined original.
- Lean code means fewer live paths, not denser cleverness. Delete dead code. Do not preserve a
  known duplicate "for safety" when the remaining path already covers the cases.
- Distinct later stages may write the same field only when that stage has a different meaning
  (for example a later workflow step that must refresh it). Do not treat a second write at the
  same stage as a backup.

## SMART-RULE-0019 – Context handoff checkpoint

- Write a handoff checkpoint before context runs out, and prefer a **stage boundary** to a
  context threshold: the best moment is immediately after a validated, committed increment and
  **before** starting a new stage of work, because that is when the repository and the agent's
  understanding agree. Take the checkpoint at whichever comes first – the natural boundary, or
  roughly the last fifth of the context window.
- Never begin a new stage of work when the remaining context is unlikely to carry it to a
  committed, validated state. Checkpoint and say so instead.
- A checkpoint updates, in the owning node: `STATE.md` with the current position, what is in
  flight, what is uncommitted and where, and the exact next action; `KNOWLEDGE.md` with durable
  facts a later session could not re-derive cheaply – especially external-system behaviour
  established by experiment; `LOG.md` with what happened and why; and `/memory/tasks/` for anything
  outstanding.
- Record **open questions with enough context to act on them**, not just their titles: what is
  unknown, what was already tried, and what would settle it.
- Record **negative findings**. What was ruled out, and the evidence that ruled it out, is as
  valuable as what worked and is never recoverable from code.
- Distinguish what is **verified** from what is **assumed or unverified**, and name where
  uncommitted work lives when it is outside this repository.
- A checkpoint must not present unfinished work as finished. Report the actual state, including
  failures, blocked steps and anything skipped.
- A checkpoint ends with **one handover prompt** for the next thread, and it is a pointer,
  not a summary: the bootstrap files to read, the owning node's `STATE.md` whose `## Handover`
  section holds the position, and the single next action. Ten lines at most; nothing in it
  that a file already says. Everything the successor needs – runs and workers with their
  packets, branches and pending results, builds and where the owner loaded them, owner steps
  outstanding, decisions still open, the reminder that a worker's completion notice reaches
  only the thread that launched it – lives under `## Handover` in the owning node's `STATE.md`
  (and, for work spanning nodes, one line per other node pointing at its own `## Handover`),
  written before the prompt and kept current at every checkpoint. Write the prompt under
  `## Handover prompt` in the same `STATE.md` and repeat it as the last section of the final
  reply. The `## Handover` of `/memory/projects/brain-development/STATE.md` also names the **active
  conductor** (session title and the time it took over) and the other live sessions it knows
  of; a new thread that finds an active conductor asks the owner which thread continues
  before dispatching anything. Take the checkpoint whenever the remaining context is unlikely
  to carry the next stage, and at any natural handover where a fresh thread would work more
  efficiently.
- The active-conductor question is not required for at most one bounded, read-only learning or public-research worker per thread under SMART-RULE-0028, within SMART-RULE-0024’s delegation budget. Workers use no credentials, take no external side effects and write only their separate result artifacts. This exception grants no product-editing, merging or canonical-integration authority.
- Finish with the Git exit check under `SMART-RULE-0014`, so the handoff and the tree agree.

## SMART-RULE-0020 – Whole-system implementation review

- In every software or development project, optimise each change for the health of the whole
  system, not only for completing the immediate task. Evaluate it against upstream and downstream
  code, shared services, data models, APIs, workflows, state transitions and integrations.
- Before introducing a new pattern, abstraction, service, dependency or data flow, check how the
  project already solves the same problem and reuse or extend that approach where it remains
  appropriate. When a new approach is genuinely required, state the reason in the change and
  say whether existing related implementations should later converge on it.
- Leave the architecture simpler after the change, or at minimum no more complex than the
  requirement demands. Prefer the smallest clear implementation that fully satisfies it.
- When a requirement conflicts with an existing architectural, product or data-model decision,
  surface the conflict to the owner and resolve it deliberately. Do not quietly create an
  exception. This extends `SMART-RULE-0017` from external configuration to decisions inside the
  codebase.
- When a workaround or compromise is unavoidable, make it visible in the code and the project
  record, and state what would be required to remove it.
- Keep code understandable to another capable engineer or agent without reconstructing hidden
  assumptions: explicit data flows, clear responsibilities, predictable naming, straightforward
  control flow, focused modules. Do not use cleverness where a simpler implementation gives the
  same result.
- Before reporting a non-trivial change complete, review it from the perspective of the whole
  repository and state, briefly, the answers to: Does it follow the strongest existing pattern
  for this problem? Has it introduced a second way of doing something that already has one? Does
  it conflict with an architectural, product or data-model decision elsewhere? Can any obsolete
  code now be removed? Has it made the system easier or harder to maintain? Clearly non-material
  changes as defined in `SMART-RULE-0016` may skip this review.

## SMART-RULE-0021 – Security designed into every implementation

- In every software or development project, treat security, privacy and access control as part
  of the implementation, not a later review step. For each change that touches an endpoint,
  a query, a permission, stored or transmitted data, an integration or a log, consider:
  authentication, authorisation, tenant and account isolation, input validation and output
  encoding, secrets and credential handling, sensitive data in responses and logs, API
  permissions and scopes, and what the code does when a check fails.
- Apply least privilege. Request, store, transmit and expose the minimum sensitive data and the
  narrowest scopes the requirement needs.
- Do not rely on UI restrictions for security. Enforce important rules server-side at the
  trust boundary that owns them.
- Fail closed. When identity, tenant, scope or a required mapping is uncertain, stop the
  operation and report, rather than proceeding with a guess or a default.
- Scope every query, write and external call by the tenant, account or location it belongs to.
  Do not let a request for one tenant read or change another's data through a missing filter or
  an inferred identifier.
- Never log or return secrets, tokens, credentials or more personal data than the caller is
  entitled to. Treat a leaked identifier that grants access as a credential.
- When a change materially widens an externally reachable surface, adds an authentication or
  payment path, or handles sensitive data for the first time, escalate to at least standard depth
  under `SMART-RULE-0016` and say so in the change.

## SMART-RULE-0022 – Tests demonstrate behaviour

- In every software or development project, tests must prove that the required behaviour
  works, not merely exercise the implementation. For each change, identify the important
  behaviours, invariants, boundary cases and failure conditions first, then make sure tests
  cover them.
- When fixing a bug, add a test that would have failed before the fix, wherever practical. If it
  is not practical, say so in the change and why.
- Include negative and boundary cases where they materially affect correctness: the empty input,
  the missing permission, the second tenant, the failed external call.
- Prefer tests that remain valid if the internal implementation changes. Assert on observable
  behaviour and outputs, not on private structure or call sequences.
- Do not report an existing green suite as evidence for new or changed behaviour unless a test
  actually asserts that behaviour. State what the tests prove and what they do not.
- Fixture and sample data remain subject to `SMART-RULE-0008`: entirely fictional.
- Proportion applies. Clearly non-material changes as defined in `SMART-RULE-0016` need no new
  test; a behavioural change always does.

## SMART-RULE-0024 – Delegated parallel work

- Delegate to another agent only work that is independent, bounded and consumable as a
  compressed result: one clear outcome, no back-and-forth with sibling workers, and a result
  the conductor can use without the worker's reasoning. Before dispatching, state in one line
  why parallel workers beat doing the work in sequence. Tightly coupled reasoning, sequential
  implementation and work that needs constant shared state stay with one agent.
- Delegate through `/shared/skills/delegate-work/`: a work packet that references canonical
  files rather than copying prose, and a result record the worker writes back. Packets and
  results are ephemeral instrumentation under `/temp/delegation/`, not task records. Work that
  must outlive the session is an ordinary `/memory/tasks/` record with `waiting_on` and `next_review`.
- Workers start isolated by default. A packet that forks the conductor's context states why.
- Workers do not commit, and do not write the files every task shares – logs, state, task lists,
  indexes, version fields, build output. A worker writes only the paths its packet names, in the
  conductor's copy and branch (`SMART-RULE-0038`), and returns findings, artifacts inside its run
  folder, and every changed path with its validation result. The conductor keeps the paths of one
  run disjoint, reviews each worker's diff before staging it, and commits and reports. A worker
  whose work cannot be kept apart – it builds or tests code, it must change a file another worker
  also changes, or it is one of several alternative attempts – works in its own worktree, branched
  from the conductor's branch; the conductor merges it back (`SMART-RULE-0014`).
- Workers use no credentials and take no external side effect unless the packet names a target
  the owner confirmed for this operation under CONTRACT §10.5. The default is none. A worker
  that needs an owner decision stops with status `blocked` and the question; it does not guess.
- Budget: depth one (workers do not delegate) and at most four workers per run, until a
  measured trial recorded under `/memory/projects/brain-development/` justifies more.
- The conductor routes each result under CONTRACT §5 and §6, treats worker claims as
  unverified until checked, writes one `LOG.md` entry per run in the owning node, and does the
  Git accounting under `SMART-RULE-0014`. Never claim parallel execution on a host that ran
  packets in sequence. Record the host and the model that actually ran each packet; never
  invent one.

## SMART-RULE-0026 – Version every change, and show it

- Every software or development project carries one version of three numbers,
  `first.middle.last`, kept in the project's own version field (`package.json`,
  `manifest.json`, `pyproject.toml` or the equivalent) and nowhere else. Each logical change
  that reaches a build a person can load, run or deploy bumps exactly one number in the same
  commit, chosen by these tests, taking the highest that applies:
  - **First number, breaking.** After the change, something that worked before no longer
    works the same way without action by someone: stored data needs a migration or is read
    differently, an interface that others call or read changes its shape or meaning, or a
    procedure a person follows changes its steps. Bumping the first number resets the other
    two. While a product is still in development its version stays below `1.0.0`, and a
    breaking change there bumps the **middle** number instead: nothing outside the team
    depends on it yet, so the first number would say nothing a reader could use. `1.0.0` is
    set once, deliberately, when the owner declares the product released, and from that
    version on the first number follows the test above. A breaking change before `1.0.0` is
    still named as breaking in its commit message and in the node's `LOG.md`, so the history
    says what changed even where the number does not.
  - **Middle number, feature.** A person can see or do something they could not before, or
    something visible behaves differently on purpose without breaking what depended on it: a
    new view, a new setting, a new record kind, a changed layout. Resets the last number.
  - **Last number, small change.** Everything else: a fix, a wording change, a refactor, a
    performance or reliability change, a test-only or build-only change that ships in the
    product. Nothing a person relied on changes.
  When one commit carries changes at several levels, bump the highest once.
- Every build embeds the version together with the commit it was built from, the build time
  and, when not on the main branch, the branch name; a build from a tree with uncommitted
  changes is marked as such. This build identity is shown where a person looks first: an
  extension's popup and its browser card, a page's footer, a service's health or about
  endpoint, a CLI's `--version`. The version is what is shown; the commit, build time and branch are one step away in every
  environment: a tooltip on the version, an about panel, the extensions card, a health
  endpoint's body or a `--version --verbose` flag.
- A test in the project's check fails when a commit changes the product without changing the
  version, so a change cannot reach a build unnumbered. Commit messages, task records and log
  entries that describe a change name the version it lands in.
- When asking the owner to reload, test or deploy, state the version and build identity they
  should see, so a stale build is recognised at a glance.

## SMART-RULE-0027 – Every list has a deliberate order

- Every list a person reads is put in an order chosen for that reader, never left in the
  order it was produced: the options of a dropdown, the rows of a table, the sections of a
  report, the findings of a check, the bullets of a reply, the entries of an index. Insertion
  order, capture order, map order and API order are not orders; they are accidents.
- The default is alphabetical by the label the reader sees, with numbers inside labels
  compared as numbers, so `1.2` precedes `1.10`. Another order replaces it only when the
  reader is better served by it, and the code or the document says so in a comment or a
  line: by time when the reader follows a sequence, by severity or priority when they act
  on the worst first, by frequency or size when the largest matters most, by a fixed
  domain order when one exists, such as the stages of a pipeline. The chosen order holds
  across renders and captures, so two views of the same data list it the same way.
- A list shows what the reader can use. Items that cannot be used from that list, such as a
  draft where only published items act, are left out or set apart under their own label,
  and the code says which.
- Reviews of a deliverable check its lists: an unordered list is a defect, not a style
  choice.

## SMART-RULE-0028 – Evidence-driven learning

- **Keep the owner’s work first.** At task entry, check the compact learning index for relevant pending work. Do not load the learning corpus. Maintenance runs as bounded background work; when unavailable, leave it pending for a later session. Never claim background execution that did not occur.
- **Try, observe and capture.** Within existing safeguards, prefer bounded experimentation when appropriate. At natural checkpoints, capture useful discoveries, failures, recurring errors, negative findings, owner corrections, preferences and decisions without waiting for a reminder. Update an existing record rather than duplicate it. Routine activity needs no learning record.
- **Keep knowledge with its subject.** Each learning has one canonical home in the owning subject’s knowledge store or `data/learnings/`; other projects reference it. Record the observation, supporting evidence, applicability, assumptions, proposed response and unresolved questions. Keep provisional claims out of established `KNOWLEDGE.md`.
- **Search before repeating.** When something unexpected happens, an approach repeatedly fails, evidence conflicts or progress is blocked, use `/shared/skills/problem-recovery/` to search relevant brain knowledge before reinvestigating. Check the relevant API quirks when applicable. Bound recovery effort across the problem; a failed attempt may lead to research, a materially different hypothesis or a pending investigation.
- **Bring in external evidence.** After meaningful implementation or investigation, including successful work, research external experience proportionately to improve the learning. This is not a routine prerequisite to experimentation. Distinguish source recommendations from locally verified outcomes and preserve provenance. Six Thinking Hats remains optional.
- **Cross-check opportunistically.** Later sessions review eligible pending learning. Record the originating and reviewing models when known. Same-model and unknown-model reviews remain useful but do not count as independent-model review. Evidence status and review status are separate: model agreement alone never confirms an empirical claim. Investigate disagreements and their assumptions.
- **Maintain and forget deliberately.** Agents may reversibly deduplicate, repair, narrow, refute, supersede or withdraw ordinary learning from routine retrieval when evidence supports it. Preserve history and valid exceptions. Age and frequency guide investigation but do not establish truth or justify retirement alone. Validate significant retirement by testing both non-use of obsolete advice and continued access to valid exceptions. Protected governance, owner decisions and raw evidence remain outside this maintenance authority.
- **Learn from use and owner input.** Distinguish retrieval from application, and usefulness from truth. Record helpful, ineffective, harmful or unknown outcomes with their evidence basis. Preserve owner feedback and classify it as preference, decision, usefulness assessment or factual observation. Apply it within its stated scope; investigate factual contradictions.
- **Interrupt only when needed.** Contact the owner when authority is required, a consequential trade-off needs judgement, uncertainty about their goals blocks a useful decision, or a finding materially affects current work. Failure or disagreement alone is not an escalation trigger. Ordinary maintenance stays silent.
- **Present a weekly review.** When due during an active session, present new learning and substantive changes since the previous delivered review, including retirements and uncertainty. Track delivery; label a possible repeat after uncertain delivery. Presentation is not acceptance of proposed governance changes.
- **One writer at a time, not one writer for all time.** Background workers return findings and do not edit canonical learning or shared views; the thread that launched a worker validates and integrates its results. Any session may integrate, and while it writes it must be the only writer: exclusion lasts for the write and never outlives the session holding it, so no designation goes stale and no work waits on a session that has ended. Re-read the target inside that window, stage only its own paths, and treat a Git conflict as the signal to reconcile rather than overwrite. Generated views are derived from the records and are regenerated after integration, never edited as source. `/shared/skills/learning-maintenance/` implements this process without expanding its authority.

## SMART-RULE-0031 – Show the text of every new or changed rule

- Whenever an agent proposes, amends, accepts or applies a rule at any level (the contract,
  `/RULES.md`, `/memory/RULES.md`, a node's `RULES.md` or a skill's operating rules), the reply
  to the owner quotes the rule's full text – its heading and every bullet, or the exact
  before-and-after for an amendment – before the file path. A summary may accompany the text but
  never replaces it.

## SMART-RULE-0032 – Skill exchange

- **Notice and suggest.** When a node-local capability is used or copied by a second node, holds no owner data once its configuration is moved out, or wraps a system other owners use, record it as a promotion candidate and suggest promoting it to a library skill at the next natural checkpoint. Procedure: `/shared/skills/skill-exchange/`.
- **Clean before it leaves memory.** Nothing moves from `/memory/` to a shareable repository (the mechanics or the skill library), or from a shareable repository to any other repository, until the personal-data check reports no hits (`SMART-RULE-0008`, CONTRACT §3.4).
- **Offer, never push.** A contribution to an upstream repository is a pull request from the owner's own repository, carrying a proposal file without a rule number, the personal-data check's result and passing tests, opened only after the owner says yes to that contribution.
- **Hear upstream on a cadence.** At session start, when a check is due (default every seven days), fetch `upstream` and tell the owner what changed in their `active_skills`, the core skills, governance and new skills. Merging is the owner's decision; an upstream change to protected governance is presented as a proposal (CONTRACT §13.2).
- **Record provenance.** A skill installed from another brain or library is read in full before it runs, and its source repository and commit are recorded in `/memory/skills/installed.json`.
- **Suggest at checkpoints, once.** Suggestions are batched at natural checkpoints (session start, end of a unit of work, the weekly review), numbered with a recommendation, capped, and not repeated after a decline unless new evidence arrives. The owner may set them to weekly or off. A security fix to a skill the owner uses is the one exception and is reported at the next response.

## SMART-RULE-0033 – A name means one thing, everywhere

- One thing has one name, and that name is the same in the interface, the code, the stored data, the specification and the conversation. A field called `Type` on screen is `type` in its key, its constants and its helpers. Where a name must differ, because something outside the brain fixes it, the code says in one line why and where the translation happens.
- A name says what the thing is, in the domain's own words, at the length that makes it unambiguous. Names in one set are built the same way, so a reader who learns one can guess the rest.
- A name is corrected while it is cheap. The moment a rename costs only a delete and a rebuild is the moment to do it; once data, integrations or habits carry the old name, the same fix needs a migration. Renaming is not deferred to a tidy-up that never comes.
- An agent given a name that will not hold – one that means something else in the same system, one that will read as wrong to the next person, one inconsistent with the names around it – says so before building on it, proposes the better name and the reason, and proceeds on the owner's answer. This is not a veto: the owner may keep their word, and the agent then uses it consistently everywhere.

## SMART-RULE-0034 – Start from the latest

- At the start of a session, before reading state or changing anything, bring every brain repository on this computer up to date with its `origin`: the mechanics, the skill library and the memory, and a project repository before working in it. Fetch; when the local branch is only behind, fast-forward it. `python shared/skills/repository-preflight/scripts/sync.py` does this for all of them (`--also <repo>` for a project repository).
- When a repository has uncommitted changes, or has commits of its own that `origin` does not (the history has diverged), change nothing in it and tell the owner what differs before starting work there.
- Never rewrite history or force a push to make a pull work. Diverged history is merged, and when files conflict, only after the owner says how.
- A computer that cannot reach `origin` says so, and works on only after the owner agrees.
- Push at the end of each unit of work (`SMART-RULE-0009`), so the next computer starts from it.

## SMART-RULE-0035 – Offer a board when a project outgrows the personal board

- When a project with no board of its own gains its fifth open task, or its work runs on three or more branches at once, the agent asks the owner once whether to give it a board. The question names the project, counts its open tasks, and suggests an answer.
- The board build (`build_boards.py`) prints the same suggestion for any project over that threshold, so the check does not rely on memory.
- A "no" is recorded in the board configuration (`board_declined`) and the agent does not ask again unless the owner raises it.
- A board is created only after a "yes": the agent registers it in `boards.json`, rebuilds the boards and gives the owner the link.

## SMART-RULE-0036 – Raise a rule that gets in the way

- When a rule blocks work that serves the owner's goals, or two rules conflict, the agent stops and puts it to the owner: the rule, what it blocks, the options and a recommendation. It never works around a rule quietly, in words or in code; changing what a validator accepts is changing a rule.
- Rules exist to support good outcomes. A rule that hinders them is changed deliberately, through a proposal the owner accepts (CONTRACT §13.2), not bent case by case.
- Continue with every part of the task the question does not block, so it arrives with the rest of the work done.

## SMART-RULE-0037 – Size parallel work to the machine and the merge

- The number of agent sessions or workers run at once is worked out for each batch, never fixed: the lower of what the machine can carry and what the conductor can merge back.
- **What the machine can carry:** measure free memory before any worker starts (the baseline), keep back 20 % of it for the owner's own work (at least 300 MB), and divide the rest by the measured memory one session actually costs, taken as the drop in free memory per running session including its child processes. Allow at most one session per two logical processors, and always at least one, with a warning when even one is tight. Before starting each further session, start it only when free memory stays above the kept-back margin plus one session's cost and the system memory load is below 90 %; otherwise wait for a running one to finish. Record the measured cost with the machine's hardware in `/memory/OWNER.md` and re-measure it after each batch.
- **What the conductor can merge back:**
  - Workers that only return results (read-only research, isolated test runs) add nothing to merge, so only the machine limits them.
  - Workers that change files count against the conductor's integration budget in `SMART-RULE-0024`, which is raised only by a measured trial.
- When the owner asks for more than this allows, the agent says so before starting, with the figures and the number it would use, and proceeds only on the owner's answer.
- When the hardware or the footprint is not recorded for the computer in use, the agent reads and records it before any parallel work.

## SMART-RULE-0038 – One working copy per session

- A session that will write to a brain repository works in its own working copy of the brain,
  never in the shared checkout: a Git worktree of the mechanics, the skill library and the memory,
  each on its own branch made from the latest `origin`, nested as the brain is, so the brain root
  and `/memory/` resolve inside it. `python shared/skills/repository-preflight/scripts/session.py
  start <name>` makes it and prints its path; the session reads and writes only there. A session
  that only reads may use the shared checkout.
- Inside a session copy, the copy is the brain root: an agent bootstraps from the copy's
  `/CONTRACT.md` and reads and writes the copy's files, never the shared checkout's by absolute
  path. A location hint that names the shared checkout (a host pointer file, `brain_root` in
  `/memory/OWNER.md`) is satisfied by a copy of the same repositories and is not a competing
  contract (CONTRACT §1).
- Claim work, not files. What a session is doing is recorded on the task it serves, never as a
  lock or a list of files. Overlap between sessions is found when their work is merged, where Git
  shows it as a conflict.
- Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with
  `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared
  checkout. `session.py finish` does this and removes the worktrees once their branches are
  merged. A conflict is reconciled, never overwritten: a generated file (a board, an index, a
  task list) is taken from `main` and rebuilt by its generator; an append-only log keeps both
  entries; any other conflict whose right resolution is not obvious from the two changes goes to
  the owner.
- The shared checkout holds only merged work. It is where the owner reads and runs things, it is
  fast-forwarded under `SMART-RULE-0034`, and no session leaves uncommitted changes in it.
- A session's delegated workers share its copy and branch by default. Each packet names the paths
  its worker may change (`writes: paths`); the conductor keeps them disjoint across the run and
  keeps shared files – logs, state, task lists, indexes, version fields, build output – for
  itself. Only the conductor stages and commits. A worker gets its own worktree, branched from the
  session's branch and merged back by the conductor, only when its work cannot be kept apart: it
  builds or tests code, it must change a file another worker also changes, or it is one of
  several alternative attempts.
- A host that cannot work in a separate folder says so at the start, works in the shared
  checkout, re-reads each file immediately before changing it, and stages only its own paths.

## Contract restatements

These restatements of `/CONTRACT.md` keep no separate rule identifier. Find the canonical wording in the contract section named here.

- Use repository-root paths in metadata and cross-references. (CONTRACT §8 / §12)
- Use one canonical home for every durable item. (CONTRACT §3.3)
- Prefer links and dependencies over copies. (CONTRACT §3.3 / §12)
- Keep metadata minimal, explicit and useful. (CONTRACT §8.4)
- Preserve raw files unchanged. (CONTRACT §11.1)
- Create Markdown source records for raw files. (CONTRACT §11.2)
- Treat `/memory/tasks/` as the canonical task system. (CONTRACT §9)
- Use shared skills for reusable capabilities. (CONTRACT §10.1)
- Keep project-specific configuration inside the project, and owner-wide skill configuration in `/memory/skills/<skill>/`. (CONTRACT §3.5 / §10.1)
- Keep personal data out of the mechanics repository; it belongs in `/memory/`. (CONTRACT §3.4)
- Record meaningful state changes and decisions. (CONTRACT §4 / §5)
- Use ISO 8601 timestamps with seconds and an explicit timezone for `created`, `updated`, and log entry headings; never use date-only values for them. (CONTRACT §8.2)
- Do not store secrets in the repository. (CONTRACT §10.3)
