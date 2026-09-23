---
id: template-owner-profile
title: Owner Profile
type: owner_profile
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
owner_name: FULL_NAME
owner_short_name: OWNER_SHORT_NAME
timezone: IANA_ZONE (+HH:MM)
brain_root: ABSOLUTE_BRAIN_ROOT
github_account: GITHUB_ACCOUNT
project_repos_root: ABSOLUTE_PROJECT_REPOS_ROOT
default_host: DEFAULT_HOST
---

# Owner Profile

Read `/CONTRACT.md` first.

This file names the person the brain works for (CONTRACT §3.6). Mechanics files say "the
owner" and set `owner: brain-owner`; both mean the person named here. Replace every
upper-case placeholder in the front matter; agents read the concrete values from here instead
of repeating them.

| Field | Used for |
|---|---|
| `brain_root` | The `cd` in owner-facing shell commands (`RULE-2026-0013`); `/` in repository-root paths |
| `default_host` | The host and tool the owner usually works in |
| `github_account` | Owner of the brain and project repositories |
| `owner_name` | Formal attribution |
| `owner_short_name` | Conversation and memory records |
| `project_repos_root` | Where project repositories are checked out (CONTRACT §16) |
| `timezone` | The offset on every timestamp the owner's agents write |

Rows are alphabetical by field name.
