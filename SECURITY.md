---
id: security-policy
title: Security policy
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-28T15:11:59+10:00
updated: 2026-09-28T15:11:59+10:00
owner: brain-owner
---

# Security policy

Read `/CONTRACT.md` first.

## Reporting a problem

Please report a security problem privately, through GitHub's **Report a vulnerability** button on
this repository's Security tab, not in a public issue. Say what you found, how to reproduce it and
what it could expose. You will get an answer, and a fix will be credited unless you would rather
it were not.

## What matters most here

In the order they would do most harm.

- The credential vault and its agent (`/shared/skills/manage-credentials/`): anything that could
  reveal a secret, the passphrase, or let another process read from an unlocked vault.
- The personal-data check (`/shared/skills/repository-preflight/`): anything that lets personal
  data reach a shareable repository unnoticed.
- The guard rails on outside systems in the contract and skills: anything that lets an agent write
  to an outside system without the owner confirming the target.

This repository holds no secrets and no personal data by design; if you find either, report it.
