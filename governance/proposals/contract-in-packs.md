---
id: PROPOSAL-contract-in-packs
title: Rule packs also hold the contract sections of their situation
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: proposed
owner: brain-owner
created: 2026-11-26T12:20:00+10:00
updated: 2026-11-26T12:20:00+10:00
previous_contract_version: 3.6.0
new_contract_version: 3.7.0
target_files:
  - /CONTRACT.md
  - /CORE-RULES.md
  - /CORE.md
  - /README.md
  - /RULES.md
  - /rules/outside-systems.md
  - /rules/rules-and-skills.md
  - /shared/skills/repository-preflight/SKILL.md
---

# Rule packs also hold the contract sections of their situation

Read `/CONTRACT.md` first. The five new pack files it generates (`/rules/files-and-sources.md`, `/rules/node-files.md`,
`/rules/nodes.md`, `/rules/project-repositories.md`, `/rules/tasks.md`) are targets too; they are not listed in
`target_files` because they do not exist until it is applied. This proposal amends `/RULES.md` (the text above the pack table, and the
table), CONTRACT §1 and the validator's *Failure behaviour*. No rule and no contract section changes
its wording or its identifier (CONTRACT §13.2). The contract changes and takes the next minor version
at acceptance: 3.7.0 (CONTRACT §13.3).

## Plain-language summary

Today a thread reads the two core files, then one rule pack for its situation. The pack holds rules
only. The contract sections for the same situation, such as the section on tasks or the one on
project repositories, are still read one by one out of `/CONTRACT.md`, and in practice they are not
read at all.

After this change a pack holds both: the contract sections and the rules of one situation, word for
word. Five packs are new (files and sources, node files, nodes, project repositories, tasks) and two
gain sections (outside systems, rules and skills). Every contract section that does not always apply
is then in a pack. Nothing is reworded. `/CONTRACT.md` and `/RULES.md` stay the only places where
the text is written; the packs are generated from them and the preflight fails when one is out of
date.

## Current problem

Measured on 26 November 2026 from the transcripts of one host's threads: none of the three threads
started since rule packs came into force opened `/CONTRACT.md`. All three worked in a project
repository and created tasks, so CONTRACT §16 and §9 applied to each of them (`/CORE-RULES.md`, *When
to read the rest*). All three did read the pack of their situation. Before the packs, 15 of 28
threads changed code and 7 of those read no software rule; since, 3 of 3 read the software pack. A
short file named for the situation is read; a section inside a 62,000-character file is not.

## Current wording and exact diff

### 1. `/RULES.md`, the paragraph above the pack table

Current:

> Rule packs, in alphabetical order. A pack is a generated file that holds, verbatim, the rules of one
> situation, so that an agent entering the situation reads one short file instead of finding each rule
> here. A rule's wording still lives only in this file (`SMART-RULE-0007`); a rule may be in more than
> one pack; and `/CORE-RULES.md` lists a rule's own row only when its text is in neither the core nor a
> pack.

Proposed:

> Rule packs, in alphabetical order. A pack is a generated file that holds, verbatim, the contract
> sections and the rules of one situation, so that an agent entering the situation reads one short file
> instead of finding each section in `/CONTRACT.md` and each rule here. A section's wording still lives
> only in `/CONTRACT.md` and a rule's only in this file (`SMART-RULE-0007`); a section or a rule may be
> in more than one pack; `/CORE-RULES.md` lists a rule's own row only when its text is in neither the
> core nor a pack; and a contract section that a pack holds is read there, so its row in
> `/CORE-RULES.md` names the pack.

### 2. `/RULES.md`, the pack table

The third column's heading changes from `Rules` to `Contract sections and rules`. Two rows change and
five are added; the rows for conducting, software and software checks stay as they are.

Changed, current:

