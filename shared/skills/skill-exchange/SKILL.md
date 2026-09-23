---
id: skill-skill-exchange
title: Skill Exchange
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
script_paths:
  - /shared/skills/skill-exchange/scripts/skill_exchange.py
created: 2026-09-23T14:00:00+10:00
updated: 2026-09-23T17:31:00+10:00
owner: brain-owner
skill_refs:
  - /shared/skills/learning-maintenance
  - /shared/skills/repository-preflight
---

# Skill Exchange

Read `/CONTRACT.md` first.

This skill is the operating detail of `SMART-RULE-0032` in `/RULES.md`.

## Purpose

Skills move between brains in both directions, and each move is the owner's decision:

1. **Notice** – an agent sees a capability built for one node that another node or another
   owner could use, and suggests promoting it to a shared skill.
2. **Offer upstream** – a promoted, scrubbed skill goes to the original mechanics repository as
   a pull request the upstream maintainer accepts or declines.
3. **Hear about upstream** – on a cadence, the agent tells the owner what changed upstream that
   touches the skills and rules they use.
4. **Install from elsewhere** – a skill from someone else's brain is installed with its source
   and commit recorded in memory.

The skill never pushes, opens a pull request, merges, installs or switches a skill on by
itself. Each of those is one question to the owner with a suggested answer (`SMART-RULE-0010`).

## Where things live

Mechanics (this folder) holds the procedure and the script. Everything about this owner's
exchange lives in memory:

| Path | What it holds |
|---|---|
| `/memory/OWNER.md` `active_skills` | The optional shared skills the owner has switched on; drives relevance. |
| `/memory/skills/installed.json` | Provenance of every skill installed from another brain. |
| `/memory/skills/skill-exchange/candidates.json` | Promotion candidates and the owner's answers. |
| `/memory/skills/skill-exchange/config/settings.json` | Cadence and suggestion settings (below). |
| `/memory/skills/skill-exchange/scrub-allow.txt` | Exact strings the scrub check may accept, each justified in the commit. |
| `/memory/skills/skill-exchange/state.json` | When upstream was last checked and what was already reported. |

`settings.json`, all keys optional:

```json
{
  "branch": "main",
  "check_every_days": 7,
  "max_items_per_digest": 5,
  "remote": "upstream",
  "suggestions": "checkpoint"
}
```

`suggestions` is `checkpoint` (default: at natural checkpoints, batched), `weekly` (only in
the weekly review of `SMART-RULE-0028`) or `off` (only when the owner asks).

## When to suggest, and how much

- **At natural checkpoints only**: session start (after bootstrap, before the owner's first task
  starts), the end of a unit of work, and the weekly learning review. Never in the middle of
  a task, never as a reply's opening line when the owner asked for something else.
- **Batched**: one short block per checkpoint, at most `max_items_per_digest` items, numbered,
  with the recommended answer marked.
- **Once**: a suggestion the owner declined is not repeated unless new evidence arrives
  (the candidate gains an observation after the decision). A digest is never repeated for the
  same upstream commit.
- **Silent when there is nothing**: no "nothing new upstream" line unless the owner asked.
- **The exception**: an upstream change that fixes a security fault in a skill the owner uses
  is reported at the next response, not the next checkpoint (`SMART-RULE-0028`, *Interrupt only
  when needed*).

## Procedure

### 1. Notice a reusable capability

While working, an agent records a candidate when a node-local skill, script or procedure
(under `/memory/projects/<node>/skills/`, or code in a project repository that is not about
that project) meets **two** of these:

- it is used, or copied, by a second node;
- nothing in it depends on this owner's data once its configuration is moved out;
- it wraps an external system or format other owners use;
- the agent searched `/shared/skills/` for it first and found nothing (`SMART-RULE-0005`).

```powershell
cd <brain_root>
python shared/skills/skill-exchange/scripts/skill_exchange.py candidate add /memory/projects/<node>/skills/<name> --reason "<the observation>"
```

At the next checkpoint the agent suggests it:

> **Suggest:** `<name>` in `<node>` looks reusable: <one line of evidence>. Promote it to a
> shared skill?
> 1. Yes – generalise it into `/shared/skills/<name>/`, owner settings to
>    `/memory/skills/<name>/` (recommended)
> 2. Not now – ask again only if it is copied somewhere else
> 3. Never for this one

The answer is recorded with `candidate mark <path> suggested|declined|promoted`.

### 2. Promote, then scrub before anything leaves memory

Promotion follows CONTRACT §3.4: the mechanism goes to `/shared/skills/<name>/` in generalised
form (`SKILL.md` with `status: proposed`, `scripts/`, `scripts/tests/` with fictional data per
`SMART-RULE-0008`), owner configuration and notes go to `/memory/skills/<name>/`, and the
original incident stays in its node. Then, **before the first mechanics commit**:

```powershell
cd <brain_root>
python shared/skills/skill-exchange/scripts/skill_exchange.py scrub shared/skills/<name>
python -m unittest discover -s shared/skills/<name>/scripts/tests
python shared/skills/repository-preflight/scripts/preflight.py
```

`scrub` is the validator's personal-data check (`SMART-RULE-0008`,
`/shared/skills/repository-preflight/scripts/personal_data.py`) run on any path you name. It
builds the owner's terms in memory from `/memory/OWNER.md` (names, account, local paths), the
owner's own project and system node names and the optional
`/memory/skills/repository-preflight/config/denylist.txt`, and looks for e-mail addresses, phone
numbers, UUIDs and absolute user paths. It must report `0 hit(s)`. Fix a hit at its source; a
value that is genuinely public or generic goes in the validator's reasoned exemptions, and
`scrub-allow.txt` covers only a one-off check of a path outside the shareable repositories. The
owner's terms are never written outside memory and never quoted in a report.

