---
id: template-library-readme
title: Skill Library
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: brain-owner
---

# Skill Library

Read `/CONTRACT.md` first. This repository is one layer of a portable AI brain: it is checked out
beneath the brain root at `/library/`, beside the mechanics repository that holds the contract
and the owner's memory at `/memory/` (CONTRACT §3.4, §3.5). It does nothing on its own: its
skills use the brain's core skills, the vault above all, and read the owner's configuration from
memory.

It holds the optional skills – access to an outside system, or a way of working an owner may
choose. The skills the brain itself depends on stay in the mechanics at `/shared/skills/`. An
owner switches a library skill on by listing it in `active_skills` in `/memory/OWNER.md`, and
may merge skills from other people's libraries into their own (`SMART-RULE-0032`).

This library started empty, from `/shared/templates/library-skeleton/` (`/SETUP.md` step B3a),
because the library of the person who shared the smarts was not readable at setup. It has no
`upstream` remote. To take in that library later, ask its owner for read access, then add it
with push disabled and merge it in:

```bash
cd <brain_root>/library
git remote add upstream <library address>
git remote set-url --push upstream DISABLED
git fetch upstream
git merge --allow-unrelated-histories upstream/main
```

A skill written here, or installed from someone else's library (`/shared/skills/skill-exchange/`),
goes under `skills/` and is listed in `skills/README.md`.

It holds no personal data (`SMART-RULE-0008`): the validator's personal-data check runs on it
before every commit.

#### Folders

##### `skills/`

Contains one folder per library skill, each with its `SKILL.md`, scripts, tests and generic
knowledge. Canonical; shareable. See `skills/README.md` for the list.
