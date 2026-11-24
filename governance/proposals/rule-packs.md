---
id: PROPOSAL-rule-packs
title: Rule packs: the rules of one situation in one file
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-24T17:32:22+10:00
updated: 2026-11-24T18:22:16+10:00
previous_contract_version: 3.3.0
new_contract_version: 3.4.0
target_files:
  - /CONTRACT.md
  - /CORE-RULES.md
  - /CORE.md
  - /RULES.md
  - /shared/skills/repository-preflight/SKILL.md
---

# Rule packs: the rules of one situation in one file

Read `/CONTRACT.md` first. This proposal amends `/RULES.md` (its index text and a new pack table), CONTRACT §1 and §15, and the validator's *Failure behaviour*; every rule keeps its identifier
(CONTRACT §13.2). The contract changes and takes the next minor version at acceptance: 3.4.0, or the one after it if another contract change of the same day is accepted first (CONTRACT §13.3). It is one of six proposals of 24 November 2026 that came out of
measuring what a session reads before it works; each can be accepted or refused alone.

## Plain-language summary

1. **Five packs.** The rules that belong to one situation – building software, a repository's checks, conducting, outside systems, writing rules and skills – are each generated into one short file.
2. **One trigger instead of many.** An agent that starts building software reads one file of about 20,000 characters and has the nine rules that apply, instead of matching nine rows and finding nine places in a 93,000-character file.
3. **No rule moves.** `/RULES.md` stays the only place a rule is written and every rule keeps its number. The packs are generated from it, like the core files, and the preflight fails when one is stale.
4. **A shorter core.** The core lists the five packs and, of the rules, only those whose text is in neither the core nor a pack: 16 rows instead of 49.

## Current problem

Twenty-three situational rules are indexed one row each in the core. To follow them an agent must notice each row that applies and then read each rule out of a 93,346-character file, which in practice means reading the whole file: the handover prompts written in this brain say "Read /CONTRACT.md, /RULES.md", 147,322 characters, to get the five rules a conductor needs.

## Current wording and exact diff

### 1. `/RULES.md` – the paragraph after the rule index, and the new pack table

Current:

> `Applies when` says when an agent reads a rule's full text: `always` rules are in `/CORE-RULES.md`,
> which every writing session reads first with `/CORE.md` (CONTRACT §1); any other rule is read, in its
> canonical home, before acting in the situation named. Both files are generated from this file and
> `/CONTRACT.md` by `shared/skills/repository-preflight/scripts/core.py`, and the preflight fails when
> either is stale or too long for a host to show whole, or when a row here has no `Applies when`.

Proposed:

> `Applies when` says when an agent reads a rule's full text: `always` rules are in `/CORE-RULES.md`,
> which every writing session reads first with `/CORE.md` (CONTRACT §1); any other rule is read before
> acting in the situation named, in its rule pack when it has one and otherwise in its canonical home.
> The core files and the packs are generated from this file and `/CONTRACT.md` by
> `shared/skills/repository-preflight/scripts/core.py`, and the preflight fails when one of them is
> stale or too long for a host to show whole, or when a row here has no `Applies when`.
>
> Rule packs, in alphabetical order. A pack is a generated file that holds, verbatim, the rules of one
> situation, so that an agent entering the situation reads one short file instead of finding each rule
> here. A rule's wording still lives only in this file (`SMART-RULE-0007`); a rule may be in more than
> one pack; and `/CORE-RULES.md` lists a rule's own row only when its text is in neither the core nor a
> pack.
>
> | Pack | Applies when | Rules |
> |---|---|---|
> | `/rules/conducting.md` | before delegating work to another agent or running more than one session or worker; working cards between threads; a conductor thread starts or hands over; the owner raises another area's topic; before pushing merged code | `SMART-RULE-0024`, `SMART-RULE-0037`, `SMART-RULE-0043`, `SMART-RULE-0048` |
> | `/rules/outside-systems.md` | looking up a fact or identifier; working against an external system or its API; using a host plugin skill or its connector | `SMART-RULE-0005`, `SMART-RULE-0013`, `SMART-RULE-0017`, `SMART-RULE-0045` |
> | `/rules/rules-and-skills.md` | writing or changing a rule, a proposal, a skill's operating instructions, a host entry file or a pointer file, or anything in the mechanics or the skill library | `SMART-RULE-0002`, `SMART-RULE-0007`, `SMART-RULE-0008`, `SMART-RULE-0031` |
> | `/rules/software.md` | building or changing software in any project: code, a user interface, tests, sample data, a version, or a change someone who uses the system would notice | `SMART-RULE-0008`, `SMART-RULE-0015`, `SMART-RULE-0018`, `SMART-RULE-0020`, `SMART-RULE-0021`, `SMART-RULE-0022`, `SMART-RULE-0026`, `SMART-RULE-0041`, `SMART-RULE-0046` |
> | `/rules/software-checks.md` | creating a code repository or giving one its remote; setting up or changing a code repository's CI, checks, test runner or pre-push hook; a check fails or is slow | `SMART-RULE-0042`, `SMART-RULE-0049` |