> | `/rules/outside-systems.md` | looking up a fact or identifier; working against an external system or its API; using a host plugin skill or its connector | `SMART-RULE-0005`, `SMART-RULE-0013`, `SMART-RULE-0017`, `SMART-RULE-0045` |
>
> | `/rules/rules-and-skills.md` | writing or changing a rule, a proposal, a skill's operating instructions, a host entry file or a pointer file, or anything in the mechanics or the skill library | `SMART-RULE-0002`, `SMART-RULE-0007`, `SMART-RULE-0008`, `SMART-RULE-0031` |

Changed, proposed:

> | `/rules/outside-systems.md` | looking up a fact or identifier; reading from or writing to an external system or its API; using a credential; using a host plugin skill or its connector | `§10`, `SMART-RULE-0005`, `SMART-RULE-0013`, `SMART-RULE-0017`, `SMART-RULE-0045` |
>
> | `/rules/rules-and-skills.md` | writing or changing the contract, a rule, a proposal, a governance template, a bootstrap file, a skill or its operating instructions, a host entry file or a pointer file, or anything in the mechanics or the skill library; accepting or applying such a change; numbering a rule or naming a proposal | `§10`, `§13.2`, `§13.3`, `SMART-RULE-0002`, `SMART-RULE-0007`, `SMART-RULE-0008`, `SMART-RULE-0031` |

Added, each in its alphabetical place:

> | `/rules/files-and-sources.md` | a file arrives to be kept, or is taken from the inbox; content arrives from outside the owner's own words: a file, an e-mail, a web page, a tool's output | `§11` |
>
> | `/rules/node-files.md` | writing a node's `README.md`, `RULES.md`, `STATE.md`, `LOG.md` or `KNOWLEDGE.md`; creating a Markdown file, or changing front matter or a log heading; writing a checkpoint, or the context was compacted; before finishing a substantive update | `§4`, `§8`, `§15`, `SMART-RULE-0019` |
>
> | `/rules/nodes.md` | creating a node, moving one into its own repository, or deciding where an item belongs; creating a durable item, or copying one; declaring a dependency, or configuring a shared skill for a node | `§3.1`, `§3.2`, `§3.3`, `§7`, `§12` |
>
> | `/rules/project-repositories.md` | working in a project repository: reading or writing its `brain/` folder, committing or pushing there, or joining one | `§16` |
>
> | `/rules/tasks.md` | creating, changing or closing a task; a project without a board gains its fifth open task or a third active branch | `§9`, `SMART-RULE-0035` |

The table of contract sections in `/RULES.md` (*Contract sections and when to read them*) does not
change: each section keeps its `Applies when`.

### 3. CONTRACT §1, *Read by situation*

Current:

> **Read by situation.** Before acting in a situation named under `Applies when` in those tables, read what the row names, in full: that section of this contract, that rule in its canonical home, or the rule pack – a file generated from `/RULES.md` that holds, verbatim, the rules of one situation. When it is unclear whether a row applies, read it.

Proposed:

> **Read by situation.** Before acting in a situation named under `Applies when` in those tables, read what the row names, in full: the rule pack – a file generated from this contract and `/RULES.md` that holds, verbatim, the contract sections and the rules of one situation – or, for a section or a rule that no pack holds, that section of this contract or that rule in its canonical home. When it is unclear whether a row applies, read it.

### 4. The validator's *Failure behaviour*, the line *the core is current*

Current, the part that changes:

> when a pack names a rule that the index does not list, that has no text in `/RULES.md` or that always applies, when a file under `/rules/` is generated by no pack,

Proposed:

> when a pack names a rule that the index does not list, that has no text in `/RULES.md` or that always applies, when a pack names a contract section that the section table does not list or that always applies, when a pack names fewer than two rules and no contract section, when a file under `/rules/` is generated by no pack,

The check "fewer than two rules" is in the validator's code today and is missing from this line; the
proposed line states it, and lets a pack that holds a contract section stand with fewer than two
rules.

### 5. Generated files and the root README

