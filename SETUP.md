---
id: brain-setup-guide
title: Guided Setup for a New Brain
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T13:00:00+10:00
updated: 2026-09-23T18:00:00+10:00
owner: brain-owner
skill_refs:
  - /shared/skills/manage-credentials
  - /shared/skills/repository-preflight
template_refs:
  - /shared/templates/memory-skeleton
  - /shared/templates/host-pointers
---

# Guided setup for a new brain

Read `/CONTRACT.md` first. This file is written for the **AI agent** that sets a person up. The
agent follows it as a resumable interview: it runs every check it can itself, asks the person
only what it cannot find out, and hands the person the few steps that must stay in human hands.
Until `/memory/OWNER.md` exists the person is called "the person"; afterwards they are "the
owner" (CONTRACT §3.6).

Steps are in the order they must happen. Each step has a stable ID (`A` to `H`, with numbered
sub-steps) that the progress record uses.

## 1. Conventions for the agent

### 1.1 How to ask

Every question carries a suggested answer (`RULE-2026-0018`). When several answers are valid,
number them and mark one as recommended, so the person can reply "yes" or a number. They may
always answer something else. Multi-select questions accept a list such as `1, 3, 7`. In
voice mode, ask one question at a time.

The form used below:

> **Ask:** the question
> 1. option (recommended)
> 2. option
>
> **Suggested reply:** `1`

Ask only what you cannot detect. Run the detection first and offer what you found as the
suggestion.

### 1.2 Who does what

Each step splits the work into **Agent does** and **You do** (addressed to the person). The
agent never takes over a "You do" item, even when the host would let it. These stay with the
person without exception:

1. **Choosing and typing the vault passphrase.** It is typed only into the vault's own hidden
   prompt, in a terminal the person opens themselves. It never appears in chat, in a file, in
   a command argument or in an environment variable (`/shared/skills/manage-credentials/`).
2. **Pasting a secret.** Client secrets, API tokens and the ABR GUID are pasted only into the
   hidden prompt of `vault_credentials.py put-entry`, run by the person in their own terminal.
   If a secret is pasted into chat by mistake, stop, tell the person it must be rotated at the
   provider, and do not store or repeat it.
3. **Registering an application** at an external provider (Google Cloud, Xero, HighLevel,
   Railway, ABR) and accepting that provider's terms.
4. **Approving an OAuth consent screen** and signing in to a provider.
5. **Signing in to GitHub** (`gh auth login`) and to the AI host.

The agent may show the **last four characters** of a stored secret for confirmation, never more.

### 1.3 Safety floor during setup

- Before a command that installs software, creates a repository, creates a scheduled task or
  changes host settings, say what it changes and wait for a yes. These are side effects on the
  person's machine or accounts.
- Before creating a GitHub repository, confirm the named GitHub account for that operation
  (CONTRACT §10.5); the person may have several.
- Give every shell command with an explicit `cd` first (`RULE-2026-0013`). Before
  `/memory/OWNER.md` exists, use the chosen brain root; afterwards read `brain_root` from it.
- Never write owner content into the mechanics repository (CONTRACT §3.4). Everything about the
  person goes under `/memory/`.

## 2. Resuming

### 2.1 The progress record

Once the memory exists (step B4), progress lives under `## Setup` in `/memory/STATE.md`. Keep
one row per step, in setup order (the order a reader follows), and replace a row when its status
changes; history goes to `/memory/LOG.md`.

```markdown
## Setup

Guide: `/SETUP.md`. Rows are in setup order. Status: `pending`, `in_progress`, `waiting_on_owner`,
`done`, `skipped`, `blocked`.

| Step | Status | Machine | Updated | Note |
|---|---|---|---|---|
| A prerequisites | done | EXAMPLE-LAPTOP | 2026-10-01T09:12:00+10:00 | git 2.51, Python 3.12, gh 2.80, Claude Code |
| B3 smarts repository | done | EXAMPLE-LAPTOP | 2026-10-01T09:20:00+10:00 | origin = own private copy; upstream push disabled |
| D xero-access | waiting_on_owner | EXAMPLE-LAPTOP | 2026-10-01T10:05:00+10:00 | owner registering the Xero app |
```

`Machine` is the computer's name (`hostname`): prerequisites, the vault, host wiring and
settings are per machine, while the repositories and skill choices are per owner.

### 2.2 Resume procedure

1. Find the brain root (walk up to `CONTRACT.md`). If none is found, start at step A.
2. If `/memory/STATE.md` has a `## Setup` section, continue from the first row that is not
   `done` or `skipped` on this machine. For a new machine, re-run the per-machine steps (A, D
   vault and connections, E, F, G) and skip the per-owner ones already `done`.
3. If memory does not exist yet, detect progress with each step's **Done when** check below,
   then continue from the first step that fails its check. Record the detected results as soon
   as step B4 creates `/memory/STATE.md`.
4. Tell the person in one line where you are resuming, then carry on.

## 3. Step A – Prerequisites

**Done when:** every check below passes on this machine.

**Agent does:** runs each check itself and reports one line per tool. For each missing or too
old tool, offers the install command, runs it after a yes, and checks again. A new terminal is
often needed before a freshly installed tool is on `PATH`; say so when a check still fails.

Rows are in install order: the later tools depend on the earlier ones.

