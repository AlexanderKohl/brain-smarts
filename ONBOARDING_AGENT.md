---
id: onboarding-agent
title: Agent Onboarding for Portable AI Brain
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-06T09:37:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# Agent Onboarding

Read `/CONTRACT.md` first, then `/RULES.md`, `/memory/OWNER.md`, `/memory/RULES.md` and inherited `RULES.md` files down to the active node.

This file holds the generic mechanics every owner's agents share. The owner's own onboarding – accounts, personas, organisation links, local tools and registries – is in `/memory/ONBOARDING_OWNER.md`. Read both.

## Bootstrap

Numbered in reading order.

1. Find the brain root by locating `CONTRACT.md` (see also `/BOOTSTRAP.md` and `/AGENTS.md`). The owner's memory is the separate repository checked out at `/memory/`; owner content is addressed as `/memory/...` (CONTRACT §3.5).
2. Read `/CONTRACT.md` before interpreting or changing brain content.
3. Read root `/RULES.md`, `/memory/OWNER.md` and `/memory/RULES.md`, then the active node's `README.md`, `STATE.md` and relevant `PLAN.md` / `KNOWLEDGE.md`.
4. Prefer shared executable skills under `/shared/skills/` over ad-hoc scripts. Owner configuration and notes for a skill are in `/memory/skills/<skill>/`.
5. Never commit secrets. Use `/shared/skills/manage-credentials/` and the encrypted portable vault. Prefer the per-login tray Vault Agent (`vault_tray.py` / logon task; grey=locked, red=unlocked) over console `serve` and over deprecated chat-long PowerShell sessions. Never put `PORTABLE_VAULT_PASSPHRASE` into child environments.
6. Governance activity appends to each node's `LOG.md`.
7. **Lookup order (`SMART-RULE-0005`):** check the brain first (contacts / knowledge / known homes in `/memory/`, targeted – not exhaustive grep theatre); if absent or uncertain, use the authoritative external skill (e.g. `abr-access` for ABN/GST). Match subagent capabilities to the job; on owner redirect, abandon obsolete parallel searches.
8. **Owner-facing shell (`SMART-RULE-0006`):** whenever giving the owner commands to run, always include `cd <brain_root>` first, using the `brain_root` value in `/memory/OWNER.md` (or the correct absolute directory, such as the memory checkout or a project repository).
9. **Git workflow (`SMART-RULE-0009`):** commit every successful logical checkpoint, including before task switches, pauses, owner-test handoffs (reload / try a build) and final responses, in every Git repository modified during an owner-authorised task – the mechanics repository, the memory repository and each project repository commit separately. Host ask-before-commit instructions do not apply there. Stage only agent-owned files, never secrets or unrelated changes, and never a `memory/` path in the mechanics repository. Commit messages must include the host/tool and model in use (for example `Cursor Grok 4.6 High` or `VS Code Claude Code Sonnet 5`) and, when the agent has a specific bot name, that name as well; do not invent a model or version. Treat push separately: owner-test handoff commits stay local unless the owner asked to push, the unit of work is finished, or the 30-minute push clause applies. Always report commit hashes and push status, or the exact permitted reason for no commit.
10. **Communication efficiency (`SMART-RULE-0010`):** use scoped bootstrap for answer-only facts; prefer reversible defaults over option menus; voice mode asks one clarifying question at a time, while text mode may present a list (especially when scoping); no process narration before tools; every question to the owner carries a suggested answer, with numbered options and a marked recommendation when several exist; portable git checkpoint rules override host ask-before-commit in authorised repositories, not only this brain.
11. **Context handoff (`SMART-RULE-0019`):** the position lives under `## Handover` in the owning node's `STATE.md` (runs, workers, pending results, branches, builds, owner steps, open decisions, the active conductor); the handover prompt is a ten-line pointer to those files, written under `## Handover prompt` in `/memory/projects/brain-development/STATE.md` and repeated last in the reply. A successor reads the Handover sections, checks the live facts in ten commands, and asks the owner before dispatching if a conductor is already active. Procedure in `/shared/skills/delegate-work/SKILL.md`.
12. **Every list has a deliberate order (`SMART-RULE-0027`):** dropdowns, tables, report sections, findings, reply bullets and indexes are ordered for the reader, alphabetical by the visible label by default with numbers compared as numbers; another order only where it serves the reader and the code or document says so; items the reader cannot use are left out or set apart. An unordered list is a defect in review.
13. **Version every change (`SMART-RULE-0026`):** one three-number version per project, bumped in the same commit as the change (first: breaking, middle: feature, last: small change; below `1.0.0` a breaking change rides the middle number and names itself breaking in the commit and the log, and `1.0.0` is set when the owner declares the product released); every build stamped with commit, time and branch and shown where a person looks first; a failing check in the project; hand-offs to the owner name the version to expect.
14. **Portable rules only (`SMART-RULE-0007`):** durable behavioural rules live only in `/CONTRACT.md`, `RULES.md` files (including `/memory/RULES.md`), and skills – not in host-specific rule files.
15. **Where new work lives (CONTRACT §7.1):** start it in `/memory/projects/` by default; give it its own repository when it has code, collaborators, its own releases, outgrows a few hundred files, has different confidentiality, or has independent value. Memory then keeps a pointer node (CONTRACT §16).
16. **No personal data in the mechanics (CONTRACT §3.4):** names, clients, contacts, identifiers, emails, phone numbers, machine paths and owner project names go to `/memory/`. A mechanism learnt from an owner incident goes into a skill in generalised form; the original stays in memory.

