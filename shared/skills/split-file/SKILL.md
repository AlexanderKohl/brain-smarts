---
id: skill-split-file
title: Split File
type: skill
schema_version: 0.2
contract: /CONTRACT.md
status: active
scope: shared
version: 0.1.1
script_paths:
  - /shared/skills/split-file/scripts/js/move.js
  - /shared/skills/split-file/scripts/js/move-methods.js
  - /shared/skills/split-file/scripts/js/move-block.js
  - /shared/skills/split-file/scripts/js/analyse.js
  - /shared/skills/split-file/scripts/js/shape.js
  - /shared/skills/split-file/scripts/py/move.py
  - /shared/skills/split-file/scripts/py/analyse.py
  - /shared/skills/split-file/scripts/py/shape.py
created: 2026-10-01T07:11:48+10:00
updated: 2026-10-01T07:11:48+10:00
owner: brain-owner
---

# Split File

Read `/CONTRACT.md` first.

The method and tools for shortening a large code file without changing what it does, as
`SMART-RULE-0041` requires: whole parts of the file move, unedited, into new files, and checks show the
rest of the program sees the same thing. A core skill: `SMART-RULE-0041` asks for exactly this kind of move.

## Purpose

Split a file that has grown past the size limit, or that mixes several jobs, so that:

- no line of moved code changes: every moved line appears in the new file exactly as it was;
- the only new code is wiring (an import, a require, a call), small enough to read in full;
- anything a move could change about behaviour is refused by the tool, not left to review;
- after each move, checks show the file's names, exports, classes and routes are the same, and every
  new file loads on its own.

The method comes from splitting four large files of one web app between 28 September and 1 October
2026 (one route file of 3,410 lines became 266 lines and ten modules), with the full test suite
passing after each split. It is not a refactoring method: code is moved first and improved later, in
separate commits.

## Allowed operations

- Read the target repository; write the new module and the wiring lines in the source file.
- Take snapshots in a temporary git worktree of a named ref, removed afterwards.
- Nothing else: no network (loading is checked for outbound connections, which are refused), no
  credentials, no commits (the agent commits, under `SMART-RULE-0009`).

## Required inputs

- The file to split, in a git repository with a clean working tree.
- A destination table (below), agreed before the first move.
- Optionally `split-file.config.json` at the repository root: the modules the shape check describes,
  and how to load them (see `scripts/js/shape.js` and `scripts/py/shape.py` for the keys).
- For JavaScript: `npm ci` in this folder once (the parser, pinned; `node_modules/` is not committed).
  Python needs only its standard library.

## Procedure

### 1. Draw up the destination table

Before moving anything, list where each part of the file goes: one row per new module, with the names
it takes, why they belong together, and what stays. Build it from the file's structure:

- `analyse.js <file>` / `analyse.py <file>`: every top-level statement with its lines and what it
  refers to;
- `--graph`: the definitions in dependency order with how many others use each (`--flag RE` marks names
  that need care, for example money code);
- `analyse.js <file> --class Name`: a class's members, the top-level names each uses and the `this.x`
  members each touches.

Group by what changes together. Move what others depend on first (shared helpers, types), so later
moves can import it. Code with money, identity or data deletion in it waits until tests pin its
behaviour (characterisation tests), even if the tools would move it.

### 2. Take the shape before, and plant faults

- `shape.js --out before.json` / `shape.py --out before.json`, or compare to a git ref with
  `--compare-ref <ref>` after each move.
- Once per repository, before trusting the check: plant a fault in a copy (change a function body,
  swap two routes, drop an export) and see the check fail. The skill's own tests do this on fictional
  apps; a new kind of project needs its own planted faults.

### 3. Move, one group per step