Why: The paragraph says how a rule's text is found; it now names the pack. The table is the whole definition of the packs: the generator reads it and nothing else. `SMART-RULE-0008` is in two packs because sample data is software work and shareable files are rule-and-skill work.

### 2. `/CONTRACT.md` – §1, item 4, "Read by situation"

Current:

>    - **Read by situation.** Before acting in a situation named under `Applies when` in those tables, read that section of this contract, or that rule in its canonical home, in full. When it is unclear whether a row applies, read it.

Proposed:

>    - **Read by situation.** Before acting in a situation named under `Applies when` in those tables, read what the row names, in full: that section of this contract, that rule in its canonical home, or the rule pack – a file generated from `/RULES.md` that holds, verbatim, the rules of one situation. When it is unclear whether a row applies, read it.

Why: The contract said a rule is read "in its canonical home". A pack is a generated, verbatim copy, so the contract has to allow it, as it already allows the core files.

### 3. `/CONTRACT.md` – §15, the line on the core files

Current:

> - `/CORE.md` and `/CORE-RULES.md` are current with this contract and `/RULES.md` (`core.py check`)

Proposed:

> - `/CORE.md`, `/CORE-RULES.md` and the rule packs under `/rules/` are current with this contract and `/RULES.md` (`core.py check`)

Why: The integrity check that keeps the core files current now covers the packs.

### 4. `/CONTRACT.md` – front matter

Current:

> contract_version: 3.3.0

Proposed:

> contract_version: 3.4.0 (or the next minor version, if another contract change is accepted first)

Why: A minor version: behaviour is added and existing content stays valid (CONTRACT §13.3). The repository manifests of the three brain repositories record the new version.

### 5. `/shared/skills/repository-preflight/SKILL.md` – *Failure behaviour*, "the core is current" (only the changed part is shown)

Current:

> when `/CORE.md` or `/CORE-RULES.md` differs from what `scripts/core.py build` would write from `/CONTRACT.md` and `/RULES.md`, or when either is longer than 28,000 characters

Proposed:

> when `/CORE.md`, `/CORE-RULES.md` or a rule pack under `/rules/` differs from what `scripts/core.py build` would write from `/CONTRACT.md` and `/RULES.md`, when a pack names a rule that the index does not list, that has no text in `/RULES.md` or that always applies, when a file under `/rules/` is generated by no pack, or when any of these files is longer than 28,000 characters

Why: What the validator refuses, stated for the packs too.

## Measured

- `/CORE.md` and `/CORE-RULES.md` together, read first by every writing session: 52,231 characters today, 49,322 with this proposal alone, 43,341 with all six of 24 November.
- The packs: `/rules/conducting.md` 13,664, `/rules/outside-systems.md` 7,974, `/rules/rules-and-skills.md` 6,585, `/rules/software-checks.md` 6,287, `/rules/software.md` 20,777 characters; each under the limit of 28,000.

## Reason

`SMART-RULE-0003`, and reliability: one situation, one row, one file.

## Scope and consequences

Every agent in every host. The contract gains the rule pack as a third thing a row may name, and takes a minor version. `/CORE-RULES.md` changes shape: sections, packs, then the remaining rule rows.

## Risks, conflicts and migration

- **A pack is read where one rule would have done.** The software pack is about 20,000 characters where a single rule is 1,000 to 2,800. For a real software change most of its rules apply anyway; for a one-line fix the agent reads more than before.
- **A rule with a wider trigger is hidden in a pack.** Rules whose trigger is wider than any pack keep their own row: `SMART-RULE-0006`, `0016`, `0019`, `0028`, `0032`, `0033`, `0035` and `0047`.
- **Generated copies drift.** They cannot: the preflight fails on a stale pack, on a pack that names a rule wrongly, and on a file under `/rules/` that no pack generates.
- **Hosts with their own instructions to read `/RULES.md`.** Still correct, only longer than needed.

## Rollback

Remove the pack table and restore the paragraph, the two contract lines and the version; `core.py build` then writes the core as before, and the `/rules/` folder is deleted.

## Planned validation

The generator and its tests are on `main` and do nothing until the pack table exists. Measured on a copy with `core.py build`: the sizes below. After acceptance: the wording by script, `core.py build`, the manifests, the full preflight.
