---
id: skill-learning-maintenance
title: Learning Maintenance
type: skill
schema_version: 0.2
contract: /CONTRACT.md
created: 2026-09-17T17:14:19+10:00
updated: 2026-09-23T12:00:00+10:00
status: active
owner: brain-owner
scope: shared
---

# Learning Maintenance

Portable procedure for RULE-2026-0043 and RULE-2026-0032 amendment A3. The rules define authority. Prototype code and the RULE-2026-0044 restructure are not active dependencies.

## Purpose

Capture, investigate, review and retire useful learning without reminders, with a weekly owner review. Any session may integrate; while it writes it is the only writer.

## Invocation and required inputs

At task entry read only `/memory/projects/brain-development/data/learning/index.md`. It supplies pending-work pointers and digest due state. Then continue the owner's task. Read the remaining procedure only for capture, eligible background work, recovery or integration. Inputs: relevant subject, evidence or candidate record, session identity, and actual model (unknown if unavailable). No designation to look up: any session may integrate.

## Data sources

Subject knowledge stores, API knowledge conventions, project state and relevant evidence; `/memory/projects/brain-development/data/learning/`; `/memory/tasks/`; existing delegated-work results. Read targeted records, not the whole corpus. External research uses public authoritative sources and records URL, retrieval time, claim supported, applicability and limitations; keep recommendation distinct from local verification. Never send private brain content to search engines.

## Allowed operations and permissions

Capture learning, perform credential-free read-only review or public research, and return findings. Any session may update canonical learning, the shared index and board, and learning state, holding exclusion for the duration of each write. Existing owner decisions, protected governance and raw evidence cannot be changed by maintenance. A normal thread may capture its own unique pending artifact; a background worker writes only inside its assigned result directory. Use the existing delegate-work protocol when the host supports workers. No vendor-specific skill or dispatcher is required.

## Capture and pending-work routing

Search the relevant canonical home for duplicates at a natural checkpoint. Capture observation, evidence, expected/actual result, scope, assumptions, proposed response and questions. Record owner feedback verbatim when safe to retain, classifying preference, decision, usefulness assessment or factual observation. Never copy secrets into learning.

Write the record to its canonical home and integrate it. The inbox at `/memory/projects/brain-development/data/learning/inbox/` is **optional** and exists for two cases: a worker returning findings it may not write itself, and a session that has something worth keeping but does not want to decide its canonical home. An inbox artifact is a UUID-named Markdown file with required front matter, canonical target or subject, origin session and model, and evidence pointers. Do not edit another session's artifact. Workers return their own artifacts; the launching thread preserves substantive evidence outside temporary run folders before they disappear. Outstanding integration is covered by one standing integration task, named in the learning index; link an artifact to that task, or create a separate canonical task for independently actionable work. Any session may drain the inbox at an integration checkpoint; it is not a foreground corpus scan. The startup index is a compact hint and may lag new records. Never treat absence from it as proof no learning exists.

## Integration

**Exclusion belongs to the write, not to a session.** While a session writes canonical learning, the
shared index or the board, it must be the only writer; when the write is done the exclusion is gone.
Nothing about it outlives the process that took it, so no designation can go stale and no work waits
on a session that has ended.

Take an exclusive OS lock for the duration of the write: `msvcrt.locking` on Windows,
`fcntl.flock` on POSIX, on a lock file beside the records. The kernel releases it if the holder dies,
which is the property that matters and the reason no lease, expiry, heartbeat or fencing token is
needed. Measured on the owner's host and recorded in
`/memory/projects/brain-development/data/learnings/filesystem-primitives-on-this-host.md`, which also states
where it does not hold.

**It does not hold across separate synced checkouts.** Two clones joined by OneDrive, Dropbox, SMB or
Git share no kernel, so no lock serialises them. There Git is the backstop: a concurrent write is a
merge conflict, which is visible and recoverable. That is the weaker guarantee and the honest one.

Each integration batch, inside that window:

1. Re-read the target's current content. A result computed against an older revision is rechecked,
   not applied blindly.
2. Merge one record at a time, preserving prior evidence and history, recording application once by
   artifact id.
3. Update task disposition, regenerate the derived views, validate and commit.

Stage only your own paths. `RULE-2026-0017` requires it and the pre-commit hook enforces it; it is
what actually stops one session disturbing another, and it matters more here than any lock. Treat a
Git conflict as the signal to reconcile, never to overwrite. If interrupted, inspect the actual Git
diff and artifact ids before continuing; never infer success from a status label. Retain pending
evidence until integration is verified.

## Canonical record and review