| Tool | Minimum | Check |
|---|---|---|
| Git | any 2.x | `git --version` |
| Python | 3.11 | `python --version` (Windows: also `py -3 --version`) |
| GitHub CLI | any 2.x | `gh --version` |
| The AI host | current | Claude Code: `claude --version`; Codex: `codex --version`; Cursor: `cursor --version` or the app's About box |

### A.1 Windows (first)

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.12 -e
winget install --id GitHub.cli -e
```

Host, one of (install commands change between releases – `verify against current host docs`):

```powershell
irm https://claude.ai/install.ps1 | iex        # Claude Code, native installer
npm install -g @openai/codex                   # Codex CLI (needs Node.js: winget install --id OpenJS.NodeJS.LTS -e)
winget install --id Anysphere.Cursor -e        # Cursor
```

Windows notes:

- If `python` opens the Microsoft Store, the Store alias is shadowing the real install. Ask the
  person to turn off **Settings → Apps → Advanced app settings → App execution aliases →
  python.exe / python3.exe**, or use `py -3` in every command.
- The vault tray (`vault_tray.py`) needs `pythonw`, which the python.org and winget installs
  provide.

### A.2 macOS

```bash
brew install git python@3.12 gh
curl -fsSL https://claude.ai/install.sh | bash   # Claude Code – verify against current host docs
brew install --cask cursor                        # Cursor, if chosen
npm install -g @openai/codex                      # Codex, if chosen (needs node: brew install node)
```

Without Homebrew, install it first from https://brew.sh (the person runs the installer; it asks
for their macOS password).

### A.3 Linux (Debian or Ubuntu)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip
```

The GitHub CLI comes from GitHub's own package repository (see https://cli.github.com, "Linux
installation"). `sudo` asks for the person's password: the person runs these commands, the agent
does not.

### A.4 Python packages

Installed per skill in step D, never globally ahead of need. If the person prefers a virtual
environment, create it at `<brain_root>/.venv` (already ignored by Git) and use its `python`
in every command.

## 4. Step B – Your two repositories

The brain is three layers (CONTRACT §3.4). The person gets:

- **Smarts** – their own private copy of the mechanics repository, with the original kept as
  the `upstream` remote so improvements can be pulled in. Checked out at the brain root.
- **Memory** – a new private repository made from `/shared/templates/memory-skeleton/`,
  checked out at `<brain_root>/memory/`.
- **Project repositories** – later, one per large body of work, as siblings under
  `project_repos_root` (CONTRACT §7.1, §16). None is needed to finish setup.

### B1. GitHub sign-in

**Done when:** `gh auth status` reports a signed-in account.

**You do:** run `gh auth login`, choose GitHub.com, HTTPS, and "Login with a web browser", then
enter the one-time code in the browser.

**Agent does:** runs `gh auth status` and `gh api user --jq .login` to learn the account name.
If more than one account is signed in, ask which one owns the brain:

> **Ask:** Which GitHub account should own your brain repositories?
> 1. `<detected active account>` (recommended)
> 2. `<other detected account>`
>
> **Suggested reply:** `1`

### B2. Git identity

**Done when:** `git config --global user.name` and `git config --global user.email` both print a
value.

**Agent does:** if either is empty, suggest the name from `gh api user --jq .name` and GitHub's
private no-reply address (`<id>+<login>@users.noreply.github.com`, from
`gh api user --jq .id`), and set them after a yes.

> **Ask:** Use these for your commits?
> 1. Name `<detected name>`, email GitHub no-reply address (recommended – keeps your real
>    address out of commit history)
> 2. Name `<detected name>`, a different email you give me
>
> **Suggested reply:** `1`

### B3. Your smarts repository

**Done when:** the brain root holds `CONTRACT.md`, `git remote -v` there shows `origin` pointing
at the person's own repository and `upstream` at the original, and
`git config core.hooksPath` prints `.githooks`.

> **Ask:** How should your copy of the smarts be made?
> 1. Private copy with the original as `upstream` (recommended – works when the original is
>    private, keeps shared history so `git merge upstream/main` stays simple)
> 2. GitHub fork (only possible when the original allows forking; a fork of a private
>    repository disappears if your access to the original is removed)
> 3. "Use this template" (only when the original is marked as a template; starts a fresh
>    history, so every later update from the original needs
>    `--allow-unrelated-histories` and manual conflict work)
>
> **Suggested reply:** `1`

> **Ask:** Where should the brain live on this computer?
> 1. `C:\dev\brain` on Windows, `~/dev/brain` on macOS and Linux (recommended)
> 2. Another folder you name
>
> **Suggested reply:** `1`

**Agent does**, for option 1 after confirming the GitHub account (Windows shown; on macOS and
Linux use `~/dev` and forward slashes):

```powershell
cd C:\dev
git clone <SMARTS_REPO_URL> brain
cd C:\dev\brain
git remote rename origin upstream
git remote set-url --push upstream DISABLED
gh repo create <github_account>/brain-smarts --private --source . --remote origin --push
git config core.hooksPath .githooks
```

`set-url --push upstream DISABLED` makes an accidental push to the original fail instead of
landing. The pre-commit hook refuses any `memory/` path and a commit that mixes governance with
other files.

For option 2: `gh repo fork <SMARTS_REPO_URL> --clone --remote` (the GitHub CLI names the
original `upstream` itself), then the same `set-url --push` and `core.hooksPath` lines. For
option 3: the person clicks **Use this template** on the original's GitHub page, chooses
**Private**, and the agent clones the new repository and adds `upstream` by hand.

