---
id: brain-rules-software
title: Rule pack: software
type: generated_core
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-29T08:00:00+10:00
updated: 2026-11-26T15:48:16+10:00
owner: brain-owner
generated_by: /shared/skills/repository-preflight/scripts/core.py
canonical_sources:
  - /CONTRACT.md
  - /RULES.md
---

# Rule pack: software

Generated from `/RULES.md` by `core.py build`; never edit it here. It holds, verbatim, the rules of one
situation, so that they are read together. Each rule's canonical home stays `/RULES.md`.

Read the whole file before: building or changing software in any project: code, a user interface, tests, sample data, a version, or a change someone who uses the system would notice.

| ID | Rule | Canonical home | Applies when |
|---|---|---|---|
| `SMART-RULE-0008` | No real data in sample data or shareable repositories | this file; `/shared/skills/repository-preflight/` | writing sample, seed or fixture data, or anything in the mechanics or the skill library |
| `SMART-RULE-0015` | Reuse project-native UI patterns | this file | creating or styling a user-interface element |
| `SMART-RULE-0018` | One canonical implementation, no duplicated side effects | this file | adding a function, write, call or control-flow path in software |
| `SMART-RULE-0020` | Whole-system implementation review | this file | before reporting a non-trivial software change complete |
| `SMART-RULE-0021` | Security designed into every implementation | this file | a software change touches an endpoint, query, permission, stored or sent data, an integration or a log; before writing to a client's live system |
| `SMART-RULE-0022` | Tests demonstrate behaviour | this file | a behavioural software change or a bug fix |
| `SMART-RULE-0026` | Version every change, and show it | this file | a software change that reaches a build someone can load, run or deploy |
| `SMART-RULE-0041` | Code files stay small | this file; `/shared/skills/code-map/` | creating, growing or splitting a code file |
| `SMART-RULE-0046` | A release note for every change a user would notice | this file; `/shared/skills/release-notes/` | starting, committing or releasing a change someone who uses the system would notice |

## SMART-RULE-0008 – No real data in sample data or shareable repositories

- Mock, sample, seed, fixture and placeholder data (in any project, coded or otherwise) must be entirely fictional: invented names, addresses, companies and identifiers only. Never copy or adapt real customer, employee, or business data into mock/sample data - including data merely seen in another file, project or filename while working, even unintentionally. When realistic-looking sample data is needed, invent it fresh and do not reuse strings noticed elsewhere in the same session.
- **Shareable repositories are written clean, not cleaned.** Everything written into a shareable repository – the mechanics and the skill library: rules, skills, scripts, tests, templates, proposals and commit messages – is free of personal data from its first draft (CONTRACT §3.4). Say "the owner". Read concrete values – names, paths, accounts, identifiers, locations, project and client names – at run time from `/memory/OWNER.md` or `/memory/skills/<skill>/config/`, never inline. Write examples with fictional values: `example.com` addresses, numbers reserved for fiction, invented names.
- **Split a lesson as you write it.** When a rule or skill comes out of the owner's own incident, write the generalised mechanism in the shareable repository and the incident, with its real identifiers, in memory at the node that owns it, in the same piece of work. Never write one file to be split later.
- **The check confirms; it does not clean.** The validator runs the personal-data check on every shareable repository before each commit, and a hit fails it. Fix a hit at its source. Exempt a value only when it is genuinely public or generic – a vendor's published documentation, a documented default – and give the reason beside the exemption. When a writing habit or a template invited the hit, record it as a learning (`SMART-RULE-0028`).
- **Fixture numbers are chosen to pass from the start.** A run of nine or more digits, such as a ten-digit epoch-second timestamp, reads as a telephone number. In fixtures, choose such values so their digits contain the run reserved for fiction, `55501` (for example `1755501000`), when the fixture is first written, and derive every expected result from them. A hit found later is fixed by whoever wrote the tests, keeping their ordering and range assertions true, never by a blanket swap of values.
- **A memory node is not named after a library skill.** The check reads the folder name of every memory project node as an owner term. Give a new memory project node a name that no skill in the library has, or the skill's own name becomes a hit in the library and its commit is refused.

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

## SMART-RULE-0018 – One canonical implementation, no duplicated side effects

- In every software or development project, before adding a function, write, call, or extra
  control-flow path, search the active project for an existing implementation that already performs
  the same job. Before building a tool, or telling the owner that none exists, search the brain's
  skills (`/shared/skills/`, `/library/skills/`, their scripts and knowledge) and the log of the
  node that owns the subject.
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
- Before an agent writes to a client's live external system – its records, configuration or
  structure, directly or by running code that writes – get the owner's explicit approval for
  that write, naming the system and the target account or location (CONTRACT §10.5). An account
  the project's own rules name as a test or sandbox account is not live.
- Never log or return secrets, tokens, credentials or more personal data than the caller is
  entitled to. Treat a leaked identifier that grants access as a credential.