Keep the record with its subject: API entries retain RULE-2026-0022 conventions; other provisional learning lives in that node's `data/learnings/`. Established KNOWLEDGE may link to it rather than duplicate it. Existing unstructured lessons can be indexed by heading without mass migration. New standalone records carry a stable ID, category, subject scope, evidence status, review status, origin session/model and evidence links. Categories: decisions/constraints; goals/preferences; observed behaviour; recovery methods; working methods. Body contains the capture fields, next action, feedback, usage and dated changes. Preserve one canonical identity when status changes.

Review pending records in a later session. Record exact reviewed revision, reviewer session/model, evidence, counterexamples, changed assumptions and disposition. Independence is `independent` only when both underlying models are known and different, otherwise `same_model` or `unknown`. Useful reviews need not be independent. Empirical confirmation requires evidence such as a live probe or observed subsequent use; model agreement alone is insufficient and independent review is not a prerequisite to recording an observed fact. Unknown models do not strand records. Investigate disagreement; escalate only under the rule's four conditions.

Run at most one background worker per thread, at most three records per run, depth one within RULE-2026-0037. Name a concrete effort/time limit in its packet and stop when it is reached, returning partial findings and remaining work. Log observed cost/time when available and unknown otherwise. Optional Six Hats can examine facts, feelings, benefits, risks, alternatives and next actions for an important or disputed question; do not represent these lenses as different models.

## Maintenance, feedback and forgetting

Keep evidence status separate from review status and usefulness. Retain old advice as refuted/superseded/withdrawn with reason and replacement/exception links; exclude it from current recommendations, but let targeted searches find its warning. Never retire solely because old or rarely used. Before relying on significant retirement, test an obsolete-advice scenario and a valid rare exception with a fresh agent when available. If that validation is unavailable, leave the significant retirement pending. Script checks and agent trials are reported separately.

Owner preferences govern usefulness within their scope; decisions remain protected from automatic retirement. A usefulness judgement does not change factual truth. Preserve conflicting factual observations and investigate; record a directly contradicted claim as disputed/pending with the specific evidence, retaining the prior status history. For each retrieval/application record date, session, outcome helpful/ineffective/harmful/unknown and basis self_report/observed/independent where supported. Count retrieval and application separately; do not infer historical use. Accumulate per-session notes and fold them in at a natural checkpoint rather than writing on every lookup.

## Index, board and weekly delivery

Whichever session integrates regenerates index.md and board.md from canonical record pointers and task state; they are derived, not a second knowledge store. Include stable IDs, canonical links, category, current status and next action, ordered by category then latest substantive change. Preserve withdrawn entries in the changed-since-last-delivery digest even when excluded from routine retrieval. Missing or stale views are repaired in background by whichever session notices; foreground work continues with targeted subject search.

The first digest is due seven days after activation. **Any session may prepare and present it.** Presenting is a read of canonical records plus a message to the owner; it writes no learning. An earlier version of this skill restricted it to a designated writer, which made `RULE-2026-0043`'s weekly review unreachable: the designated session would usually not be the one active when the digest fell due. The designation is gone, and the general lesson is kept: a skill may implement the rule's duties and must not narrow one into something that cannot happen.

When due in an active session, that session prepares a snapshot of all new learning and substantive changes since the last delivered snapshot, including retirements, uncertainty and owner questions. Record snapshot ID and status prepared, then presenting before showing it, and delivered only after actually displaying it. Record next due seven days after delivery. If delivery is uncertain, retain the snapshot and label the next presentation a possible repeat. Two sessions reaching the due date together are safe: the states are at-least-once by design, and a repeat is labelled rather than hidden. A digest may be offered in the normal response without a separate interruption. No scheduler or real-time guarantee is implied. Presentation never accepts governance.

A weekly review the owner sees twice costs little; one they never see costs the whole mechanism.

## Scripts or commands

None required. This is an agent-executed portable procedure. Use repository preflight for structural validation; keep the isolated concurrency prototype inactive.

## Outputs

Canonical learning or linked evidence, pending tasks/artifacts, review receipts in record history, generated Markdown index/board, weekly digest, and explicit validation limitations.

## Failure behaviour

When workers are unavailable, preserve pending work; when exclusion cannot be taken or the evidence is uncertain, defer integration and retry later. Continue independent foreground work. Investigate failures/disagreement rather than automatically asking the owner. Apply the four escalation conditions in RULE-2026-0043. No silent deletion, invented model identity, assumed delivery or claimed future execution.

## Logging and state, knowledge and task updates

The integrating session records each substantive integration batch in the owning LOG, updates affected task state, and commits under the Git rules. Do not modify shared logs from a worker. The standing integration task named in the learning index tracks operation, integration and initial behavioural evaluation. Keep task status and `/memory/tasks/STATE.md` consistent. Record observed failures as learning and adjust through the same process; operating-rule changes still require acceptance.
