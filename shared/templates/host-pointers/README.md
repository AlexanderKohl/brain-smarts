---
id: host-pointers-readme
title: Host Pointer and Settings Templates
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T13:00:00+10:00
updated: 2026-09-23T15:30:00+10:00
owner: brain-owner
---

# Host pointer and settings templates

Read `/CONTRACT.md` first. `/SETUP.md` steps E and F install these files; read them there for
the reasoning and the questions to ask.

Two kinds of file live here:

- **Pointers** make a host's session start from `/CONTRACT.md`. `SMART-RULE-0007` allows a host
  entry file to point at the portable bootstrap and nothing more, so each pointer names the
  contract and says it is only a pointer. Never add a behavioural rule to an installed copy; it
  belongs in `/RULES.md`, `/memory/RULES.md` or a node `RULES.md`.
- **Settings** let routine work run without a prompt while keeping a floor: no reading of secret
  files, no destructive Git, recursive deletes ask. External side effects are still confirmed
  with the owner per operation (CONTRACT §10.5) whatever the settings say.

## Placeholders

Alphabetical. Fill them from `/memory/OWNER.md`.

| Placeholder | Value |
|---|---|
| `<BRAIN_FOLDER>` | The brain root's folder name as seen from a sibling project repository (for example `brain`) |
| `<BRAIN_ROOT>` | `brain_root`, absolute |
| `<PROJECT_REPOS_ROOT>` | `project_repos_root`, absolute |

Write the paths with forward slashes in the Markdown pointers and the JSON settings (for example
`C:/dev/brain`), so a filled path such as `<BRAIN_ROOT>/CONTRACT.md` never mixes `\` and `/`.
The one exception is the Codex trust table in `codex.config.template.toml`: there `<BRAIN_ROOT>`
takes the form Codex itself records (on Windows `C:\dev\brain`, inside single quotes).

Pointer templates name no rule number: a pointer only points, so an installed copy cannot go
stale when rules are renumbered.

## Installing

- **Markdown pointers going outside the brain** (user-level files): copy the text below the
  closing `---` of the front matter; the front matter is for this repository's validator only.
- **Markdown pointers going inside the brain or a project repository** (`memory/AGENTS.md`, a
  project's `AGENTS.md` or `CLAUDE.md`): keep the front matter, remove the `template-` prefix
  from `id`, drop `install_to`, and set `created` and `updated` to the install time.
- **Settings files:** merge into an existing file key by key; never overwrite a file the person
  already has. `/SETUP.md` step F gives the merge command for JSON and the placement rule for
  TOML. JSON has no comments, so the reasons for each entry are in `/SETUP.md` step F. The allow
  list names `python -m unittest`, the runner every shared skill's tests use.

## Files

Alphabetical by file name.

| File | Install to | Kind |
|---|---|---|
| `claude-code-user.CLAUDE.template.md` | `~/.claude/CLAUDE.md` | Pointer |
| `claude-code.settings.local.template.json` | `<BRAIN_ROOT>/.claude/settings.local.json`, and each project repository's `.claude/settings.local.json` | Settings – routine allow list |
| `claude-code.user-settings.template.json` | merged into `~/.claude/settings.json` | Settings – deny and ask lists, default mode |
| `codex-user.AGENTS.template.md` | `~/.codex/AGENTS.md` | Pointer |
| `codex.config.template.toml` | merged into `~/.codex/config.toml` | Settings – approval and sandbox |
| `cursor-cli.cli-config.template.json` | merged into `~/.cursor/cli-config.json` | Settings – Cursor CLI allow and deny lists |
| `cursor-project-repo.brain-contract.mdc.template` | `<project repo>/.cursor/rules/brain-contract.mdc` | Pointer, only when Cursor does not read the project's `AGENTS.md` |
| `memory-root.AGENTS.template.md` | `<BRAIN_ROOT>/memory/AGENTS.md` | Pointer – hosts that stop at the Git root otherwise miss the contract |
| `project-repo.AGENTS.template.md` | `<project repo>/AGENTS.md` | Pointer |
| `project-repo.CLAUDE.template.md` | `<project repo>/CLAUDE.md` | Pointer |

## What is confirmed and what is not

Confirmed from working configuration files on a real install: Claude Code `permissions.allow`
and `permissions.deny` with `Bash(...)`, `PowerShell(...)`, `Read(...)` and `WebFetch(...)`
rules; Codex `[projects.'<path>'] trust_level`; Cursor CLI `permissions.allow`,
`permissions.deny` with `Shell(...)` entries and `approvalMode: "allowlist"`.

From host documentation, not re-checked offline – `verify against current host docs` before
relying on them: Claude Code `permissions.ask`, `permissions.defaultMode`,
`permissions.additionalDirectories` and `~` in path rules; Codex `approval_policy`,
`sandbox_mode` and `[sandbox_workspace_write]`; Cursor CLI `Read(...)` entries and whether
`Shell(<command> <subcommand>)` matches at subcommand level; Cursor `.mdc` rule front matter.

Pattern rules match command prefixes. They are guard rails against mistakes, not a sandbox: a
shell command can still reach a file that a `Read(...)` rule denies to the reading tool.

#### Folders

No immediate child folders.