- Keep credentials out of every tracked file, including application configuration such as
  settings, company or fixture files; load them from the environment or a secret manager at run
  time. A credential that reaches Git history is rotated at its issuer, not only deleted from
  the file.
- When a change materially widens an externally reachable surface, adds an authentication or
  payment path, or handles sensitive data for the first time, escalate to at least standard depth
  under `SMART-RULE-0016` and say so in the change.
- **List the whole surface before the first review.** Work that guards something (credentials,
  money, personal data, permissions) produces, before its first code review, a list of every path
  that reads, writes, spends or copies the guarded thing, and a test that fails when the code
  gains a path the list does not name. The reviewer is given the list and asked what is missing
  from it. A finding of one more path is answered by completing the list, not by closing that
  path alone.

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
- Proportion applies. Clearly non-material changes as defined in `SMART-RULE-0016` need no new
  test; a behavioural change always does.
- **Run it for real before trusting the tests.** When a change has more than one process, or meets
  the operating system or another program (a background service, a keychain, a pipe, a file lock,
  a scheduler, a working tree another tool rewrites), the first thing built is a thin end-to-end
  run with real processes and throwaway data, kept as a script that can be run again. It is run
  before the first review and after every fix that touches such a boundary. A test that stands in
  for a boundary with a fake proves the logic on each side, never that the two sides meet: a
  passing suite is not reported as evidence that the parts work together until that run has
  passed. The run keeps itself away from live data, refuses to start when it cannot prove that,
  and proves its own clean-up.

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
    two. Until the owner declares the product released, its version stays below `1.0.0` and
    a breaking change bumps the **middle** number instead; it is still named as breaking in
    its commit message and in the node's `LOG.md`. `1.0.0` is set once, deliberately, and
    from that version on the first number follows the test above.
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

## SMART-RULE-0041 – Code files stay small

- A code file has at most 800 lines. Code files are those the code map counts by extension:
  JavaScript and TypeScript, Vue and Svelte, Python, shell and PowerShell, PHP, Go, Ruby, C#,
  Java, Kotlin, Swift, Rust, EJS templates and SQL. Generated, vendored, minified, migration,
  seeder and fixture files are exempt. Markdown, data and configuration files are not code files.
- A repository adopts the limit by recording every code file already over it, with its size, in
  `code-map/sizes.json` (`code-map record --adopt`). A recorded file may not grow. When it
  shrinks, its record is lowered in the same commit, and it leaves the record once it is within
  the limit. A new code file over the limit is split, never recorded.
- The limit is checked where every change to the repository is checked – its test suite, CI or
  validator – not only by a tool on one machine. The code map's `size` check and a test that
  reads the same record are equivalent.
- A file is shortened by moving whole parts of it into new files, without changing behaviour, in
  commits of their own; splitting a large file is a planned task. Squeezing lines, joining
  statements or deleting comments to pass the check is not shortening.
- Until a repository's own checks enforce the limit, its state names the task that will add
  them, and no change there makes an oversized file larger.

## SMART-RULE-0046 – A release note for every change a user would notice

- A release note records one change that someone who uses the system – the team, customers, or a colleague working in a platform the brain builds in – would see, do, receive or need to watch for differently. It is written from their side, in their words, with no code terms. Commits and their messages stay the developer's record and are not release notes.
- One note per user-visible outcome, never per commit. The agent opens the note when the work
  starts and names it in each commit that belongs to it (`Release-note: <slug>` trailer). A later
  commit that changes what a note says updates the note in the same commit. Refactors, tests,
  tooling and fixes no user could have met get no note; a commit that needs none but would
  otherwise be listed as missing one goes in `release-notes/not-user-visible.txt`.
- Every version that raises the first or middle number (`SMART-RULE-0026`) names at least one note
  in its commits. The project checks this on every push to its development branch, not only on
  pull requests: a push with a feature version that names no note, or names one that does not
  exist, fails.
- A note's `commits` and `versions` are generated from the trailers by
  `/shared/skills/release-notes/` (`release_notes.py link`), never kept by hand.
- A note's `kind` is one of `added`, `changed`, `fixed` or `removed`, and its other fields follow
  the release-notes skill; the project's check refuses anything else.
- Code notes live in the project repository under `release-notes/unreleased/`. Notes for changes
  made in a no-code platform come from that platform's export where a tool provides one, or are
  written by hand in the owning node.
- Every note starts as `visibility: undecided`. Only the owner moves a note to `announce`, `hold`
  or `internal`. At release, only `announce` notes are published to the team; `undecided` and
  `hold` notes carry forward to the next release; `internal` notes are recorded and never sent.
- **A release is recorded once.** The notes moved into `released/<version>/`, with the `release.json` beside them, are the record of what a release contained and which environment it reached when. The commit released to production carries an annotated tag `v<version>`, so Git itself shows what is in production. `STATE.md`, `LOG.md` and a handover entry name the version and do not list what it contained.
- A production release is a merge to the repository's production branch, or the platform
  equivalent the owner layer or the project's rules name.