| Tool | Moves | Wiring it writes |
|---|---|---|
| `js/move.js <src> --to <mod> --names a,b` | whole top-level declarations of a CommonJS file | the new module's imports (copied, narrowed) and `module.exports`; one `require` back in the source |
| `js/move-methods.js <src> --class C --to <mod> --methods m1,m2` | whole methods of one class | a holder class in the new module; a loop in the source copying its descriptors onto `C.prototype` |
| `js/move-block.js <src> --to <mod> --register fn --lines A-B` | a contiguous run of statements (route registrations and the helpers only they use) | `function fn(router, { deps })` in the new module; one call where the run was |
| `py/move.py <src> --to <mod> --names a,b` | whole top-level definitions and assignments of a Python module | the new module's imports (copied, narrowed), `from __future__`, and the path setup they need; one `from <mod> import …` back in the source |
| `py/move.py … --no-load-back` | test classes of a test file | the same, without importing back; the new file may import helpers from the source |

`analyse.js <file> --range "start text" "end text"` finds a block's line range.

Each tool refuses rather than guess. It refuses when:

- moved code needs a name that stays behind (other than an import): the new module would have to load
  the source, a cycle – move that name too, or first;
- moved code uses what means something else in another file: `module`, `exports`, `__filename`, a
  top-level `this`; in Python `__name__`, `globals()`, and `__file__` other than to name the folder;
- a binding would be copied where it must be shared: a reassigned `let`/`var` passed to a block, a
  moved variable assigned later, Python `global`, a test that patches a moved name on the source module;
- a value would be read before it is set: a dependency declared after a block's call;
- code would run at a different moment: a moved initial value with effects (pass `--allow-load-order`
  only after checking the order does not matter);
- a range cuts a statement, a name is not found, or a statement declares more than was named;
- JavaScript members that cannot be copied as descriptors: constructors, static, private, getters,
  setters, methods using `super` or the class by name.

### 4. Check after each move

1. Syntax of every changed file (`node --check`, or the Python import in the next step).
2. The shape against the base: `--compare-ref <base>` also loads every changed or new file alone in a
   fresh process, which finds load-order cycles.
3. The tests that load the changed code; the full suite at the end of the split.
4. `git diff --color-moved=zebra` shows moved lines apart from new ones: the new ones should be wiring
   only.

A move that fails a check is undone (`git checkout` of the two files, delete the new one) and planned
again, never patched up.

### 5. Commit and record

- One commit per move or small group of moves, with the check results in the message.
- Lower the file's size record in the same commit (`SMART-RULE-0041`).
- Tests that read source text (rather than behaviour) follow the code: they read the new files; their
  assertions do not change.
- Merge the same day. A split branch left for days falls behind a busy branch and has to be redone.

## What the checks cannot see

- Which binding an unchanged function refers to after a move: covered by the refusals and the tests.
- Options of middleware made by factories the JavaScript shape does not know (it knows Express's own,
  `cors` and `multer`).
- In Python, `__module__` of moved functions and classes changes; code that reads it (pickle,
  logging's module field) is reviewed by hand.
- Timing and concurrency.

## Scripts or commands

```bash
npm ci --prefix shared/skills/split-file
node shared/skills/split-file/scripts/js/analyse.js src/big.js --graph
node shared/skills/split-file/scripts/js/move.js src/big.js --to bigHelpers --names a,b --ref TASK-0000-0001
node shared/skills/split-file/scripts/js/shape.js --root . --modules src/big.js --compare-ref origin/main
python shared/skills/split-file/scripts/py/move.py scripts/big.py --to big_parse --names parse,Token
python shared/skills/split-file/scripts/py/shape.py --root . --modules scripts/big.py --compare-ref HEAD
```

Tests, on fictional apps in `tests/fixtures/`:

```bash
npm test --prefix shared/skills/split-file
python -m unittest discover -s shared/skills/split-file/tests
```

## Outputs

The new module and the wiring lines in the source; a one-line summary of each move; shape snapshots as
JSON, and a comparison listing every difference and problem (exit code 1 when there is one).

## Permissions

Writes only the source file and the new module it names. No network, no credentials, no commits.

## Failure behaviour

- A refusal lists every reason at once and changes nothing (exit code 1).
- A file that cannot load is reported by the shape check as a problem, with the error's first line.
- The tools never partly write: the new module and the source are written together after all checks
  pass.

## Logging behaviour

The scripts write no logs. The commit message of each move records the command and the check results.

## State, knowledge and task update behaviour

The scripts update nothing in the brain. The split's plan, its destination table and its progress
belong to the owner's task for the split.
