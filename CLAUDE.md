---
id: claude-entry
title: Claude Code Entry Point
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-12T08:05:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start here

This repository is a contract-governed, file-based "brain", not a conventional codebase. All operating rules, structure, conventions, and commands are defined in [`/CONTRACT.md`](CONTRACT.md) – **read it in full before creating, changing, or deleting anything here.**

This file is intentionally just a pointer, not a summary. Repository behaviour, folder layout, task/knowledge routing, shared skills, and governance rules all live in the contract and the files it directs you to, and evolve there. Do not duplicate that content back into this file – read it fresh each session so it can't go stale.

## Bootstrap

Follow the sequence `/CONTRACT.md` itself defines (Section 1; see also `/BOOTSTRAP.md`):

1. Read `/CONTRACT.md`
2. Read root `/RULES.md`, then `/memory/OWNER.md` and `/memory/RULES.md`, then any inherited `RULES.md` down to the active node
3. Read the active node's `README.md` and `STATE.md`
4. Read `/ONBOARDING_AGENT.md` for the current shared-skill index and operating notes, and `/memory/ONBOARDING_OWNER.md` for the owner's own

If given a nested path, walk upward until `CONTRACT.md` is found. If location hints resolve to different contracts, stop and report the ambiguity rather than guessing.
