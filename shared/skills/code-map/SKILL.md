---
id: skill-code-map
title: Code Map
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.4.2
script_paths:
  - /shared/skills/code-map/scripts/code-map.js
created: 2026-09-28T17:00:17+10:00
updated: 2026-09-28T17:00:17+10:00
owner: brain-owner
---

# Code Map

Read `/CONTRACT.md` first.

A candidate core skill. No rule requires it yet: whether one should is decided on the evidence of its
trial, and until then an agent may use it on any code repository and must not treat its checks as
mandatory.

## Purpose

Give agents and people an exact map of a code repository, read from the code by fixed rules and never
guessed, and fail a check when a link between its parts breaks. It answers:

- where something is and what a change touches (`show`, `find`);
- which UI calls reach which backend routes, which code reads which columns, settings and environment
  variables, and which data fields are read, compared, defaulted or set, including in templates;
- whether a value is produced anywhere in the repository at all, or comes from outside it;
- what the project's structure is today, as a generated inventory that cannot go stale (`report`).

It does not make agents noticeably cheaper at finding files: in a measured trial, reading and searching
code was about a fifth of an agent's context. Its gains are exact answers to cross-boundary and data
questions, and checks that catch broken links before release.

## Allowed operations

- Read every file of a repository (read-only), build the map in memory, print or write it.
- Write the committed records into the repository's record folder (`record`), and the inventory to a
  named file (`report --out`).
- Nothing else: no network, no database connection, no credentials, no change to source files.

## Required inputs

- A repository folder.
- Optionally `code-map.config.json` at its root, or `--config FILE`: declarations the project makes
  about itself – ignore and size-exempt patterns, the size limits, import aliases, URL-building
  functions for HTTP calls, settings loaders and settings files, the database dialect. Anything not
  declared is not guessed; the report lists what was not covered.

## Data sources

The repository's own files only. What the map reads, by language and framework:

| Area | Covered |
|---|---|
| Languages | JavaScript, TypeScript, JSX/TSX, Vue (script and template), HTML inline scripts, Python; other code files by size only |
| Templates | Vue templates, EJS, Handlebars, Mustache, Jinja/Nunjucks, Liquid |
| Backend routes | Express (routers, mounts, middleware order), Next.js pages and route handlers, Python `http.server` |
| UI | vue-router, React Router, Next.js pages; HTTP calls through `fetch`, `axios`, axios instances and declared wrappers |
| Data | Sequelize models and migrations, Prisma schema and migrations, Dexie stores, raw SQL in code and `.sql` files |
| Configuration | environment variables against example env files; settings keys from declared loaders against settings files |
| Messaging | socket.io events, browser-extension messages |

## Scripts or commands

```bash
cd <brain-root>/shared/skills/code-map
npm ci                                   # once: installs the three pinned parsers
node scripts/code-map.js show <name> --repo <repo>     # a file, function, route, column, setting, env variable or field
node scripts/code-map.js find <words…> --repo <repo>   # functions where the most of the words meet
node scripts/code-map.js check <repo>                  # exit 1 on a new failing finding
node scripts/code-map.js record <repo> --adopt         # first run: accept what exists today
node scripts/code-map.js record <repo>                 # after an intended interface change
node scripts/code-map.js report <repo> --out <file>    # the generated inventory, Markdown
node scripts/code-map.js build <repo> --out <file>     # the whole map, JSON
node scripts/code-map.js --version --verbose
npm test                                 # the skill's own tests
```

For an agent answering a question about code: `show` the names the question contains first; when a
field says **NOT SET anywhere in this repository**, the value comes from stored data, a request or
another system, so look where its object is loaded rather than searching further. Use `find` with the
question's own words when no name is known.

## Outputs

- `show` and `find`: plain text, capped per list.
- `check`: one line per check, the new findings, and what was not covered; exit 0 or 1 (2 for a usage
  or configuration error).
- The record folder (default `code-map/` in the repository): `sizes.json` (files over the limit and their
  recorded size, which only goes down), `interface.json` (exports, class methods, routes and middleware in
  order), `known-findings.json` (findings accepted at adoption).
- `report`: backend routes with handlers and callers, UI routes, environment variables, settings keys,
  models, tables and columns, oversized files, what was not resolved, and coverage.

## The checks

| Check | Fails | What it catches |
|---|---|---|
| `size` | yes | a code file over the limit (default 800 lines) that is new or grew |
| `cycles` | yes | files that load each other at startup (a require inside a function is not one) |
| `interface` | yes | exports, class methods or routes changed without updating the record in the same commit |
| `http` | yes | a UI call whose URL matches no backend route |
| `env` | yes | an environment variable read but missing from every example env file |
| `settings` | reports only (unless `settings.enforce`) | a settings key read with no default and no declaration |
| `columns` | yes | code naming a column its model or table does not define (migrations excluded) |

Unresolved items – a URL held in a variable, a computed key – never fail a check; they are listed.

## What is generated and what is written

If a script can produce a fact from the repository alone, it is generated here and not written by hand.
Behaviour is shown by tests. A project's `KNOWLEDGE.md` keeps only what the code cannot tell: reasons,
how outside systems behave (with the date checked), what things mean to the business, and history.

## Permissions

Read-only on the target repository, except the record folder and a named `--out` file. No network, no
credentials, no external side effects.

## Failure behaviour

- A file that fails to parse is listed under coverage with its first error; the rest of the map is built.
- A missing parser package is reported as `dependency: missing` with the install command; files in that
  language are mapped by size only.
- A name `show` does not know falls back to a word search, and says so.
- Anything the map declines to do is reported, never dropped silently.

## Logging behaviour

The script writes no logs. A session that uses the map for a decision cites the command and the map's
version (`--version --verbose`).

## State, knowledge and task update behaviour

The script updates nothing in the brain. The committed records live in the project repository and change
only through `record`. Findings that need work become the project's own tasks.