If the person already cloned the smarts to follow the seed prompt, keep that checkout and only
fix the remotes.

### B4. Your memory repository

**Done when:** `<brain_root>/memory/OWNER.md` exists with no upper-case placeholder left in its
front matter, and `<brain_root>/memory/` is its own Git repository with an `origin` remote.

**Agent does:**

1. Copy the skeleton:

   ```powershell
   cd C:\dev\brain
   Copy-Item -Recurse shared\templates\memory-skeleton memory
   ```

   macOS and Linux: `cd ~/dev/brain && cp -R shared/templates/memory-skeleton memory`.
2. Run the owner-profile interview (B5) and write the answers into `memory/OWNER.md`.
3. In every file under `memory/`: replace `OWNER_SHORT_NAME`, remove the `template-` prefix from
   each `id`, and set `created`, `updated` and the first `LOG.md` heading to the current time in
   the owner's timezone (CONTRACT §8.2).
4. Add the `## Setup` section to `memory/STATE.md` (section 2.1) with every step detected so far.
5. Copy `/shared/templates/host-pointers/memory-root.AGENTS.template.md` to
   `memory/AGENTS.md`, drop the `template-` prefix from its `id`, and list it in
   `memory/README.md` Navigation (step E explains why).
6. Run the validator from the brain root and fix every error:

   ```powershell
   cd C:\dev\brain
   python shared/skills/repository-preflight/scripts/preflight.py --root .
   ```

7. After confirming the GitHub account, create the repository and the first commit:

   ```powershell
   cd C:\dev\brain\memory
   git init -b main
   git add -A
   git commit -m "<host> <model>: memory created from the skeleton"
   gh repo create <github_account>/brain-memory --private --source . --remote origin --push
   ```

   `git add -A` is safe here only because the folder is brand new and holds nothing else; from
   now on stage named paths only (`RULE-2026-0017`).

### B5. Owner profile interview

Fill every field of `/memory/OWNER.md` front matter (CONTRACT §3.6). Detect first, then ask
once, showing all detected values together; the person corrects any line.

| Field | Detect with | Suggested answer |
|---|---|---|
| `brain_root` | the folder chosen in B3 | that folder, absolute |
| `default_host` | the host running this setup | for example `Claude Code desktop` or `Codex CLI` |
| `github_account` | `gh api user --jq .login` | the account confirmed in B1 |
| `owner_name` | `gh api user --jq .name` | the detected name |
| `owner_short_name` | first word of `owner_name` | that word |
| `project_repos_root` | parent folder of `brain_root` | for example `C:\dev` |
| `timezone` | Windows: `tzutil /g` (map the Windows zone to IANA); macOS and Linux: `readlink /etc/localtime` | IANA zone with its offset, for example `Australia/Brisbane (+10:00)` |

Rows are alphabetical by field.

> **Ask:** Here is your profile as I detected it. Is it right?
> 1. Yes, write it (recommended)
> 2. Change a line (tell me which)
>
> **Suggested reply:** `1`

Then one optional question about owner-layer rules (`/memory/RULES.md`):

> **Ask:** Do you want any standing preferences of your own now? You can add them any time.
> 1. None yet (recommended – add them as they come up; each is a proposal you accept)
> 2. Typography: en dash, never the em dash, in everything the agents write
> 3. Something else you describe
>
> **Suggested reply:** `1`

A preference becomes a proposal under `/memory/governance/proposals/` and is applied only after
the owner accepts it (CONTRACT §13.2).

### B6. Proposed field: `active_skills`

This guide proposes one additional `OWNER.md` front matter field. It lists the **optional**
shared skills the owner has chosen to use, alphabetically; skills that the rules themselves
require are always active and are not listed. Per-machine readiness stays in the `## Setup`
table.

```yaml
active_skills:
  - ai-session-log
  - manage-credentials
  - xero-access
```

Adding the field to the skeleton's `OWNER.md` template is a change to a governance template
(CONTRACT §13.2) and needs the owner's acceptance of a proposal; until then the agent writes it
into the person's own `OWNER.md` only.

## 5. Step C – Choose your skills

**Done when:** `active_skills` in `/memory/OWNER.md` holds the person's choice (an empty list is
a valid choice).

**Agent does:** reads `/shared/skills/README.md` to confirm the list is still current, then
shows the menu. Always-on skills are listed for information; the person chooses from the
others. Numbers run through both groups so a reply stays short.

**Always on** (governed by rules; nothing to set up). Alphabetical.

| Skill | What it does |
|---|---|
| delegate-work | Hands independent pieces of work to parallel worker agents and collects their results (`RULE-2026-0037`) |
| learning-maintenance | Captures and reviews what the brain learns from use (`RULE-2026-0043`) |
| problem-recovery | Searches the brain's own knowledge before re-investigating a failure |
| product-development | Evidence-and-decision process for software work (`RULE-2026-0028`) |
| raw-file-ingestion | Keeps every uploaded file unchanged under `/memory/raw/` with a readable Markdown copy |
| repository-preflight | Validates both repositories before every commit |
| ui-implementation | Rules a live screen must keep while data changes underneath it |
| ui-mockup | Builds a preview of a screen for you to refine before anything is built |

**Choose from these.** Alphabetical; `Needs` says what the person must provide.

