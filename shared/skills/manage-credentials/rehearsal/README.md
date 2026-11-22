---
id: manage-credentials-rehearsal-readme
title: Secrets store rehearsal
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-11-21T14:39:16+10:00
updated: 2026-11-22T16:08:17+10:00
owner: brain-owner
---

# Secrets store rehearsal

`rehearse.py` runs the synced secrets store end to end on one computer with invented secrets only,
as two throwaway computers, before the real cut-over. It never uses the live vault, the live
configuration, the owner's clones, checkpoint, recovery-package folder, keychain entries or running
Vault Agent, and it never calls a real provider or GitHub.

## How to run it

From the brain root (a session copy or the shared checkout):

```text
python shared/skills/manage-credentials/rehearsal/rehearse.py --check
python shared/skills/manage-credentials/rehearsal/rehearse.py
```

`--check` runs the guard and every step that touches no keychain entry, no long-lived process and
no cloud folder: it records the owner's baseline, exports two throwaway brains, writes their
configuration, makes two local bare repositories and the run certificate, and judges guard items
1 to 6 from inside each rehearsal environment. It reads no keychain entry. The full run adds the
store steps below; `--check` lists them by name, in order, after its clean-up line, and runs none of
them. `--commit REF` names the commit under test (default `HEAD`).

Each step prints one line: the step, `ok` or `FAILED`, and what was checked. No line carries a
value: invented values are derived from a random seed held in memory and compared by hash.
A failed guard item refuses the start and names the item (exit 2); a failed step stops the run
(exit 1); the clean-up always runs, lists what it removed and names anything left (exit 3).

## What it touches on this computer

| Place | What | Removed by the clean-up |
|---|---|---|
| `%TEMP%\brain-rehearsal-<id>` | two throwaway brains (`CONTRACT.md` and `shared/` from the commit), clones, bare remotes, checkpoints, agent homes, logs, the run certificate | yes, then checked absent |
| Keychain service `brain-secrets` (full run) | two entries, users `rehearsal-<id>@rehearsal-pc1-<id>` and `...-pc2-<id>` | yes, by exact user, never by service; checked absent, `cmdkey /list` checked for the id |
| `<OneDrive>\brain-rehearsal-<id>` (full run) | throwaway recovery packages | yes; OneDrive keeps deleted files in its online recycle bin (invented secrets, encrypted) |
| Named pipes (full run) | `PortableAIBrainVaultAgent-rehearsal-<id>-pc1`, `-pc2` | the agents are stopped; no pipe with the id may remain |
| 127.0.0.1 (full run) | the fake token endpoint, TLS with the run certificate | stopped |

The owner's agent state file (time and pid only), recovery-package folder and checkpoint folder are
recorded before the run and compared after it; any change is reported as left.

## How isolation works

- Every child process runs `python -I -B wrapper.py` with the rehearsal environment
  (`names.child_env`): `USERPROFILE`, `HOME` and `LOCALAPPDATA` in the run folder, an empty
  `GH_CONFIG_DIR`, no passphrase, GitHub token or proxy variables, Git author `rehearsal@example.com`.
- The wrapper, and only the wrapper, sets the agent's pipe name to the run's own and makes the token
  endpoint trust the run certificate alone; no product setting changes.
- The product code is the copy in each throwaway brain, so `find_brain_root` and the store
  configuration resolve there; both remotes are local bare repositories, so `gh` is never asked to
  create one.

## Steps of the full run

Rehearsal plan order: set-up of a throwaway person and store; a static secret put and read through
the agent from a second process; a first sign-in and the four sorts of refresh against the fake
endpoint (answered, nothing sent, refused, time-out) and `replace-signin`; personal and team
recovery packages; restore with its three refusals; a team store and a second computer enrolled
in the personal store and then the team store (two enrolments), with its own agent; migration from a throwaway old vault, the store-on refusal and the rollback;
the clean-up and its proof. The guard is checked again before each step.

Step 7, after the migration and while the store is on (plan R11, rules 3 and 5): the migrated
sign-in, whose entry also holds a static field, is deleted with `brain_secrets.py delete --entry E
--field F` (the entry name typed again through the confirm callback), checked gone from the store
with the static field's hash unchanged; a static field is then stored under that sign-in's name `F`
with `brain_secrets.py put`. The rollback's dry run must name that late field; the marker is checked
present just before the rollback and absent after it; after it the old vault holds the static
entry, the entry's static field and field `F` with the store's value, compared by hash (the late
field crosses the agent's pipe as `vault_restore_marked_static`).

## Files

- `rehearse.py` – entry point, step order, the session client
- `guard.py` – guard items 1 to 7 and the owner baseline
- `names.py` – the run's names and the child environment
- `wrapper.py` – the rehearsal-only wrapper and the guard's probe
- `steps.py` – the step commands run inside a rehearsal computer
- `tls.py` – the run certificate and the fake token endpoint
- `cleanup.py` – the clean-up and its proof
- `tests/test_rehearsal.py` – unit tests with fakes only
