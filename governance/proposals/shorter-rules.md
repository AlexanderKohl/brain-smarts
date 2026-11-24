---
id: PROPOSAL-shorter-rules
title: The root rules say each thing once
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T13:56:06+10:00
updated: 2026-11-24T13:56:06+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.3.0
target_files:
  - /RULES.md
  - /CORE-RULES.md
---

# The root rules say each thing once

Read `/CONTRACT.md` first. This proposal amends rules in `/RULES.md` and keeps every identifier
(CONTRACT §13.2). The contract is not changed. `/CORE-RULES.md` is regenerated from `/RULES.md`.

## Plain-language summary

The owner asked on 24 November 2026 for a review of `/RULES.md` "for anything that is duplicated,
redundant or can be restated more succinctly". This is that review: 34 changes, each
with the text as it is, the text that would replace it and the reason. 5,349 of the
file's 96,887 characters go. The part that every writing session reads first,
`/CORE-RULES.md`, goes from 27,140 to 25,150 characters against
its limit of 28,000. With that room, the wording accepted the same day in
`PROPOSAL-answer-first-deliver-after` fits (27,180) and the limit need
not be raised.

One row changes meaning on purpose: "a question never stops the work it does not block", written
three times today for three kinds of question, is written once in `SMART-RULE-0010` and so applies
to every question. Every other row is meant to change no behaviour.

## Current problem

Rules that always apply are copied into the core, so every repeated sentence there is read by
every writing session, and the core had 786 characters of room left. `SMART-RULE-0007` already
says a rule's wording lives in one place; the file does not follow it everywhere.

## Current wording and exact diff

The changes are in three groups – duplicated, redundant, shorter – and inside each group in rule
order. The owner may accept all of them, or name the numbers accepted or refused.

### 1. SMART-RULE-0009 – Logical checkpoint commits, bullet 3 of 8 (duplicated; 45 characters shorter)

Only the changed part of the bullet is shown; the rest of it stays as it is.

Current:

> before asking the owner to test, reload, load-unpacked, install, or try a build;

Proposed:

> before an owner test (next bullet);

Why: The next bullet opens with the same list of five verbs. One of the two is enough.

### 2. SMART-RULE-0009 – Logical checkpoint commits, bullet 8 of 8 (duplicated; 49 characters shorter)

Current:

> - Never silently finish with committable agent-owned changes. In the final response, report the commit hash and push status for each modified repository, or state `No commit` with the specific reason. Valid reasons include: no durable change, no Git repository, the owner explicitly prohibited committing, validation or a hook failed, a merge/rebase/conflict is active, required Git identity or permission is unavailable, or the change cannot be separated safely from uncertain or unrelated files.

Proposed:

> - Never silently finish with committable agent-owned changes. The permitted reasons for no commit are: no durable change, no Git repository, the owner explicitly prohibited committing, validation or a hook failed, a merge/rebase/conflict is active, required Git identity or permission is unavailable, or the change cannot be separated safely from uncertain or unrelated files. The reply reports the commit, or the reason, as `SMART-RULE-0014` says.

Why: "Report the commit hash and push status for each modified repository, or state No commit with the reason" is the second bullet of SMART-RULE-0014, which also gives the exact line. This bullet keeps what only it holds: the list of permitted reasons.

### 3. SMART-RULE-0010 – Communication efficiency, bullet 1 of 4 (duplicated; 62 characters shorter)

Current:

> - In voice mode, when a clarifying question is required, ask one question at a time and wait for the answer before asking the next, unless the owner explicitly requests a grouped questionnaire. Outside voice mode, presenting a list of clarifying questions is acceptable-especially when scoping a software project. Do not invent questions when a safe default exists.

Proposed:

> - In voice mode, when a clarifying question is required, ask one question at a time and wait for the answer before asking the next, unless the owner explicitly requests a grouped questionnaire. Outside voice mode, a list of clarifying questions is acceptable, especially when scoping a software project.

Why: "Do not invent questions when a safe default exists" goes: the next bullet says it in full (prefer a reversible default and proceed; ask only for irreversible actions, secrets, material trade-offs or where policy requires).

