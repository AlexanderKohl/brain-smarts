---
id: brain-bootstrap
title: Portable AI Brain Bootstrap
type: bootstrap
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T23:16:08+10:00
updated: 2026-09-29T08:00:43+10:00
owner: brain-owner
---

# Portable AI Brain Bootstrap

Use these instructions when an agent or person is given a repository directory, nested node, or file.

1. If given a directory, look for `CONTRACT.md` inside it.
2. If given a nested path, move upward until `CONTRACT.md` is found. A path inside the memory checkout (`/memory/`) or its nodes finds the contract in the brain root one level above it.
3. Choose the bootstrap tier before reading further (`/CONTRACT.md` §1, item 4). Answer-only work reads what the answer needs and nothing else. Any work that will create, change or delete content, take a side effect or meet policy doubt does the full bootstrap first; a turn that began answer-only does it before its first such action.
4. Full bootstrap: read `/CORE.md`, then the owner profile `/memory/OWNER.md` and the owner-layer rules `/memory/RULES.md`, then inherited node `RULES.md` files down to the active node. Read any other contract section or rule in full when its `Applies when` in `/CORE.md` fits the work.
5. Read the active node's `README.md`, `STATE.md` and relevant declared dependencies.
6. Treat machine-specific absolute paths as location hints only. The owner's own local paths are recorded in `/memory/OWNER.md`.
7. If two hints resolve to different contracts, or no contract can be read, stop and report the ambiguity.
8. If `/memory/` is absent, work only on the mechanics and say so. To set up a memory for a new owner, follow `/README.md` § Setting up a memory.
9. Inside an external project repository (`/CONTRACT.md` §16), bootstrap from the brain root, then read the repository's `brain/README.md` and `brain/STATE.md` as the active node.

The repository-root path `/CONTRACT.md` is canonical after discovery. External bootstrap instructions should name the exact contract file when a fixed absolute path is necessary; they should not name a directory and call it a file.