`core.py build` regenerates `/CORE.md`, `/CORE-RULES.md` and the packs. In `/CORE-RULES.md` the row of
a contract section that a pack holds reads `in` and the pack's file name where its `Applies when`
stood, because the pack's own row now says when; the row of `SMART-RULE-0019` leaves the list of rules
that are in no pack. The `rules/` entry of `/README.md` says that a pack holds contract sections and
rules, from both files.

## Measured

Generated on 26 November 2026 from the proposed text, by `core.py` with the change below, on a copy:

| File | Now | Proposed |
|---|---|---|
| `/CORE.md` | 18,851 | 18,943 |
| `/CORE-RULES.md` | 24,490 | 24,927 |
| `/rules/conducting.md` | 13,664 | 13,664 |
| `/rules/files-and-sources.md` | – | 4,865 |
| `/rules/node-files.md` | – | 16,654 |
| `/rules/nodes.md` | – | 6,557 |
| `/rules/outside-systems.md` | 7,974 | 10,704 |
| `/rules/project-repositories.md` | – | 5,268 |
| `/rules/rules-and-skills.md` | 6,585 | 15,977 |
| `/rules/software-checks.md` | 6,287 | 6,287 |
| `/rules/software.md` | 21,184 | 21,184 |
| `/rules/tasks.md` | – | 6,262 |

Every file is under the 28,000 characters a host shows whole. What a thread reads before it works
does not change: the two core files. What it reads by situation grows by the sections it was already
meant to read: a thread that changes code in a project repository and creates a task reads the
software pack as today, and 11,530 characters more in two short files.

## Reason

A rule that is not read does not govern. The packs showed that a short file named for a situation is
read where a section of a long file is not, and the contract's situational sections are the part
still left in the long file.

## Scope and consequences

- Every agent in every host, for every piece of work that falls under a pack's `Applies when`.
- A thread reads more by situation than it does today in practice, and exactly what the contract
  already required.
- `SMART-RULE-0019` is read in `/rules/node-files.md`. After a compaction a thread re-reads the two
  core files, the owner rules, its own handover entry and the rules of its work in flight, as that
  rule says; the pack is where it finds the rule.
- The file names `/CORE.md` and `/CORE-RULES.md` and the folder `/rules/` do not change here. Whether
  the generated files should be named after their sources is a separate question for the owner.

## Risks, conflicts and migration

- **`/rules/node-files.md` applies to most writing sessions**, because most of them write a state
  file or a log. At 16,654 characters it is the largest new read. Its sections could instead be
  marked `always` and join `/CORE.md`, which would then be 27,737 characters, at the limit; the pack
  keeps the first read as it is.
- **A pack row's `Applies when` is the union of its sections' and rules' own.** A reader of
  `/CORE-RULES.md` no longer sees a section's own `Applies when`, only the pack's; `/RULES.md` keeps
  both.
- **No migration of content.** No file an owner wrote changes. Another brain that follows the
  mechanics receives the new packs with its next merge, and its preflight builds them.
- **The generator changes:** `core.py` reads `§` numbers in the pack table, writes the sections into
  the pack ahead of the rules, and marks a held section's row in `/CORE-RULES.md`. The change is
  written and rehearsed, and is applied with this proposal, not before it: until then a `§` in the
  pack table is ignored.

## Rollback

Revert the commit that applies this proposal in the mechanics repository and run `core.py build`; the
five new pack files are then generated by no row and the preflight names them for deletion. The
contract returns to 3.6.0.

## Planned validation

- The validator's tests, with new cases: a pack that names a section holds it word for word; a pack
  with one section and no rule passes; a pack that names a section which always applies, or one the
  table does not list, fails; a held section's row in `/CORE-RULES.md` names its pack.
- `core.py check` and the full preflight on the result; every generated file under 28,000 characters.
- A week after acceptance, the same measurement as above: which packs threads read, and whether any
  thread that worked in a project repository or created a task went without its pack.