### 4. SMART-RULE-0010 – Communication efficiency, bullet 4 of 4 (duplicated; 152 characters longer)

Current:

> - Every question to the owner carries at least one concrete suggested answer, so the owner
>   can reply "yes" or "ok". When several valid options exist, number them and mark the
>   recommended one, so the owner can reply with a number. The owner may always answer with
>   different instructions instead; a suggestion or a numbered list never limits the choice.

Proposed:

> - Every question to the owner carries at least one concrete suggested answer, so the owner can reply "yes" or "ok". When several valid options exist, number them and mark the recommended one, so the owner can reply with a number. The owner may always answer with different instructions instead; a suggestion or a numbered list never limits the choice. A question never stops the work it does not block: the agent continues with every other part of the task, so the question arrives with the rest already done.

Why: The last sentence is new here. Today it is written three times, in SMART-RULE-0017, 0036 and 0044, each for its own kind of question. Stated once in the rule about questions, it covers all three. It then applies to every question, not only those three kinds; that is the one change of meaning in this review.

### 5. SMART-RULE-0017 – Surface external-system configuration mismatches, bullet 3 of 4 (duplicated; 165 characters shorter)

Current:

> - Continue with every part of the task that does not depend on the answer, so the question arrives
>   with the rest of the work already done rather than blocking it.

Proposed:

Removed.

Why: Now the last sentence of SMART-RULE-0010's fourth bullet.

### 6. SMART-RULE-0019 – Context handoff checkpoint, bullet 12 of 14 (duplicated; 305 characters shorter)

Only the changed part of the bullet is shown; the rest of it stays as it is.

Current:

> The `## Handover` of `/memory/projects/brain-development/STATE.md` also names the **active conductor** (session title and the time it took over) and the other live sessions it knows of; a new thread that finds an active conductor asks the owner which thread continues before dispatching anything. Take the checkpoint whenever the remaining context is unlikely to carry the next stage, and at any natural handover where a fresh thread would work more efficiently.

Proposed:

> The live conductors are named in the `## Handover` of `/memory/projects/brain-development/STATE.md`, and a new thread that finds one asks the owner which thread continues (`SMART-RULE-0048`).

Why: Two duplicates at the end of the longest bullet. The register of live conductors and the question a new thread asks are the first bullet of SMART-RULE-0048, almost word for word. "Take the checkpoint whenever the remaining context is unlikely to carry the next stage" is the first two bullets of this same rule.

### 7. SMART-RULE-0022 – Tests demonstrate behaviour, bullet 6 of 8 (duplicated; 83 characters shorter)

Current:

> - Fixture and sample data remain subject to `SMART-RULE-0008`: entirely fictional.

Proposed:

Removed.

Why: A pointer that only repeats SMART-RULE-0008, whose own row in the index already applies it to "writing sample, seed or fixture data".

### 8. SMART-RULE-0032 – Skill exchange, bullet 4 of 6 (duplicated; 228 characters shorter)

Only the changed part of the bullet is shown; the rest of it stays as it is.

Current:

> merges `upstream/main` into the mechanics and the skill library the way `SMART-RULE-0034` merges `origin`: a merge commit, never a rebase or a forced push; a conflicting hand-written file stops the merge and is put to the owner; the merged result passes the repository preflight before it is pushed to `origin`. […] The setting is the owner's standing acceptance of protected-governance changes the upstream maintainer has already accepted on upstream `main` (CONTRACT §13.2); each merge that brings one is recorded

Proposed:

> merges `upstream/main` into the mechanics and the skill library the way `SMART-RULE-0034` merges `origin`, and pushes the checked result to `origin`. […] The setting is the owner's standing acceptance under CONTRACT §13.2; each merge that brings a protected-governance change is recorded

Why: The bullet says "the way SMART-RULE-0034 merges origin" and then repeats that rule's three conditions. The standing acceptance is defined in CONTRACT §13.2 in the same words.

### 9. SMART-RULE-0034 – Start from the latest, bullet 5 of 8 (duplicated; 71 characters shorter)

Current:

> - Never rewrite history or force a push to make a pull or a push work.