| # | Skill | What it does | Needs |
|---|---|---|---|
| 1 | abr-access | Looks up Australian Business Numbers and company names on the Australian Business Register | Free ABR web-services GUID (emailed after registration); the vault |
| 2 | ai-session-log | Keeps a local, temporary log of every AI call and a viewer at `127.0.0.1:8768` | Nothing external |
| 3 | gohighlevel-access | Reads and, with your confirmation, writes HighLevel CRM data across sub-accounts | A HighLevel **agency** account; a Marketplace app you register; the vault |
| 4 | google-drive-access | Legacy Drive access through a host's own connector | A host Google connector – **not recommended**; use 5 |
| 5 | google-workspace-access | Gmail (draft-first), Calendar, Tasks, Drive and Contacts for one or more Google accounts | A Google account; a Google Cloud project and OAuth client you register; the vault; a Personal CRM node (the agent creates it) |
| 6 | manage-credentials | The encrypted vault every credentialed skill uses | A passphrase you choose; chosen automatically with 1, 3, 5, 8 or 9 |
| 7 | owner-board | One permanent page showing every request you have made and what needs you | Nothing external – **see the note below** |
| 8 | railway-access | Reads Railway projects, deployments and logs | A Railway account token you create; the vault |
| 9 | xero-access | Reads Xero accounting data and, with your approval, creates planned accounts or draft invoices | A Xero organisation; a Xero developer app you register; the vault |

> **Ask:** Which of 1 to 9 do you want? You can add more later by asking me to resume setup.
> 1. `2` only – start local, add accounts later (recommended for a first session)
> 2. A list you give, for example `2, 5, 9`
> 3. None for now
>
> **Suggested reply:** `2`

Owner-board note: its scripts (`cards.py`, `build-status.py`, `reconcile.py` and the directory
builders) are not yet shipped in the mechanics repository. If chosen, record it in
`active_skills`, mark its `## Setup` row `blocked` with that reason, and move on.

Record the choice in `active_skills` (alphabetical; add `manage-credentials` whenever a
credentialed skill is chosen), add one `## Setup` row per chosen skill, and continue to D.

## 6. Step D – Set up each chosen skill

Order: the vault first, because every credentialed skill depends on it; then the chosen skills
alphabetically. Each skill ends with its own verification command; a skill is `done` only when
that command succeeds.

Every command below runs from the brain root. Commands that read the vault need the **Vault
Agent unlocked** (tray icon red, or `vaultctl.py status` reports unlocked).

### D.0 Credential management node (agent only)

When any credentialed skill is chosen, the agent creates `/memory/projects/credential-management/`
(the vault scripts look there by default): the five core files from
`/shared/templates/node-*.template.md`, an empty `data/` folder, and a non-secret registry at
`data/credential-registry.json` naming each vault entry and its fields. The registry is for
people and agents; no script reads it. Proposed shape (fictional values):

```json
{
  "entries": [
    {
      "entry": "xero-oauth",
      "fields": ["client_id", "client_secret", "oauth_token_json"],
      "skill": "/shared/skills/xero-access",
      "system": "Xero",
      "status": "planned"
    }
  ]
}
```

Update `/memory/projects/README.md` to list the new folder (CONTRACT §4).

### D.1 manage-credentials – the vault

**Agent does:**

```powershell
cd C:\dev\brain
python -m pip install -r shared/skills/manage-credentials/requirements.txt
```

Then, after a yes (it creates a Windows scheduled task that starts the tray at every sign-in):

```powershell
cd C:\dev\brain
powershell -NoProfile -File shared/skills/manage-credentials/scripts/install_vault_agent_login.ps1
```

**You do:**

1. Choose a passphrase of **at least 20 characters** that you use nowhere else. Store it in your
   password manager or on paper kept away from the computer. **There is no reset: a lost
   passphrase is a lost vault.** Never type it into the chat.
