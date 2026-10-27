---
name: command-output
description: Shorten the long output of a recognised shell command – a test run, a build, an install, a long git diff or git log – before an agent reads it, keeping the head and the tail, every error line and the exit code, and saving the full output to a file the last line names. Works with any model and any AI host, through an after-command hook where the host has one and a wrapper where it does not.
metadata:
  id: skill-command-output
  title: Command Output
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: core
  owner: brain-owner
  version: 0.1.0
  canonical_source: /shared/skills/command-output
  script_paths:
    - /shared/skills/command-output/scripts/filtering.py
    - /shared/skills/command-output/scripts/hook.py
    - /shared/skills/command-output/scripts/run.py
  created: 2026-10-07T08:31:30+10:00
  updated: 2026-10-27T16:58:41+10:00
---

# Command Output

Read `/CONTRACT.md` first.

## Purpose

Most of what an agent reads in a coding session is the output of the commands it runs, and most of
that output is noise: hundreds of passing tests, download progress, unchanged diff context. This
skill shortens that output before the model reads it, so a session carries less and costs less,
without hiding what the agent needs: errors, failures, summaries and the exit code.

It does the same thing for every model and every host, because the filtering is fixed rules, not a
model. Hosts differ only in how the filter is attached (section *Hosts*).

## What it does to an output

1. **Leaves it alone** when it is short (under 80 lines and 8 000 characters), when the command is
   not one it recognises, when the command already narrows its own output (a pipe into `head`,
   `tail`, `grep`, `Select-String` and the like), when the result would save less than a fifth of
   it, or when the full output cannot be saved first. Leaving it alone means the agent sees exactly
   what it would have seen without the skill.
2. **Recognises the command** by its families in `scripts/filters.json` (alphabetical): `build`,
   `docker`, `git-diff`, `git-log`, `install` and `test`, each a list of program patterns matched at
   the start of any segment of the command line, after `cd ... &&`, variable assignments, a path to
   the program and an `.exe` or `.cmd` ending are set aside.
3. **Shortens it**: removes colour codes and progress-bar redraws, drops the family's noise lines
   (passing tests, download progress, unchanged diff context), collapses a run of three or more
   identical lines into the line and one marker, and, when it is still over the family's limit,
   keeps the head, the tail and, from the middle, every error line with a line before and two
   after, every line the family keeps (a diff's file and hunk headers, a test run's failure
   headers and summary), then warnings while the budget lasts. Every omitted stretch is marked with
   the number of lines it held; error lines beyond the budget are counted, never dropped silently.
4. **Saves the full output** to `/temp/command-output/<time>-<id>.log` with the command, the folder
   it ran in and the exit code, and ends the shortened output with one line:
   `[command-output: showing 35 of 175 lines (test filter, exit code 0). Full output: <path>]`.
   The exit code is named when the host reports it and left out when it does not.

An agent that needs more reads the named file with its ordinary file-reading tool; nothing else is
needed to get the full output back.

## Hosts

How the filter attaches, host by host (alphabetical). An after-command hook is preferred: the
command runs unchanged, so its exit code, its permission rules and the host's approval prompts are
untouched. `<brain_root>` is the `brain_root` in `/memory/OWNER.md`.

| Host | Attaches through | Verified |
|---|---|---|
| Aider | the wrapper, by rule | not run |
| Claude Code | `PostToolUse` hook, matcher `Bash\|PowerShell`, `updatedToolOutput` | live, version 2.1.288, 7 October 2026 |
| Cline, Roo Code | the wrapper, by rule | not run |
| Codex | `PostToolUse` hook, matcher `^Bash$`; `decision: "block"` with the shortened output as `reason` replaces the result | to the documented format; not run on Codex |
| Copilot CLI | `postToolUse` hook, `modifiedResult` | to the documented format; not run; whether the result is replaced or added to is unconfirmed |
| Copilot in VS Code, Cursor, OpenCode | the wrapper, by rule; their hooks can rewrite a command but cannot replace a shell command's output | not run |
| Gemini CLI | `AfterTool` hook, matcher `run_shell_command`; `decision: "deny"` with the shortened output as `reason` replaces the result | to the documented format; not run on Gemini CLI |

What the live Claude Code test established (7 October 2026, version 2.1.288):

- A successful command's medium output is replaced: `git log -n 14 --stat`, 8 643 characters,
  reached the model as 4 215 with the footer line.
- `PostToolUse` fires only for a command that succeeded. A failing command's output reaches the
  model in full, with its exit code, so on Claude Code the hook never shortens a failure.
- The hook input carries `stdout`, `stderr`, `interrupted`, `isImage` and `noOutputExpected`, and
  no exit code.
- Output too long for Claude Code (about 30 000 characters) is saved by Claude Code itself
  (`persistedOutputPath`) and shown to the model as a short preview of its head; a replacement does
  not change that, so the hook leaves such output to Claude Code.

### Registering the hooks

Each hook is registered once, in the host's **user** settings, so it covers the brain, every
session copy and every project repository on the computer. It is never put in a repository's
committed host file: that file is the same for every owner, and an owner's choice of skill does not
belong in it. `python shared/skills/command-output/scripts/hook.py settings <host>` prints the
exact entry with the shared checkout's absolute path. The entries are:

