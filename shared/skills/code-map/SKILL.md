---
id: skill-code-map
title: Code Map
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.5.1
script_paths:
  - /shared/skills/code-map/scripts/code-map.js
created: 2026-09-28T17:00:17+10:00
updated: 2026-09-28T21:39:50+10:00
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
- what the project's structure is today, as a generated inventory that cannot go stale (`report`);
- what code is no longer used: files, exports, declarations, Vue state and example env lines (`unused`,
  report only).

What it was measured to do (trial of 28 September 2026, one repository of about 480 code files, 28 agent
runs and 156 replayed commits; evidence in the owner's brain-development records): agents with the map
were as accurate as without it and used a median 11% fewer tokens and 8% less time, inside the run-to-run
noise on most questions; the largest saving was on a data question (38% fewer tokens). Replayed over six
weeks of commits, the checks raised 13 new findings: 8 real but minor (environment variables missing from
the example file), 4 false alarms, 1 harmless, and no functional broken link. The size check would have
stopped 72 of 155 commits. So its value is exact answers to cross-boundary and data questions, and cheap
checks – not a large saving for agents.

## Allowed operations

- Read every file of a repository (read-only), build the map in memory, print or write it.
- Write the committed records into the repository's record folder (`record`), and the inventory to a
  named file (`report --out`).
- Nothing else: no network, no database connection, no credentials, no change to source files.

## Required inputs

- A repository folder.
- Optionally `code-map.config.json` at its root, or `--config FILE`: declarations the project makes
  about itself – ignore and size-exempt patterns, the size limits, import aliases, URL-building
  functions for HTTP calls, settings loaders and settings files, the database dialect, and for the
  unused report the files the project starts in ways the map cannot see (`unused.entries`) and files
  to leave out (`unused.ignore`). Anything not declared is not guessed; the report lists what was not
  covered.

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
node scripts/code-map.js unused <repo> [--only files,exports] [--json]   # code no longer used; never fails
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
  models, tables and columns, oversized files, unused code, what was not resolved, and coverage.
- `unused`: each kind with its items (file, line, name, why) and what the report leaves out; exit 0.

## The checks

| Check | Fails | What it catches |
|---|---|---|
| `size` | yes | a code file over the limit (default 800 lines) that is new or grew |
| `cycles` | yes | files that load each other at startup (a require inside a function is not one) |
| `interface` | yes | exports, class methods or routes changed without updating the record in the same commit |
| `http` | yes | a UI call whose URL matches no backend route |
| `env` | yes | an environment variable read but missing from every example env file; reads through helper functions such as `readEnv('X')` count, and retired fallback names passed as a list need not be listed |
| `settings` | reports only (unless `settings.enforce`) | a settings key read with no default and no declaration |
| `columns` | yes | code naming a column its model or table does not define (migrations excluded) |

Unresolved items – a URL held in a variable, a computed key – never fail a check; they are listed.

## The unused report

`unused` lists code the repository no longer uses. It never fails a run: each kind has blind spots,
listed below and printed with the report.

| Kind | Listed when | Counts as used, so not listed |
|---|---|---|
| `files` | no entry point reaches the file through imports | entry points: package `scripts` (paths, globs, folders), `main`, `bin` and `exports`; tests; tool configuration (`*.config.*`); migrations and seeders; `<script src>` in HTML pages; browser-extension manifests; Next.js route files; `unused.entries`. Reached by: imports of any kind, scripts started by file name (`execFileSync(node, [path.join(__dirname, 'x.js')])`, `fork`, `spawn`, `importScripts`, `new Worker`), and a loader that requires every file of its folder (`readdirSync(__dirname)`) |
| `exports` | no file imports the name, reads it from the whole module (`m.name`) or re-exports it | a module passed on whole counts as fully used; exports of entry points, Vue components and unreached files are not listed |
| `declarations` | a module-level function, class or variable its own file never reads (or only sets) | exported names, imports, names starting with `_`, and scripts with no import or export (their names are globals) |
| `vue-state` | a `<script setup>` binding neither the script nor the template uses | template expressions, component tags, template `ref`s, `defineProps` and the other compiler macros; commented-out markup does not count |
| `env` | an example env line no code reads and no other file mentions | reads through `process.env`, `import.meta.env` and helper functions (`readEnv('X')`, including names passed as a list) |

Not covered: imports never used, TypeScript types, Vue options-API state, packages, Python.

Measured on extract-bill-api (`testing` `44e7b8a`, 28 September 2026), every finding or a sample checked
by hand:

| Kind | Found | Real |
|---|---|---|
| `files` | 14; 5 with one `unused.entries` line for extension scripts loaded by name at run time | 5 of 5 |
| `exports` | 157 | a random 20 of 20; on the Knip trial's hand-checked 20, it found 10 of the 11 real and none of the 9 false alarms |
| `declarations` | 4 | 4 of 4 (one a latent bug: an expiry time that is set and never read) |
| `vue-state` | 32 | 32 of 32 |
| `env` | 1 | 1 of 1 (was 31 before helper reads were recognised) |

Knip 6.38.0 on the same code reached 5 of 8 for files, 6 of 13 for packages and 11 of 20 for exports. The
three ideas taken from it – entry points instead of "nobody imports it", member reads of whole modules,
scripts started by name – are what make the difference here. Evidence: the owner's
brain-development records (Knip trial of 28 September 2026).

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