2. Open your own terminal (not the agent's) and create the vault; it asks for the passphrase
   twice through a hidden prompt:

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py init
   ```

3. Start the tray and unlock it from its menu (**Unlock…**); the icon turns from grey to red:

   ```powershell
   cd C:\dev\brain
   pythonw shared\skills\manage-credentials\scripts\vault_tray.py
   ```

**Agent verifies:**

```powershell
cd C:\dev\brain
python shared/skills/manage-credentials/scripts/vaultctl.py status
```

`done` when it reports an unlocked agent. Never ask for the passphrase to "help"; if the check
fails, follow the skill's "Access from a sandboxed Python process" section.

macOS and Linux: the tray uses `pystray`, which is untested there (`verify`). The console
alternative is `python shared/skills/manage-credentials/scripts/vault_agent.py serve` in a
terminal the person keeps open, then `vaultctl.py unlock` in another; the broker uses a socket
under `$XDG_RUNTIME_DIR` or `~/.cache`. The Windows logon task has no equivalent yet.

**Storing a secret**, used by every skill below. **You do**, in your own terminal:

```powershell
cd C:\dev\brain
python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
  --entry <entry> --secret <field> [--secret <field> ...] [--empty-json oauth_token_json]
```

Each `--secret` opens a hidden prompt; paste that value there and nowhere else. The agent gives
the exact command with the entry and fields filled in.

### D.2 abr-access

**You do:**

1. Open https://abr.business.gov.au/Tools/WebServices and follow the web-services
   registration link. Accept the web services agreement and give your contact details.
2. ABR emails you an authentication GUID. Store it:

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
     --entry abr-webservices-guid --secret authentication_guid
   ```

If `google-workspace-access` is already `done` and the GUID sits in an old email, the agent can
import it instead with `abr_import_guid_from_gmail.py` (see the skill); it shows only the last
four characters.

**Agent does:** adds the entry to the credential registry.

**Agent verifies** (a read-only lookup of a public entity):

```powershell
cd C:\dev\brain
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry abr-webservices-guid --map ABR_AUTHENTICATION_GUID=authentication_guid `
  -- python shared/skills/abr-access/scripts/abr_search_name.py --name "Australian Taxation Office" --max-results 1
```

### D.3 ai-session-log

**Agent does** (no credentials, no external account):

```powershell
cd C:\dev\brain
python shared/skills/ai-session-log/scripts/session_log.py self-test
python shared/skills/ai-session-log/scripts/session_log.py listen --once
```

**Agent verifies:** `self-test` passes and `session_log.py path` prints a file under
`/temp/ai-session/`. Keeping the listener running and the viewer are in step G.

### D.4 gohighlevel-access

Needs a HighLevel **agency** login with admin rights.

**You do** (Marketplace labels change between releases – `verify against current host docs`):

1. Sign in at https://marketplace.gohighlevel.com with your agency login and open **My Apps →
   Create App**.
2. Name it (suggested: `brain-local`), type **Private**, target user **Agency**.
3. Under **Auth**: add the redirect URL exactly `http://localhost:8766/oauth/callback`; add the
   scopes `companies.readonly` and `locations.readonly`, plus the resource scopes you intend to
   use (for example `contacts.readonly`, `opportunities.readonly`); add `oauth.readonly` and
   `oauth.write` only if they are offered.
4. Under **Client Keys**, add a key and store the client ID and secret straight into the vault:

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
     --entry ghl-agency-oauth --secret client_id --secret client_secret --empty-json oauth_token_json
   ```

5. Copy the app's generated **Installation URL**; you will paste it into the local manager page,
   not into chat.

**Agent does:** adds the registry entry, then starts the manager:

```powershell
cd C:\dev\brain
python shared/skills/gohighlevel-access/scripts/ghl_connect.py
```

**You do:** open `http://localhost:8766/`, paste the Installation URL, sign in as agency admin
and approve the sub-accounts the brain may reach.

**Agent verifies:**

```powershell
cd C:\dev\brain
python shared/skills/gohighlevel-access/scripts/ghl_subaccounts.py
```

`done` when it prints the agency name and the approved sub-accounts. Every later write still
needs the target sub-account confirmed for that operation (CONTRACT §10.5).

### D.5 google-workspace-access

**Agent does first:**

1. Installs the dependencies:
   `python -m pip install -r shared/skills/google-workspace-access/requirements.txt`.
2. Creates a Personal CRM node at `/memory/projects/contacts/` (five core files, and
   `data/`, `personas/`, `contacts/`), and `/memory/skills/google-workspace-access/config/crm.json`:

   ```json
   { "crm_root": "/memory/projects/contacts" }
   ```

3. Asks for an alias per Google login and writes `data/google-accounts.json`:

   > **Ask:** Which Google logins should the brain use, and what short alias for each?
   > 1. One login, alias `personal` (recommended to start)
   > 2. Several – give me each login and alias
   >
   > **Suggested reply:** `1`

   ```json
   {
     "accounts": [
       {
         "alias": "personal",
         "email": "owner@example.com",
         "vault_entry": "google-workspace-oauth-personal",
         "used_by_personas": ["personal"],
         "status": "planned"
       }
     ]
   }
   ```

**You do**, in Google Cloud Console signed in with the Google login that will own the app
(console labels move – `verify against current host docs`):

1. **Create a project:** https://console.cloud.google.com/projectcreate – name suggested
   `brain-workspace`.
2. **Enable APIs:** https://console.cloud.google.com/apis/library – enable Gmail API, Google
   Calendar API, Google Tasks API, Google Drive API and People API.
3. **Branding:** https://console.cloud.google.com/auth/branding – app name (suggested
   `Brain local`), your support email, your developer contact email.
4. **Audience:** https://console.cloud.google.com/auth/audience
   - A Google Workspace organisation where every login you will connect belongs to it: choose
     **Internal**.
   - Otherwise (for example a personal Gmail login): choose **External** and add each login as
     a **Test user**. While the app is in **Testing**, Google expires its refresh tokens after
     seven days, so you would reconnect weekly. To avoid that, press **Publish app**; the
     consent screen then warns that the app is unverified, which is expected for an app only
     you use.
5. **Create the OAuth client:** https://console.cloud.google.com/auth/clients → **Create
   client** → type **Web application** → name `brain-local` → **Authorised redirect URIs**:
   exactly `http://localhost:8767/oauth/callback` → **Create**. Keep the dialog open.
6. Store the client ID and secret straight from that dialog (one entry per alias; the same
   client may serve several aliases):

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
     --entry google-workspace-oauth-personal --secret client_id --secret client_secret --empty-json oauth_token_json
   ```

**Agent does:** starts the connection manager:

```powershell
cd C:\dev\brain
$env:GOOGLE_TOKEN_STORE = "vault"; $env:GOOGLE_REDIRECT_URI = "http://localhost:8767/oauth/callback"
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-personal `
  --map GOOGLE_CLIENT_ID=client_id --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_connect.py --account personal
```

**You do:** open `http://localhost:8767/`, connect, sign in with **the login recorded for that
alias**, and approve the scopes (for an unverified External app: **Advanced → Go to … (unsafe)**
is expected).

**Agent verifies:**