### 3. Offer it upstream

Only after the owner says yes to *this* contribution (it publishes to someone else's
repository):

1. Branch the smarts checkout: `git switch -c contrib/<name>`.
2. Commit the skill folder and a proposal file
   `/governance/proposals/PROPOSAL-skill-<name>.md` (`type: governance_proposal`,
   `status: proposed`, no `RULE-` number – the upstream maintainer assigns one if a rule is
   needed) stating the problem, what the skill does, what it needs, its tests and its risks.
3. Push to the owner's own repository (`origin`), never to `upstream`.
4. Open the pull request against the upstream default branch. The body carries the **scrub
   report** (`0 hit(s)` and the count of allow-listed strings, never the strings), the test
   command and its result, and the preflight result:

   ```powershell
   gh pr create --repo <upstream owner>/<upstream repo> --head <github_account>:contrib/<name> --title "Skill: <name>" --body-file <report>
   ```

   This works when the owner's repository is a GitHub fork of upstream. A private copy made
   with `/SETUP.md` step B3 option 1 is not a fork: ask the upstream maintainer for a
   contributor branch (`git push <upstream url> contrib/<name>`, with the owner's written go)
   or send `git format-patch` output instead. Say which applies before asking.
5. Upstream acceptance is the maintainer's; the owner's copy keeps the skill either way.

### 4. Hear about upstream

At session start, cheaply:

```powershell
cd <brain_root>
python shared/skills/skill-exchange/scripts/skill_exchange.py due
```

Exit code 0 means a check is due (default every seven days). Then:

```powershell
python shared/skills/skill-exchange/scripts/skill_exchange.py upstream
```

which runs `git fetch upstream`, compares `HEAD` with `upstream/main` from their merge base, and
prints a digest for the owner, in this order: changed skills in `active_skills`, changed
skills every brain uses (named by path in `/RULES.md` or `/CONTRACT.md`), changed governance,
new skills; everything else is one count. It records the upstream commit so the same digest
is never shown twice. `--json` gives the full grouping; `--dry-run` records nothing.

The owner decides locally. The usual answer is to take upstream whole, because mechanics are
inert until switched on:

> 1. Merge `upstream/main` now; switch nothing on (recommended when no governance changed)
> 2. Merge, and add `<new skill>` to `active_skills`
> 3. Not now

A digest that includes governance changes (`/CONTRACT.md`, `/RULES.md`, bootstrap files,
`/governance/`) is **protected governance**: merging it changes active rules, so it is
presented as a proposal with the diff and waits for explicit acceptance (CONTRACT §13.2).

### 5. Install a skill from another brain

Only on the owner's request, and only after the agent has read every file of the skill
(scripts run with the owner's credentials and access):

```powershell
cd <brain_root>
git fetch <source repository url> <commit>
git switch -c install/<name>
git checkout FETCH_HEAD -- shared/skills/<name>
python shared/skills/skill-exchange/scripts/skill_exchange.py scrub shared/skills/<name>
python -m unittest discover -s shared/skills/<name>/scripts/tests
git commit -m "<host> <model>: install <name> from <source> at <commit>" -- shared/skills/<name>
python shared/skills/skill-exchange/scripts/skill_exchange.py record-install --skill <name> --source <source repository url> --commit <full commit>
```

`installed.json` (memory) then holds the skill, its path, source repository, source commit,
the installed tree hash and the time. `verify-installs` says whether each installed skill
still matches what was installed, so a local edit to someone else's code is visible. The source
repository is recorded only in memory: it names another person's account.

Switching the skill on is a separate step: add it to `active_skills` and follow its own
`## Setup` instructions.

## Scripts or commands

`scripts/skill_exchange.py`, stdlib only. Subcommands, alphabetical:

| Command | Job | Writes |
|---|---|---|
| `candidate add|list|mark` | Record, list and resolve promotion candidates | `candidates.json` |
| `due` | Exit 0 when an upstream check is due | nothing |
| `record-install` | Record a skill's source and commit | `/memory/skills/installed.json` |
| `scrub <path>...` | Personal-data check; exit 1 on any hit | nothing |
| `upstream` | Fetch and digest upstream changes | `state.json` (unless `--dry-run`) |
| `verify-installs` | Compare installed skills with their recorded trees | nothing |

Tests: `python -m unittest discover -s shared/skills/skill-exchange/scripts/tests -v`.

## Allowed operations and permissions

Reads the mechanics repository, `/memory/OWNER.md` and this skill's memory folder; `git fetch`
from `upstream`; writes only the memory files listed above. Pushing, opening a pull request,
merging upstream, fetching from another person's repository and switching a skill on each
need the owner's yes for that action. No credentials.

## Failure behaviour

No `upstream` remote: the digest says so and points at `/SETUP.md` step B3. A failed fetch
stops with git's message and records nothing. A scrub hit blocks the commit or pull request
until it is fixed or allow-listed with a reason.

## Logging and state, knowledge and task updates

A promotion, contribution or install is logged in the `LOG.md` of the node that owned the
capability, or `/memory/LOG.md` for an install. A declined suggestion needs no log entry; its
record in `candidates.json` is enough.
