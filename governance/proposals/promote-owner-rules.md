---
id: PROPOSAL-promote-owner-rules
title: Four owner-layer rules become mechanics rules
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-10-23T08:13:29+10:00
updated: 2026-10-23T08:13:29+10:00
rule_id: null
accepted_by: null
accepted_at: null
implemented_at: null
previous_contract_version: 2.7.0
new_contract_version: 2.7.0
target_files:
  - /RULES.md
  - /memory/RULES.md
  - /memory/OWNER.md
  - /library/skills/command-output/SKILL.md
  - /library/skills/release-notes/SKILL.md
  - /library/skills/product-feedback/SKILL.md
  - /library/skills/README.md
  - /shared/skills/README.md
---

# Four owner-layer rules become mechanics rules

Read `/CONTRACT.md` first.

## Plain-language summary

Four of the owner's five owner-layer rules describe mechanisms any owner could adopt. They move to
`/RULES.md` as `SMART-RULE-0045` to `SMART-RULE-0048`, written for "the owner" instead of a name,
with the owner's own details left in memory:

- **Host plugins act under the brain** (was `MEMORY-RULE-0002`) – unchanged in substance.
- **A release note for every change a user would notice** (was `MEMORY-RULE-0003`) – the HighLevel
  specifics stay in the owner layer as a shortened `MEMORY-RULE-0003`.
- **Long command output is shortened** (was `MEMORY-RULE-0004`) – unchanged in substance.
- **One conversation with the owner** (was `MEMORY-RULE-0005`) – untangled: the bullets that
  repeat `SMART-RULE-0024` are dropped, the number of team sessions becomes a setting in
  `/memory/OWNER.md` (`team_sessions_max`, two for this owner), and the Brain Feedback triage run
  moves into the product-feedback skill's own permissions.

Three skills the new rules require become core skills (CONTRACT §3.4) and move from `/library/` to
`/shared/skills/`: `command-output`, `release-notes` and `product-feedback`. The en-dash rule
(`MEMORY-RULE-0001`) stays in the owner layer: it is a house style another owner may not share.

## What a "team session" is

A team session is a separate agent session – its own conversation, visible in the host's session
list – that the conductor starts for one body of work lasting more than a day. It conducts that
work with its own workers, reports to the conductor and never talks to the owner. It is not a
worker: a worker is a subagent started with a delegation packet inside the conductor's session. The
limit of two came from the scrum trial (`SMART-RULE-0043`, "Start with two teams") and from the
memory each session costs on the owner's machine (`SMART-RULE-0037`); as a setting it can rise after
a measured trial without a rule change.

## Current wording

`/memory/RULES.md`, `MEMORY-RULE-0002` to `MEMORY-RULE-0005`, as of 17 October 2026 (unchanged
here; read the file).

## Proposed wording

### New rows in the `/RULES.md` index

```markdown
| `SMART-RULE-0045` | Host plugin skills act under the brain | this file |
| `SMART-RULE-0046` | A release note for every change a user would notice | this file; `/shared/skills/release-notes/` |
| `SMART-RULE-0047` | Long command output is shortened before the model reads it | this file; `/shared/skills/command-output/` |
| `SMART-RULE-0048` | One conversation with the owner | this file; `team_sessions_max` in `/memory/OWNER.md`; `/shared/skills/product-feedback/` |
```

### New sections in `/RULES.md`

```markdown
## SMART-RULE-0045 – Host plugin skills act under the brain

- A host plugin skill is a skill installed in one AI host rather than in the brain (for example a
  host's engineering, marketing, design or legal plugins). It may be used as a tool inside brain
  work. `/CONTRACT.md`, this file, `/memory/RULES.md` and the active node's rules govern it: where a
  plugin's own instructions differ – output style, list order, record formats, sending messages,
  external writes, commits – the brain's rule applies.
- Work done with a plugin follows the brain skill it serves: engineering work stays inside the
  product-development process (`SMART-RULE-0016`) with its gates, versions and checkpoint commits;
  user-interface work inside the brain's UI skills; marketing and legal work inside the owning
  project's node. The owner's mapping of enabled plugins to brain skills is kept in
  `/memory/ONBOARDING_OWNER.md` § Host plugins and updated whenever a plugin is enabled or disabled.
- Output lands in its canonical home in house style: a draft in the owning node or
  `/memory/outbox/`, a decision in the node's `STATE.md` or `KNOWLEDGE.md`, a task in
  `/memory/tasks/`. Messages are drafted, never sent without the owner's approval, and a plugin
  connector's write to an outside system needs the confirmed target of CONTRACT §10.5 like any
  other.
- **Learnings flow into the brain.** Using a plugin skill is ordinary evidence under
  `SMART-RULE-0028`. At the next natural checkpoint the agent records, in the owning subject's
  knowledge store or `data/learnings/`: what the plugin produced that proved useful or wrong, the
  owner's corrections to its output and the preference behind them, durable decisions it helped
  reach, and failures or limits met. Each record names the host and plugin skill that produced the
  output. Routine use that teaches nothing needs no record.
- A plugin pattern that proves useful more than once is a candidate brain skill, suggested for
  promotion under `SMART-RULE-0032`, so the capability becomes portable to hosts that lack the
  plugin.
- A plugin connector's account is recorded in the owner's credential registry as
  `managed_by: host` when it is first used for real work; its credentials stay with the host,
  never in the brain.

## SMART-RULE-0046 – A release note for every change a user would notice

- A release note records one change that someone who uses the system – staff, customers, or a
  colleague working in a platform the brain builds in – would see, do, receive or need to watch for
  differently. It is written from their side, in their words, with no code terms. Commits and
  their messages stay the developer's record and are not release notes.
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
- A production release is a merge to the repository's production branch, or the platform
  equivalent the owner layer or the project's rules name.

## SMART-RULE-0047 – Long command output is shortened before the model reads it

- A shell command's long output reaches the model shortened by `/shared/skills/command-output/`:
  its head and tail, every error line, and a last line naming the file that holds the full output.
  Short output, and the output of a command the skill does not recognise, reach the model
  unchanged.
- On a host whose after-command hook is registered (the skill's *Hosts* section), the hook does
  this and the agent does nothing. On any other host, the agent runs a test run, a build, an
  install, or a long `git diff` or `git log` through the skill's wrapper, `run.py`.
- An agent that needs more than the shortened output reads the named file. It does not run the
  command again to see the rest.
- When shortened output hid something an agent needed, the agent tells the owner in its next reply
  and records the case under `/memory/projects/brain-development/` as evidence about the filter
  (`SMART-RULE-0028`).

## SMART-RULE-0048 – One conversation with the owner

- The owner talks to one conductor thread at a time. The conductor answers the owner, puts every
  question to the owner, and gets work done through workers (`SMART-RULE-0024`).
- For a task that will take more than a day and passes several of the owner's gates, the
  conductor may start a team session: a separate agent session that conducts that one body of work
  with its own workers (a team thread, `SMART-RULE-0043`). At most `team_sessions_max` in
  `/memory/OWNER.md` run at once, two when it is not set. A team session never puts a question to
  the owner and never starts another session; it sends its questions and results to the
  conductor, who asks the owner in the conversation. The conductor archives a team session the day
  it hands back. No other session is started unless the owner asks for one in words, or a rule
  names it.
- Every packet that changes code carries the pre-merge checklist. The conductor runs it again on
  the merged tree before every push: the full unit suite, the code map check, the build, the
  version and release-note checks, unique migration names, and a safe fallback when a read fails.
  A push goes only after the checks pass, and CI results are read after each push, before the next
  merge.
- When the conductor's context reaches its checkpoint (`SMART-RULE-0019`), it hands over to one
  successor conductor and stops. The successor is the only thread the owner talks to.
```