- **Claude Code**, merged into `~/.claude/settings.json`:

  ```json
  {"hooks": {"PostToolUse": [{"matcher": "Bash|PowerShell", "hooks": [{"type": "command",
    "command": "python <brain_root>/shared/skills/command-output/scripts/hook.py claude-code"}]}]}}
  ```

- **Codex**, in `~/.codex/config.toml` (and `[features] hooks = true` if the running version needs it):

  ```toml
  [[hooks.PostToolUse]]
  matcher = "^Bash$"
  [[hooks.PostToolUse.hooks]]
  type = "command"
  command = "python <brain_root>/shared/skills/command-output/scripts/hook.py codex"
  timeout = 30
  ```

- **Copilot CLI**, in `~/.copilot/hooks/command-output.json`:

  ```json
  {"version": 1, "hooks": {"postToolUse": [{"type": "command",
    "bash": "python <brain_root>/shared/skills/command-output/scripts/hook.py copilot-cli",
    "powershell": "python <brain_root>/shared/skills/command-output/scripts/hook.py copilot-cli"}]}}
  ```

- **Gemini CLI**, merged into `~/.gemini/settings.json`:

  ```json
  {"hooks": {"AfterTool": [{"matcher": "run_shell_command", "hooks": [{"type": "command",
    "command": "python <brain_root>/shared/skills/command-output/scripts/hook.py gemini-cli"}]}]}}
  ```

A host setting outside the brain is the owner's configuration: an agent proposes it and the owner
adds it, or tells the agent to.

### The wrapper

On a host without a hook that can replace output, the agent puts the wrapper in front of a noisy
command:

```bash
python <brain_root>/shared/skills/command-output/scripts/run.py -- npm test
python <brain_root>/shared/skills/command-output/scripts/run.py --shell bash -- "cd app && npm test"
python <brain_root>/shared/skills/command-output/scripts/run.py --shell powershell -- "Set-Location app; npm test"
```

It captures standard output and standard error together, in order, shortens long output (with the
generic filter for a command no family recognises, because asking for the wrapper is asking for the
filter) and exits with the command's own exit code; a program that cannot be started exits 127. On
Windows, `--shell bash` runs Git for Windows' bash, never WSL's, and a program such as `npm` is found
through `PATH` with its `.cmd` ending.

## Allowed operations

- Read the output a host passes to the hook, or the output of the command the wrapper runs.
- Write under `/temp/command-output/` (or `COMMAND_OUTPUT_DIR` when set): the saved full outputs,
  removed after seven days; `stats.jsonl`; `errors.log`.
- Run the one command the wrapper was given, as the agent would have run it.

## Required inputs

The hook: the host's name as its argument and the host's hook input on standard input. The
wrapper: the command after `--`, and optionally `--shell`.

## Data sources

The command's own output. No network, no credentials, no external system.

## Outputs

The shortened output (the hook in the host's own reply shape; the wrapper on standard output), or
nothing, which leaves the output as it was. The saved full output. One line per shortened output in
`stats.jsonl`: time, host, family, lines and characters before and after, exit code. It never holds
the command or the output.

## Permissions

None beyond the local folder above. The skill takes no external side effect, uses no credential and
never changes a command, its exit code or a host's permission decision. The saved outputs hold
whatever the command printed, which can include a secret a command echoes: they stay in the
ignored `/temp/` folder of one computer, are removed after seven days, and are never committed or
sent anywhere.

## Failure behaviour

- The hook fails open: any error leaves the output unchanged and appends the traceback to
  `errors.log`. An unknown host name exits 2 and changes nothing.
- When the full output cannot be saved, the output is left unchanged, so nothing is dropped that
  cannot be read back.
- `COMMAND_OUTPUT=off` in the environment turns the filter off without touching any host file.

## Logging behaviour

`stats.jsonl` and `errors.log` beside the saved outputs, both local scratch. Nothing is written to a
node's `LOG.md` by the skill.

## State, knowledge and task updates

None by the skill itself. A trial or a change of the rules is recorded in the node that runs it
(for this brain, `/memory/projects/brain-development/`); a quirk of a host's hooks found in use is
added to the table in *Hosts* with its date and version.

## Tuning

The families, their patterns and their limits are data in `scripts/filters.json`, described in its
`about` field. A change there is tested like code: add or adjust a case in
`scripts/tests/test_filtering.py` first.

## Tests

```bash
python -m unittest discover -s shared/skills/command-output/scripts/tests -v
```

They prove that short, unrecognised and self-narrowed output is untouched; that a failing test run
keeps every failure, its summary and its exit code; that the full output is saved and named; that
Windows line endings keep their text; that each host gets its own reply shape, including Claude
Code's observed one; that the hook fails open; and that the wrapper exits with the command's own
code. Every fixture is invented.

## Provenance

The approach – command-aware filtering of tool output, with the full output kept for retrieval –
follows the published RTK project (`rtk-ai/rtk`, Apache-2.0) and OmniRoute's account of it
(`diegosouzapw/OmniRoute`, MIT), reviewed on 7 October 2026. No code or filter file was copied; the
rules here were written for this skill. RTK's open issues about swallowed exit codes, hidden
failures and broken Windows hooks are why this skill filters after the command has run, never
rewrites the command, and leaves output alone whenever it cannot keep the full text.