```powershell
cd C:\dev\brain
$env:GOOGLE_TOKEN_STORE = "vault"
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry google-workspace-oauth-personal `
  --map GOOGLE_CLIENT_ID=client_id --map GOOGLE_CLIENT_SECRET=client_secret `
  -- python shared/skills/google-workspace-access/scripts/google_status.py --account personal
```

`done` when the status succeeds; then set the account's `status` to `connected` in
`google-accounts.json`. Email stays draft-first: nothing is sent without the owner approving a
specific draft.

### D.6 railway-access

**You do:**

1. Open https://railway.com/account/tokens → create a token named `brain-local`. For all
   projects, leave the workspace as **No workspace** (an account token); for one team only,
   choose that workspace.
2. Store it before closing the page (it is shown once):

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
     --entry railway-api --secret api_token
   ```

**Agent does:** `python -m pip install -r shared/skills/railway-access/requirements.txt`, and the
registry entry.

**Agent verifies:**

```powershell
cd C:\dev\brain
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry railway-api --map RAILWAY_API_TOKEN=api_token `
  -- python shared/skills/railway-access/scripts/railway_projects.py --list-workspaces
```

### D.7 xero-access

**You do** (portal labels move – `verify against current host docs`):

1. Open https://developer.xero.com/app/manage and sign in with your Xero login → **New app**.
2. App name (suggested `brain-local-<short name>`; Xero rejects names containing "Xero"),
   integration type **Web app**, company or application URL (your website or your GitHub
   profile URL), redirect URI exactly `http://localhost:8765/oauth/callback`. Accept the
   developer terms and create the app.
3. On the app's **Configuration** page, copy the client ID, press **Generate a secret**, and
   store both at once:

   ```powershell
   cd C:\dev\brain
   python shared/skills/manage-credentials/scripts/vault_credentials.py put-entry `
     --entry xero-oauth --secret client_id --secret client_secret --empty-json oauth_token_json
   ```

**Agent does:** adds the registry entry, then starts the manager:

```powershell
cd C:\dev\brain
$env:XERO_TOKEN_STORE = "vault"; $env:XERO_VAULT_ENTRY = "xero-oauth"; $env:XERO_VAULT_FIELD = "oauth_token_json"; $env:XERO_REDIRECT_URI = "http://localhost:8765/oauth/callback"
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry xero-oauth --map XERO_CLIENT_ID=client_id --map XERO_CLIENT_SECRET=client_secret `
  -- python shared/skills/xero-access/scripts/xero_connect.py
```

**You do:** open `http://localhost:8765/`, choose **Add Organisation…**, sign in to Xero, tick
the organisations the brain may read, and allow access. Then pick the default organisation and
**Save selection**.

**Agent verifies** (read-only; output stays in the ignored `temp/` folder):

```powershell
cd C:\dev\brain
$env:XERO_TOKEN_STORE = "vault"; $env:XERO_VAULT_ENTRY = "xero-oauth"; $env:XERO_VAULT_FIELD = "oauth_token_json"
python shared/skills/manage-credentials/scripts/vault_credentials.py run `
  --entry xero-oauth --map XERO_CLIENT_ID=client_id --map XERO_CLIENT_SECRET=client_secret `
  -- python shared/skills/xero-access/scripts/xero_download.py --resource Organisation `
     --output temp/xero-access/organisation.json --requesting-node /memory/projects/credential-management