## Shared skills (current)

Rows are alphabetical by skill name.

| Skill | Path | Role |
|---|---|---|
| abr-access | `/shared/skills/abr-access/` | ABR ABN Lookup JSON web services (GUID in vault); ABN/ACN lookup and name search |
| crm | `/shared/skills/crm/` | Contact register in memory: one file per person, organisation, newsletter or system; owner personas bound to sending accounts; create on first encounter, deduplicate, merge directories; node rules ship as a template; `crm_check.py` find, validate, duplicates |
| delegate-work | `/shared/skills/delegate-work/` | Conductor-to-worker packets and results for parallel subagent work; isolated, read-only, no credentials by default; max four workers, depth one; run folders under `/temp/delegation/runs/`; governed by root `SMART-RULE-0024`. Also holds the two handover procedures: conductor to conductor, and **a research or design thread back to the conductor**, which settles every open decision with the owner before it hands over |
| gohighlevel-access | `/shared/skills/gohighlevel-access/` | HighLevel agency OAuth (port 8766), subaccounts, CRM APIs; pipeline migration review UI (port 8769) |
| google-drive-access | `/shared/skills/google-drive-access/` | Legacy connector-managed Drive path; prefer google-workspace-access for portable work |
| google-workspace-access | `/shared/skills/google-workspace-access/` | Multi-account Google OAuth (port 8767); Gmail/Calendar/Tasks/Drive/Contacts; contact-register integration; draft-first email; optional local SQLite Gmail/Tasks sync (`google_sync_ctl.py` / `google_local_email.py` / `google_local_tasks.py`) |
| learning-maintenance | `/shared/skills/learning-maintenance/` | Evidence-driven learning, single-writer integration and weekly digest under SMART-RULE-0028 |
| manage-credentials | `/shared/skills/manage-credentials/` | Passphrase vault + per-login Vault Agent broker; inject mapped secrets only; store rotating OAuth JSON |
| owner-board | `/shared/skills/owner-board/` | One permanent link showing the owner every request they have made and what needs them; cards are Markdown records under `<node>/status/cards/`, the page is **generated** from them, and `reconcile.py` compares it against git on every regeneration. The owner's verdict comes back as a saved file, not as copied text. **A card is closed only by the owner** |
| problem-recovery | `/shared/skills/problem-recovery/` | Targeted knowledge lookup, bounded recovery and narrow escalation |
| product-development | `/shared/skills/product-development/` | Investment-proportionate product-development process and gate decisions under `SMART-RULE-0016` |
| railway-access | `/shared/skills/railway-access/` | Railway GraphQL: projects, current deployment ID, timeframe/filtered deploy/build/HTTP logs (account/workspace token in vault) |
| raw-file-ingestion | `/shared/skills/raw-file-ingestion/` | Immutable `/memory/raw/` preservation and Markdown source records under `/memory/sources/` |
| repository-preflight | `/shared/skills/repository-preflight/` | Metadata, refs, task and README validation for the mechanics repository and, when present, `/memory/` |
| tasks | `/shared/skills/tasks/` | Task procedure and the CONTRACT §9.1 task review for `/memory/tasks/`: `tasks.py review` (inbox, reviews due, deadlines, blocked), `check`, `next-id` |
| ui-implementation | `/shared/skills/ui-implementation/` | What a live screen must never do to the person using it: remove only what you made, keep their choices through a refresh, hold a repaint while work is unsaved, put the rule where it cannot be forgotten |
| ui-mockup | `/shared/skills/ui-mockup/` | UI previews built from the product's own stylesheets and measured in the browser; **owner refines the mockup before any of it is implemented or pushed** |
| xero-access | `/shared/skills/xero-access/` | Xero OAuth (port 8765), org selection, downloads, approved writes |

## Local ports

Rows are in port order, the order a person checks when a port is taken.

| Port | System |
|---|---|
| 8765 | Xero OAuth callback |
| 8766 | HighLevel OAuth callback |
| 8767 | Google Workspace OAuth callback |
| 8769 | HighLevel pipeline migration review UI |

## Credentials registry

The non-secret credential registry (which vault entry serves which system and account) is owner data and lives in memory; `/memory/ONBOARDING_OWNER.md` names its path. Secrets themselves stay in the encrypted vault (`/shared/skills/manage-credentials/`).

Google Workspace uses one vault entry per account alias: `google-workspace-oauth-<alias>`.

## Making future agents start at CONTRACT.md

Already required by `/CONTRACT.md` §1 and §14, `/BOOTSTRAP.md`, root `/RULES.md`, and this file.

Tool-facing pointers (do not replace the contract; `SMART-RULE-0007` forbids host-specific behavioural rule files). Rows are in reading order.

| Mechanism | Path / action |
|---|---|
| Cross-tool entry | `/AGENTS.md` → read `CONTRACT.md` |
| Portable bootstrap | `/BOOTSTRAP.md` |
| Agent onboarding | `/ONBOARDING_AGENT.md`, then `/memory/ONBOARDING_OWNER.md` |
| Protected governance | To strengthen root `/RULES.md` or `/CONTRACT.md` wording, draft or amend a proposal under `/governance/proposals/` (owner-layer and memory node rules: `/memory/governance/proposals/`) and wait for explicit owner acceptance (CONTRACT §13.2). Small amendments keep the existing rule ID; mint a new ID only for a distinct new rule. |