Proposed:

Removed.

Why: The second bullet of this rule already says "never a rebase of commits already made, a reset or a forced push", and SMART-RULE-0009's sixth bullet forbids amending, rewriting and force-pushing.

### 10. SMART-RULE-0034 – Start from the latest, bullet 8 of 8 (duplicated; 97 characters shorter)

Current:

> - Push at the end of each unit of work (`SMART-RULE-0009`), so the next computer starts from it.

Proposed:

Removed.

Why: A pointer to SMART-RULE-0009, which holds the push rule. SMART-RULE-0038 points to it as well ("Merge back at every unit of work").

### 11. SMART-RULE-0036 – Raise a rule that gets in the way, bullet 3 of 3 (duplicated; 114 characters shorter)

Current:

> - Continue with every part of the task the question does not block, so it arrives with the rest of the work done.

Proposed:

Removed.

Why: Now the last sentence of SMART-RULE-0010's fourth bullet.

### 12. SMART-RULE-0038 – One working copy per session, bullet 4 of 8 (duplicated; 141 characters shorter)

Current:

> - Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with
>   `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared
>   checkout. `session.py finish` does this and removes the worktrees once their branches are
>   merged. A conflict is reconciled, never overwritten: a generated file (a board, an index, a
>   task list) is taken from `main` and rebuilt by its generator; an append-only log keeps both
>   entries; any other conflict whose right resolution is not obvious from the two changes goes to
>   the owner.

Proposed:

> - Merge back at every unit of work (`SMART-RULE-0009`): bring the branch up to date with `origin/main`, resolve any conflict, validate, push to `main`, and fast-forward the shared checkout. `session.py finish` does this and removes the worktrees once their branches are merged. A conflict is reconciled as `SMART-RULE-0034` says, never overwritten; one whose right resolution is not obvious from the two changes goes to the owner.

Why: The treatment of a conflicting generated file and of an append-only log is in SMART-RULE-0034, almost word for word. Note: the two rules differ slightly today. 0034 sends every conflict in a hand-written file to the owner; 0038 sends only one "whose right resolution is not obvious". The new text keeps 0038's wording, so nothing changes here, but you may want one of the two.

### 13. SMART-RULE-0038 – One working copy per session, bullet 6 of 8 (duplicated; 539 characters shorter)

Current:

> - A session's delegated workers share its copy and branch by default. Each packet names the paths
>   its worker may change (`writes: paths`); the conductor keeps them disjoint across the run and
>   keeps shared files – logs, state, task lists, indexes, version fields, build output – for
>   itself. Only the conductor stages and commits. A worker gets its own worktree, branched from the
>   session's branch and merged back by the conductor, only when its work cannot be kept apart: it
>   builds code or runs tests that write outside its own paths, it must change a file another
>   worker also changes, or it is one of several alternative attempts. Unit tests that read and
>   write only inside the worker's own paths (and their caches) run in the session copy.

Proposed:

> - A session's delegated workers share its copy and branch by default. `SMART-RULE-0024` says which paths a worker may change, that only the conductor stages and commits, and when a worker gets a worktree of its own.

Why: The largest duplicate in the file. Every sentence of this bullet is also in the seventh bullet of SMART-RULE-0024: the packet's paths, disjoint paths, the shared files the conductor keeps, who commits, the three cases for an own worktree, and unit tests in the session copy. 0024 is read before any delegation, which is when this is needed.

### 14. SMART-RULE-0044 – Raise the ambition of every request, bullet 4 of 4 (duplicated; 159 characters shorter)

Current:

> - When a request starts a project, or leaves the design open, and the goals or the values behind
>   it are uncertain or could be read in more than one way, the agent asks about those before it
>   designs: what the work is for, whom it serves, and what matters more when two aims conflict.
>   It does not ask how the goals should be achieved; that is the agent's to work out. Each
>   question carries a suggested answer (`SMART-RULE-0010`), and the questions arrive with every
>   part of the work they do not block already done. A task whose outcome is already spelled out
>   gets no such questions.

Proposed:

> - When a request starts a project, or leaves the design open, and the goals or the values behind it are uncertain or could be read in more than one way, the agent asks about those before it designs: what the work is for, whom it serves, and what matters more when two aims conflict. It does not ask how the goals should be achieved; that is the agent's to work out. A task whose outcome is already spelled out gets no such questions.

Why: "Each question carries a suggested answer, and the questions arrive with every part of the work they do not block already done" goes: both halves are SMART-RULE-0010's fourth bullet.

### 15. SMART-RULE-0045 – Host plugin skills act under the brain, bullet 4 of 6 (duplicated; 172 characters shorter)

Current:

> - **Learnings flow into the brain.** Using a plugin skill is ordinary evidence under
>   `SMART-RULE-0028`. At the next natural checkpoint the agent records, in the owning subject's
>   knowledge store or `data/learnings/`: what the plugin produced that proved useful or wrong, the
>   owner's corrections to its output and the preference behind them, durable decisions it helped
>   reach, and failures or limits met. Each record names the host and plugin skill that produced the
>   output. Routine use that teaches nothing needs no record.

Proposed:

> - **Learnings flow into the brain.** Using a plugin skill is ordinary evidence under `SMART-RULE-0028`: what the plugin produced that proved useful or wrong, the owner's corrections to its output and the preference behind them, durable decisions it helped reach, and failures or limits met. Each record names the host and plugin skill that produced the output.

Why: "At the next natural checkpoint", "in the owning subject's knowledge store or data/learnings/" and "routine use needs no record" are SMART-RULE-0028's own second and third bullets, which this bullet already invokes.

### 16. SMART-RULE-0002 – Protected governance, bullet 1 of 3 (redundant; 85 characters longer)

Current:

> - Do not activate a protected governance change without the owner's explicit acceptance under Contract section 13.2.

Proposed:

> - CONTRACT §13.2 governs every change to protected governance. The report of an accepted change names its proposal ID, the exact files changed, the effective contract version and the validation result.

Why: The first bullet restates CONTRACT §13.2 (no change becomes active without the owner's explicit acceptance). Of the second, the contract already asks for the files and the version; the proposal ID and the validation result are named only here, so that sentence is kept.

### 17. SMART-RULE-0002 – Protected governance, bullet 2 of 3 (redundant; 132 characters shorter)

Current:

> - Report accepted governance changes with their proposal ID, exact changed files, effective contract version and validation result.

Proposed:

Removed.

Why: Merged into the bullet above.

### 18. SMART-RULE-0002 – Protected governance, bullet 3 of 3 (redundant; 438 characters shorter)

Current:

> - Small additive or clarifying changes to an existing numbered rule amend that rule in place and keep its ID. Give a new identifier only to a distinct new rule, not to a tweak, extra sentence or tighter constraint on an existing one; it takes the next number in its layer when the owner accepts it (CONTRACT §13.2, *Rule identifiers*). Record the amendment on the original proposal record; do not supersede a live rule with a new number.

Proposed:

Removed.

Why: CONTRACT §13.2 says the same in its paragraph "When the change is a small additive or clarifying amendment…" and under "Rule identifiers", to which this bullet itself points.

### 19. SMART-RULE-0013 – Per-API quirk knowledge base, bullet 2 of 5 (redundant; 169 characters shorter)

Current:

> - Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external API, search that system's `knowledge/` folder first - by filename convention (for example `Glob "business--*"` for one object type, `Glob "*--textbox-list--*"` for one field type across objects) and by frontmatter (`Grep` for `object_type:`, `field_type:`, `endpoint:` or `status:`) - before re-investigating from scratch. Treat a `refuted` entry as a warning against repeating that exact hypothesis; treat a `deprecated` entry as a pointer to its `superseded_by` replacement, not as current fact.

Proposed:

> - Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external API, search that system's `knowledge/` folder first, by filename and by front matter as its `_CONVENTION.md` shows, before re-investigating from scratch. Treat a `refuted` entry as a warning against repeating that exact hypothesis; treat a `deprecated` entry as a pointer to its `superseded_by` replacement, not as current fact.

Why: The search examples are in the `_CONVENTION.md` that the first bullet puts in every knowledge folder (section "Finding entries").

### 20. SMART-RULE-0013 – Per-API quirk knowledge base, bullet 3 of 5 (redundant; 49 characters shorter)

Current:

> - After a fix or investigation resolves genuinely unexpected or undocumented external-API behaviour, write one entry under that system's `knowledge/` folder, copied from `/shared/templates/api-knowledge-entry.template.md`, named `<object_type>--<field_or_topic>--<short-slug>.md`, with `system`, `object_type`, `field_type`, `endpoint`, `status` and `source_refs` set. Do not create an entry for routine work that reveals nothing unexpected about the external API - this store is for quirks and workarounds, not a general changelog.

Proposed:

> - After a fix or investigation resolves genuinely unexpected or undocumented external-API behaviour, write one entry under that system's `knowledge/` folder, copied from `/shared/templates/api-knowledge-entry.template.md` and named as the convention says, with `system`, `object_type`, `field_type`, `endpoint`, `status` and `source_refs` set. Routine work that reveals nothing unexpected about the external API gets no entry: the store holds quirks and workarounds, not a changelog.

Why: The file-name pattern is in the convention file (section "Filename").

### 21. SMART-RULE-0038 – One working copy per session, bullet 7 of 8 (redundant; 90 characters shorter)

Current:

> - The pre-commit hook refuses a commit on `main` in a repository's own working tree – the
>   shared checkout – and names the command that makes a session copy. Session copies are linked
>   worktrees on their own branches, so their commits pass; so do a `proposal/*` branch and any
>   other branch.

Proposed:

> - The pre-commit hook refuses a commit on `main` in the shared checkout and names the command that makes a session copy. A commit in a session copy, on a `proposal/*` branch or on any other branch passes.

Why: The hook enforces this and prints the command itself. The rule only needs to say that it does.

### 22. SMART-RULE-0044 – Raise the ambition of every request, bullet 1 of 4 (redundant; 157 characters shorter)

Current:

> - At the intake of every request, the agent applies `/shared/skills/raise-ambition/`: it names
>   the outcome behind the request and checks whether a bigger version would serve the user better
>   – one that reaches higher (an outcome kept true, not a task done once), deeper (an expert's
>   methods and a harder, measurable target) or wider (other fields and roles, including an
>   adversarial reviewer). The user is the person whose request it is: the owner, or a
>   collaborator working in a shared project.

Proposed:

> - At the intake of every request, the agent applies `/shared/skills/raise-ambition/`: it names the outcome behind the request and checks whether a bigger version – higher, deeper or wider, as the skill defines them – would serve the user better. The user is the person whose request it is: the owner, or a collaborator working in a shared project.

Why: The three definitions in brackets are the skill's own first lines, word for word. The rule names the skill, so the agent reads them there.

### 23. Contract restatements (end of the file), the whole section (redundant; 1,282 characters shorter)

Current:

> ## Contract restatements
>
> These restatements of `/CONTRACT.md` keep no separate rule identifier. Find the canonical wording in the contract section named here.
>
> - Use repository-root paths in metadata and cross-references. (CONTRACT §8 / §12)
> - Use one canonical home for every durable item. (CONTRACT §3.3)
> - Prefer links and dependencies over copies. (CONTRACT §3.3 / §12)
> - Keep metadata minimal, explicit and useful. (CONTRACT §8.4)
> - Preserve raw files unchanged. (CONTRACT §11.1)
> - Create Markdown source records for raw files. (CONTRACT §11.2)
> - Treat the task stores of CONTRACT §9 – every node's `tasks/` and `/memory/tasks/` – as the canonical task system. (CONTRACT §9)
> - Use shared skills for reusable capabilities. (CONTRACT §10.1)
> - Keep project-specific configuration inside the project, and owner-wide skill configuration in `/memory/skills/<skill>/`. (CONTRACT §3.5 / §10.1)
> - Keep personal data out of the mechanics repository; it belongs in `/memory/`. (CONTRACT §3.4)
> - Record meaningful state changes and decisions. (CONTRACT §4 / §5)
> - Use ISO 8601 timestamps with seconds and an explicit timezone for `created`, `updated`, and log entry headings; never use date-only values for them. (CONTRACT §8.2)
> - Do not store secrets in the repository. (CONTRACT §10.3)

Proposed:

Removed.

Why: Thirteen one-line restatements of the contract, under a heading that says so. SMART-RULE-0007: "A rule's wording lives only in its canonical home. Anywhere else it is referred to by its identifier and section, never restated in other words." The table of contract sections at the top of this file already says when to read each one.

### 24. SMART-RULE-0006 – Owner-facing shell includes cd, bullet 1 of 1 (shorter; 85 characters shorter)

Current:

> - Whenever giving the owner shell commands to run, always include an explicit `cd` (or equivalent) to the brain root named as `brain_root` in `/memory/OWNER.md` (or the active absolute working directory if the command must run elsewhere, such as the memory checkout or a project repository) before the command, so the owner does not have to locate the correct folder.

Proposed:

> - A shell command given to the owner starts with an explicit `cd` (or equivalent) to the folder it must run in: the brain root named as `brain_root` in `/memory/OWNER.md`, or the absolute working directory when it runs elsewhere, such as the memory checkout or a project repository.

Why: One sentence, same rule.

### 25. SMART-RULE-0007 – Portable behavioural rules only, bullet 1 of 4 (shorter; 84 characters longer)

Current:

> - Keep durable behavioural rules only in portable governance: `/CONTRACT.md`, root and node `RULES.md` files, and skill operating instructions. Do not create or maintain host-specific behavioural rule files that restate or extend how agents must behave.

Proposed:

> - Durable behavioural rules live only in portable governance: `/CONTRACT.md`, root and node `RULES.md` files, and skill operating instructions. A host entry file only points agents to the portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`, `/AGENTS.md`); no host-specific file restates, extends or carries behavioural policy of its own.

Why: The first two bullets say the same thing from two sides (no host rule files; host files only point). Merged.

### 26. SMART-RULE-0007 – Portable behavioural rules only, bullet 2 of 4 (shorter; 162 characters shorter)

Current:

> - Host entry files may only point agents to portable bootstrap (`/CONTRACT.md`, `/BOOTSTRAP.md`, `/AGENTS.md`) and must not carry independent behavioural policy.

Proposed:

Removed.

Why: Merged into the bullet above.

### 27. SMART-RULE-0009 – Logical checkpoint commits, bullet 1 of 8 (shorter; 167 characters shorter)

Current:

> - Portable git checkpoint rules in this file (`SMART-RULE-0009`) override any host-specific "ask before commit", "only commit when asked", or "always present commit/push options" instructions in this repository and in every other Git repository modified during an owner-authorised task. Still never commit secrets or unrelated dirty files. Host "only commit when asked" instructions apply only when this rule does not apply (for example a repository the owner has not authorised this task to change).

Proposed:

> - This rule overrides a host's "ask before commit", "only commit when asked" or "always present commit/push options" instructions in every Git repository modified during an owner-authorised task. Those host instructions apply only where this rule does not, for example in a repository the owner has not authorised the task to change.

Why: The override is said once instead of twice. "Still never commit secrets or unrelated dirty files" goes: the sixth bullet of the same rule already forbids both.

### 28. SMART-RULE-0009 – Logical checkpoint commits, bullet 5 of 8 (shorter; 139 characters shorter)

Current:

> - At each checkpoint, inspect `git status` and the relevant diff, stage only agent-owned files that belong to that logical change, check that no secret or unrelated change is included, run proportionate validation, and commit with a concise message whose subject says what changed and never names the tool or the model. Two trailers of the same commit name them: `Tool: <host or tool>` (for example `Tool: Claude Code desktop` or `Tool: Cursor`, with the agent's bot name when it has one) and `Co-Authored-By: <model> <address>` (for example `Co-Authored-By: Claude Opus 5.5 <the host's no-reply address>`). In the brain's repositories the commit-message hook refuses a commit, other than a merge, without both. Do not invent a model or version. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.

Proposed:

> - At each checkpoint, inspect `git status` and the relevant diff, stage only the agent-owned files of that logical change, run proportionate validation, and commit with a concise message whose subject says what changed and never names the tool or the model. Two trailers of the same commit name them: `Tool: <host or tool>` (for example `Tool: Cursor`, with the agent's bot name when it has one) and `Co-Authored-By: <model> <address>` (the host's no-reply address), never an invented model or version. In the brain's repositories the commit-message hook refuses a commit, other than a merge, without both. Pre-existing or concurrent dirty files do not prevent a path-scoped commit when the agent-owned change can be separated safely.

Why: One example per trailer instead of three. "Check that no secret or unrelated change is included" goes: staging only agent-owned files covers the second half, and the next bullet forbids committing secrets.

### 29. SMART-RULE-0026 – Version every change, and show it, bullet 1, first number (shorter; 255 characters shorter)

Only the changed part of the bullet is shown; the rest of it stays as it is.

Current:

> two. While a product is still in development its version stays below `1.0.0`, and a breaking change there bumps the **middle** number instead: nothing outside the team depends on it yet, so the first number would say nothing a reader could use. `1.0.0` is set once, deliberately, when the owner declares the product released, and from that version on the first number follows the test above. A breaking change before `1.0.0` is still named as breaking in its commit message and in the node's `LOG.md`, so the history says what changed even where the number does not.

Proposed:

> two. Until the owner declares the product released, its version stays below `1.0.0` and a breaking change bumps the **middle** number instead; it is still named as breaking in its commit message and in the node's `LOG.md`. `1.0.0` is set once, deliberately, and from that version on the first number follows the test above.

Why: The two explanations of why go ("nothing outside the team depends on it yet…", "so the history says what changed…"). What to do is unchanged. Say no to this row if you want the reasons kept in the rule.

### 30. SMART-RULE-0027 – Every list has a deliberate order, bullet 1 of 4 (shorter; 72 characters shorter)

Current:

> - Every list a person reads is put in an order chosen for that reader, never left in the
>   order it was produced: the options of a dropdown, the rows of a table, the sections of a
>   report, the findings of a check, the bullets of a reply, the entries of an index. Insertion
>   order, capture order, map order and API order are not orders; they are accidents.

Proposed:

> - Every list a person reads is in an order chosen for that reader, never the order it was produced in: a dropdown's options, a table's rows, a report's sections, a check's findings, a reply's bullets, an index's entries. Insertion, capture, map and API order are accidents, not orders.

Why: Same six examples and the same point, in fewer words.

### 31. SMART-RULE-0027 – Every list has a deliberate order, bullet 2 of 4 (shorter; 95 characters shorter)

Current:

> - The default is alphabetical by the label the reader sees, with numbers inside labels
>   compared as numbers, so `1.2` precedes `1.10`. Another order replaces it only when the
>   reader is better served by it, and the code or the document says so in a comment or a
>   line: by time when the reader follows a sequence, by severity or priority when they act
>   on the worst first, by frequency or size when the largest matters most, by a fixed
>   domain order when one exists, such as the stages of a pipeline. The chosen order holds
>   across renders and captures, so two views of the same data list it the same way.

Proposed:

> - The default is alphabetical by the label the reader sees, with numbers inside labels compared as numbers, so `1.2` precedes `1.10`. Another order replaces it only when it serves the reader better, and the code or the document says so in a line: time for a sequence, severity or priority when the worst is acted on first, frequency or size when the largest matters most, a fixed domain order such as the stages of a pipeline. The chosen order holds across renders and captures, so two views of the same data agree.

Why: Same default, same four exceptions, same requirement to say which order was chosen.

### 32. SMART-RULE-0034 – Start from the latest, bullet 2 of 8 (shorter; 103 characters longer)

Current:

> - **Diverged history between agents is routine, not an owner decision.** When a brain repository – the mechanics, the skill library or the memory – has commits of its own that `origin` does not, and `origin` has commits it does not (the history has diverged), and no tracked file has uncommitted changes, the agent merges `origin` into it without asking: a merge commit, never a rebase of commits already made, a reset or a forced push. A generated file that conflicts (a board, an index, a task list) is taken from `origin` and rebuilt by its generator; an append-only log keeps both entries. The merged result passes the repository preflight before it is pushed. `sync.py` does this for the shared checkout by merging in a session copy of its own and then fast-forwarding the shared checkout, which is never merged into (`SMART-RULE-0038`); `session.py finish` does it for a session copy.

Proposed:

> - **Diverged history and a refused push are routine, not an owner decision.** When a brain repository – the mechanics, the skill library or the memory – and its `origin` each have commits the other lacks, and no tracked file has uncommitted changes, the agent merges `origin` into it without asking: a merge commit, never a rebase of commits already made, a reset or a forced push. A generated file that conflicts (a board, an index, a task list) is taken from `origin` and rebuilt by its generator; an append-only log keeps both entries. The merged result passes the repository preflight before it is pushed. A push refused because `origin` has moved on is the same case: fetch, merge, check and push again, up to three attempts in all, then stop and report. `sync.py` does the merge for the shared checkout, in a session copy of its own, so that the shared checkout is only ever fast-forwarded (`SMART-RULE-0038`); `session.py finish` does the merge and the repeated push for a session copy.

Why: The second and third bullets describe one routine in two places ("A refused push is the same case"). Merged into one bullet; every step is kept.

### 33. SMART-RULE-0034 – Start from the latest, bullet 3 of 8 (shorter; 248 characters shorter)

Current:

> - **A refused push is the same case.** When a push is refused because `origin` has moved on, the agent fetches, merges, runs the preflight and pushes again, up to three attempts in all, then stops and reports. `session.py finish` does this itself.

Proposed:

Removed.

Why: Merged into the bullet above.

### 34. SMART-RULE-0046 – A release note for every change a user would notice, bullet 1 of 8 (wording; 3 characters shorter)

Only the changed part of the bullet is shown; the rest of it stays as it is.

Current:

> – staff, customers, or a colleague

Proposed:

> – the team, customers, or a colleague

Why: Not a saving: a word. Your owner-layer rule asks for "the team", never "staff", and to correct it when the file is next touched.

## Found and not changed

- **Who commits a subagent's work.** SMART-RULE-0014, bullet 3, says the primary agent commits and a subagent reports its changed paths. SMART-RULE-0024, bullet 4, says an agent started without a work packet does the whole job, the commit included. The two disagree for a subagent without a packet in a shared worktree. Not changed here: it needs your decision, not shorter wording.
- **A conflict in a hand-written file.** SMART-RULE-0034, bullet 4, sends every such conflict to the owner. SMART-RULE-0038, bullet 4, sends only one whose right resolution is not obvious from the two changes. Kept as it is today.
- **Long rules left alone.** SMART-RULE-0016 (product development), 0024 (delegated work), 0028 (learning) and 0049 (fast checks) are the longest rules that are not read by every session. I found nothing in them that is written twice. Shortening them means reading each beside its skill, which I have not done.

## Reason

Fewer words to read at the start of every session, one place to change when a rule changes, and
room in the core for rules still to come.

## Scope and consequences

Every agent in every host. `/CORE-RULES.md` becomes shorter. Rules that are not always read lose
only sentences that another rule, the contract, a skill or a template states.

## Risks, conflicts and migration

- **A rewrite drops a nuance nobody intended to drop.** Each row shows the full old and new text
  so the owner can refuse it. A shortened rule that is later found to have lost something is
  restored from this record.
- **A removed duplicate was the copy an agent actually read.** `SMART-RULE-0038`'s sixth bullet is
  in the core and its twin in `SMART-RULE-0024` is not; after the change an agent learns the
  worker rules when it reads 0024 before delegating, which the index requires.
- No migration.

## Rollback

Restore `/RULES.md` from the commit before the change and regenerate the core files.

## Planned validation

- Every "current" text was matched in `/RULES.md` exactly once by script before the page and this
  record were written; the sizes above were measured with `core.py build` on a copy.
- After acceptance: apply the accepted rows by the same script, `core.py build`, the repository
  preflight, and the tests of the repository-preflight skill.