```

Record the organisation names and tenant IDs in `/memory/skills/xero-access/NOTES.md`, never in
the mechanics. Every write still needs the organisation confirmed for that operation.

## 7. Step E – Make every session start from the contract

**Done when:** each file below exists on this machine for each host the person uses.

`RULE-2026-0015` allows host entry files to **point** at the portable bootstrap and nothing
more: no behavioural rule may live in them. Every template in `/shared/templates/host-pointers/`
is such a pointer. Copy the body, fill `<BRAIN_ROOT>`, and change nothing else.

Rows are grouped by host, then in the order a session looks for them.

| Host | File | Template | Why |
|---|---|---|---|
| Claude Code | `<brain_root>/CLAUDE.md` | already in the smarts | Sessions in the brain or in `memory/` (Claude Code also reads parent folders) |
| Claude Code | `~/.claude/CLAUDE.md` | `claude-code-user.CLAUDE.template.md` | Sessions opened in a sibling project repository or elsewhere |
| Claude Code | `<project repo>/CLAUDE.md` | `project-repo.CLAUDE.template.md` | A project repository's own pointer, useful to collaborators too |
| Codex | `<brain_root>/AGENTS.md` | already in the smarts | Sessions in the brain root |
| Codex | `<brain_root>/memory/AGENTS.md` | `memory-root.AGENTS.template.md` | Codex stops at the Git root, and `memory/` is its own repository (installed in B4) |
| Codex | `~/.codex/AGENTS.md` | `codex-user.AGENTS.template.md` | Every Codex session, any folder |
| Codex, Cursor and others | `<project repo>/AGENTS.md` | `project-repo.AGENTS.template.md` | A project repository's own pointer |
| Cursor | `<brain_root>/AGENTS.md` and `.cursor/hooks.json` | already in the smarts | Cursor reads `AGENTS.md`; the hooks feed the session log |
| Cursor | `<project repo>/.cursor/rules/brain-contract.mdc` | `cursor-project-repo.brain-contract.mdc.template` | Only when the project's Cursor does not pick up `AGENTS.md` (`verify`) |

**Agent does:** for a user-level file that already exists, show the person the current content
and offer:

> **Ask:** `~/.codex/AGENTS.md` already has content. What should I do?
> 1. Keep it and add the pointer at the top (recommended)
> 2. Replace it with the pointer (the old file is saved beside it as `.bak`)
> 3. Leave it alone
>
> **Suggested reply:** `1`

If the existing content carries behavioural rules, point out that `RULE-2026-0015` wants them in
`/memory/RULES.md` instead, and offer to draft that proposal.

Project repository pointers name the brain by its usual sibling location and never name a
`/memory/` path, because a collaborator cannot resolve it (CONTRACT §16.2).

## 8. Step F – Uninterrupted work settings

**Done when:** the person has chosen a level and the chosen files are in place, or chose to keep
the host defaults.

### F.1 The trade-off

Hosts ask before commands and edits by default. That is safe and slow: the brain's own rules
already require a commit at every checkpoint (`RULE-2026-0017`), so a person who approves each
`git add` and `git commit` spends the session clicking. Allowing routine commands removes the
clicks. The cost is that a mistaken command runs without a human looking at it first.

What stays whatever the setting:

1. **No secrets.** Vault files, `.env` files and the vault agent's runtime folder are denied to
   the agent's reading tools. A deny rule on a reading tool does not stop a shell command from
   reading the same file, so the contract's credential rules (CONTRACT §10.3) still apply as
   instructions, not only as settings.
2. **No destructive Git.** Force push, hard reset, `git clean`, amending and `--no-verify` are
   denied (`RULE-2026-0017`).
3. **Recursive deletes ask.** `rm -rf` and `Remove-Item -Recurse` always ask.
4. **External side effects are still confirmed** with the owner for each operation (CONTRACT
   §10.5). No setting replaces that conversation; the skills also refuse writes without their
   confirmation flags.

Pattern rules match command prefixes. A determined or confused agent can reach the same effect
another way (a script, a different shell), so treat the lists as guard rails, not a sandbox.

> **Ask:** How much should the agent do without asking?
> 1. Routine work runs: reads, edits inside the brain and project repositories, tests,
>    preflight, `git add`, `git commit`, plain `git push`; everything in the deny and ask lists
>    still stops (recommended)
> 2. Edits run, every command asks (the host's "accept edits" level)
> 3. Keep the host defaults
>
> **Suggested reply:** `1`

### F.2 Claude Code

The smarts' `.gitignore` ignores `.claude/`, so a committed project `settings.json` is not
possible without changing that; this guide recommends local files instead, which suit
per-machine choices anyway.

| File | Template | Holds |
|---|---|---|
| `~/.claude/settings.json` (merge) | `claude-code.user-settings.template.json` | The deny and ask lists and the default mode – they then apply in every folder, including project repositories |
| `<brain_root>/.claude/settings.local.json` | `claude-code.settings.local.template.json` | The allow list for routine work in the brain |
| `<project repo>/.claude/settings.local.json` | the same template | The allow list in each project repository |

Rows are in the order Claude Code applies them, broadest first.

Confirmed from working settings files: the `permissions` object with `allow` and `deny` lists,
rule forms `Bash(git add *)`, `PowerShell(...)`, `Read(//c/abs/path/**)` and
`WebFetch(domain:...)`. From the host's documentation, not re-checked offline (`verify
against current host docs`): the `ask` list, `defaultMode` values (`default`, `acceptEdits`,
`plan`, `bypassPermissions`, and in recent versions an automatic mode), `~` in path rules, and
precedence deny > ask > allow.

Modes: **accept edits** (`defaultMode: "acceptEdits"`, or Shift+Tab in a session) lets edits run
and asks for commands not on the allow list. It is the recommended default. **Bypass
permissions** skips every prompt, including the ask list, and is not recommended for a brain
that holds credentials. An automatic mode, where offered, lets the host decide per action; if
the person uses it, the deny list still applies (`verify`).

### F.3 Codex

Merge `codex.config.template.toml` into `~/.codex/config.toml`. Confirmed from a working file:
`[projects.'<path>'] trust_level = "trusted"` and `[windows] sandbox = "unelevated"`. From the
host's documentation, not re-checked offline (`verify against current host docs`):
`approval_policy` (`untrusted`, `on-failure`, `on-request`, `never`), `sandbox_mode`
(`read-only`, `workspace-write`, `danger-full-access`) and the `[sandbox_workspace_write]`
table (`writable_roots`, `network_access`).

Recommended: `approval_policy = "on-request"` with `sandbox_mode = "workspace-write"`: the agent
works inside the brain and project repositories without asking, and asks to leave the sandbox.
Codex has no per-command deny list in this file; the safety floor there is the sandbox plus the
contract's instructions.

The Vault Agent broker may be unreadable from inside the sandbox; the vault skill documents the
recovery (run the consumer outside the sandbox after approval). Expect one approval per
credentialed command.

### F.4 Cursor

- **Editor:** Cursor Settings → Agents → Auto-run: choose **Use allowlist** and add the commands
  from `claude-code.settings.local.template.json`'s `allow` list written as plain command
  prefixes (`git status`, `git add`, `git commit`, `python shared/skills/repository-preflight/scripts/preflight.py`).
  Keep file-deletion, dotfile and external-file protection on. Setting names move between
  releases (`verify against current host docs`).
- **Cursor CLI:** merge `cursor-cli.cli-config.template.json` into `~/.cursor/cli-config.json`.
  Confirmed from a working file: `permissions.allow` and `permissions.deny` lists with
  `Shell(<command>)` entries, and `approvalMode: "allowlist"`. `Read(...)` and `Write(...)`
  entries are from the host's documentation (`verify`).

## 9. Step G – Optional extras

Offer each; each is `skipped` unless the person says yes.

> **Ask:** Which extras do you want?
> 1. Session-log listener at sign-in, and the viewer (recommended if `ai-session-log` was chosen)
> 2. Owner board (blocked until its scripts ship – see step C)
> 3. A scheduled task (see G.3)
> 4. None now
>
> **Suggested reply:** `1`

### G.1 Session-log listener and viewer

Run while working:

```powershell
cd C:\dev\brain
python shared/skills/ai-session-log/scripts/session_log.py listen --model "<host> <model>"
python shared/skills/ai-session-log/scripts/session_log.py view --open
```

The viewer is at `http://127.0.0.1:8768/`. Use the model name the host shows; never invent one.

To start the listener at every Windows sign-in (after a yes; it creates a scheduled task):

```powershell
cd C:\dev\brain
schtasks /Create /TN "Brain\SessionLogListener" /SC ONLOGON /RL LIMITED `
  /TR "pythonw C:\dev\brain\shared\skills\ai-session-log\scripts\session_log.py listen --root C:\dev\brain"
```

`pythonw` must be on `PATH` for the task, or give its full path (`where.exe pythonw`). macOS
(`launchd`) and Linux (`systemd --user`) equivalents are not written yet (`verify`).

### G.2 Owner board

Blocked until the board scripts ship in the mechanics repository (see step C). When they do: a
board per project node at `/memory/projects/<node>/status/status.html` and the directory at
`/memory/boards/index.html`, which the owner bookmarks once (`/shared/skills/owner-board/`).

### G.3 Scheduled tasks

The contract forbids claiming future follow-up unless a scheduler is actually configured
(CONTRACT §14). Candidates, alphabetical:

- **Google local sync worker** (`google_sync_ctl.py worker`), when `google-workspace-access`
  local sync is wanted – runs under `vault_credentials.py run`, so the Vault Agent must be
  unlocked.
- **Task review**, surfacing waiting tasks at `next_review` (CONTRACT §9.1) – through the host's
  own scheduler (for example Claude Code scheduled tasks or routines), started from the brain
  root.
- **Vault Agent tray at sign-in** – already created in D.1.

Record each configured schedule in `/memory/STATE.md` so the next session knows it exists.

## 10. Step H – Final validation and tour

**Done when:** preflight passes on both repositories, both have a pushed commit, and the tour is
given.

**Agent does:**

1. Validate both repositories in one pass and write the manifests:

   ```powershell
   cd C:\dev\brain
   python shared/skills/repository-preflight/scripts/preflight.py --root .
   python shared/skills/repository-preflight/scripts/preflight.py --root . --write-manifest
   ```

2. Commit each repository separately, staging named paths only, with the host and model in the
   message (`RULE-2026-0017`):

   List what setup changed with `git status --short`, check that no secret or vault file is
   among it, and stage those paths by name (example below):

   ```powershell
   cd C:\dev\brain\memory
   git status --short
   git add -- OWNER.md STATE.md LOG.md repository-manifest.json projects/README.md projects/credential-management skills
   git commit -m "<host> <model>: setup complete"
   git push
   cd C:\dev\brain
   git commit -m "<host> <model>: manifest after setup" -- repository-manifest.json
   git push
   ```

   The smarts commit exists only if the manifest changed; nothing about the person goes there.
3. Set every `## Setup` row to its final status and append one `LOG.md` entry naming the
   chosen skills, the host wiring and the settings level.
4. Report the commit hash and push status for each repository (`RULE-2026-0023`).

**Tour** – five minutes, in this order (the order the owner will meet them):

1. `/memory/OWNER.md` – who the brain works for; change it any time.
2. Say a task out loud ("remind me to renew the domain by Friday") – watch it land in
   `/memory/tasks/open/`.
3. Drop a file in the chat – it is kept unchanged under `/memory/raw/` with a readable copy in
   `/memory/sources/`.
4. "From now on…" – a standing preference becomes a proposal you accept before it applies.
5. Getting improvements: `cd <brain_root>; git fetch upstream; git merge upstream/main`, then
   preflight. Improvements you make to the mechanics can be offered back to the original as a
   pull request, provided they carry no personal data.
6. Adding a skill later: "resume setup" – the agent reads this guide and your `## Setup` table.

## 11. Items to verify against current host and provider documentation

Collected from the steps above so they can be checked in one pass. Alphabetical.

- Claude Code: `ask` list, `defaultMode` values, `~` in path rules, rule precedence, the
  automatic mode, and the native installer command.
- Codex: `approval_policy`, `sandbox_mode`, `[sandbox_workspace_write]`, and the install command.
- Cursor: Auto-run allowlist setting names, whether `AGENTS.md` is read in every project, the
  `.cursor/rules/*.mdc` front matter (`alwaysApply`), and CLI `Read(...)`/`Write(...)` entries.
- Google Cloud Console page paths (Google Auth Platform) and the seven-day refresh-token limit in
  Testing.
- HighLevel Marketplace labels (Private app, Client Keys, Installation URL).
- Vault Agent on macOS and Linux (tray and console agent), and non-Windows logon start-up.
- Xero developer portal labels and app-name restrictions.
