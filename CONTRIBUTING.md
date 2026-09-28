---
id: contributing
title: Contributing
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-28T15:11:59+10:00
updated: 2026-09-28T15:11:59+10:00
owner: brain-owner
---

# Contributing

Read `/CONTRACT.md` first: it governs every change here, including yours.

## How to contribute

In the order you will meet them.

1. **Open an issue first** for anything larger than a fix, so the change can be agreed before it
   is built.
2. **Work from your own brain.** A change to a rule, the contract, a template or the preflight is
   *protected governance*: send it as a proposal file under `/governance/proposals/`, named by a
   slug, with **no rule number** (numbers are assigned when a proposal is accepted), a plain
   summary, the exact change, the reason, risks and a rollback (CONTRACT §13.2). The skill
   exchange (`/shared/skills/skill-exchange/`) prepares this for you.
3. **Keep it free of personal data.** No names, companies, addresses, identifiers or machine paths,
   in files or in commit messages. Examples use invented values and `example.com`. The preflight's
   personal-data check must pass (`SMART-RULE-0008`).
4. **Show it works.** Run `python shared/skills/repository-preflight/scripts/preflight.py` and the
   tests of any skill you changed; add a test that shows the new behaviour.
5. **Open a pull request.** The GitHub check runs the preflight again. The maintainer decides on
   each proposal; a declined one can come back with new evidence.

## Style

Write for someone who has not read the thread: plain words, en dashes rather than em dashes, and
every list in a deliberate order (`SMART-RULE-0027`).