### `/memory/RULES.md`

- `MEMORY-RULE-0002`, `MEMORY-RULE-0004` and `MEMORY-RULE-0005` are retired: each heading is
  replaced by one line, "Retired on <date>: now `SMART-RULE-00NN` in `/RULES.md`." Their numbers
  are never reused.
- `MEMORY-RULE-0003` keeps its number and shrinks to the owner's own details:

```markdown
## MEMORY-RULE-0003 – Release notes: HighLevel details

- `SMART-RULE-0046` governs release notes. For this owner, the people who notice a change include
  office staff, sales, installers and customers, and colleagues working in HighLevel.
- HighLevel notes come from Atlas's export, or are written by hand in the owning memory node until
  Atlas has one.
- For HighLevel, a production release is a snapshot push from the Main sub-account.
```

### The product-feedback skill's *Permissions* section gains

```markdown
- **A feedback packet may start one triage run.** The companion starts one headless run per packet
  it receives, in sequence, on the owner's machine and subscription. The run is a worker
  (`SMART-RULE-0024`): it reads the triage brief, the packet and the product's node rules, answers
  the person in the panel, writes only inside the packet's folder under `/temp/feedback/`, never
  commits, never writes a task, log, state or index file, never uses a credential, and never puts a
  question to the owner in the conversation. A bug or an idea it logs reaches the conductor through
  `companion.py sweep`, which the conductor turns into cards; the build goes through the
  conductor's workers as any other card. The run counts against the machine's margin
  (`SMART-RULE-0037`) like a worker.
```

### `/memory/OWNER.md`

`team_sessions_max: 2` added to the front matter, with a row in its field table.

## Reason

The owner asked on 23 October 2026 to promote `MEMORY-RULE-0002`, `0003` and `0004`, and to
untangle `0005` so it can be promoted too.

## Scope and consequences

Every brain that adopts the mechanics gains the four rules. For this owner nothing changes in
behaviour: the wording is the same in substance, and the owner's details stay in the owner layer
and `/memory/OWNER.md`.

## Risks, conflicts and migration

- **Skill moves.** `command-output`, `release-notes` and `product-feedback` move from `/library/`
  to `/shared/skills/` (core skills, CONTRACT §3.4). About 8, 8 and 17 references to their library
  paths are updated in the mechanics, library and memory; historical logs and proposals keep the
  old paths, and the moved files are registered in `/governance/removed-files.md`.
- **The host hook.** The owner's Claude Code user settings run
  `C:/dev/brain/library/skills/command-output/scripts/hook.py`; the path is updated in the same
  change, or the hook stops shortening output (it fails open, so nothing breaks, but long output
  would reach the model in full).
- **Project repositories.** None of the four checked project repositories references the
  release-notes skill's library path in CI; each is checked again before the move.
- **Overlap with `SMART-RULE-0043`.** The scrum master of `SMART-RULE-0043` and the conductor of
  `SMART-RULE-0048` are the same thread when a scrum runs; team sessions are its team threads.

## Rollback

Delete `SMART-RULE-0045` to `0048` and their index rows, restore `MEMORY-RULE-0002` to `0005` from
Git history, move the three skills back to `/library/`, and restore the hook path. Retired numbers
are not reused.

## Validation

Repository preflight on all three repositories, each moved skill's own tests, a run of the
command-output hook on a long `git log` after the path change, and the release-notes check in one
project repository.
