---
id: brain-seed-prompt
title: Seed Prompt for a New Brain
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T13:00:00+10:00
updated: 2026-09-23T15:02:27+10:00
owner: brain-owner
---

# Seed prompt

Read `/CONTRACT.md` first. This is the prompt a new person pastes into their AI host (Claude
Code, Codex or Cursor) to start their own brain. Replace `<SMARTS_REPO_URL>` with the address of
the smarts repository they were given before sharing it. The same prompt resumes an unfinished
setup.

```text
Set up my own portable AI brain, or resume the setup if it is already started.
The mechanics repository is <SMARTS_REPO_URL>. If it is not cloned on this computer yet:
1. Check that git and the GitHub CLI are installed (git --version, gh --version). If either is
   missing, offer the install command (Windows: winget install --id Git.Git -e and
   winget install --id GitHub.cli -e; macOS: brew install git gh; Linux: sudo apt install git,
   and gh from GitHub's own package repository) and run it only after my yes. I may need to
   open a new terminal afterwards.
2. Check gh auth status. If I am not signed in, tell me to run gh auth login in my own
   terminal (GitHub.com, HTTPS, login with a web browser) and wait until I say done.
3. Clone it into C:\dev\brain (Windows) or ~/dev/brain (macOS and Linux), creating the dev
   folder first if it is missing – ask me first if you think another folder is better.
Then read CONTRACT.md and SETUP.md in that folder and follow SETUP.md step by step.
Check what you can yourself; ask me only what you cannot find out, always with a suggested answer.
Never ask me for a passphrase, password, token or client secret in this chat: tell me the
command to run in my own terminal and I will type or paste it into the hidden prompt there.
Confirm with me before installing anything, creating a repository or changing a setting.
Record progress under "## Setup" in memory/STATE.md so we can stop and pick up later.
```
