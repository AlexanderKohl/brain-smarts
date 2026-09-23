---
id: RULE-2026-0043
title: Evidence-driven learning
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: implemented
owner: brain-owner
created: 2026-09-17T14:50:16+10:00
updated: 2026-09-18T00:30:00+10:00
accepted_by: brain-owner
accepted_at: 2026-09-17T17:14:19+10:00
implemented_at: 2026-09-17T17:56:12+10:00
previous_contract_version: 0.9.0
new_contract_version: 0.9.0
target_files:
  - /RULES.md
  - /ONBOARDING_AGENT.md
project_refs:
  - /memory/projects/brain-development
---

# Evidence-driven learning

## Current problem

The brain records what it is told and what it decides. It does not reliably record what it
*learned*, and nothing makes it look at what it already learned before learning it again.

`RULE-2026-0022` closed this for one subject: every `<system>-access` skill owns a `knowledge/`
folder, entries carry `pending` / `confirmed` / `refuted` / `deprecated`, and an agent searches
that folder before re-investigating an API surprise. It works, and its scope is external APIs
only. Everything else the brain discovers - a method that failed and why, a constraint found by
experiment, a correction the owner had to give twice - lands in a `KNOWLEDGE.md` paragraph with
no status, no evidence, no review, and no way to retire it when it stops being true.

Three consequences follow. Discoveries survive only when the owner asks at the right moment, as
`RULE-2026-0032` records of its own origin. A wrong belief written once is never refuted, only
buried. And nothing measures whether any of it is ever found again, let alone whether finding it
helped.

## Current wording

No rule with the ID `RULE-2026-0043` exists. The root ID list in `/RULES.md` runs `0003`, `0004`,
`0010`, `0013`, `0015`, `0016`, `0017`, `0018`, `0022`, `0023`, `0025`, `0028`, `0029`, `0030`,
`0032`, `0033`, `0034`, `0035`, `0037`, `0039`, `0040`, `0042`; `0043` is free.

The adjacent live rules, which this one extends rather than restates:

- `RULE-2026-0010` - internal-first then external lookup, with a targeted search and no
  exhaustive grep.
- `RULE-2026-0022` - per-API quirk knowledge base, its status lifecycle, and its opportunistic
  promotion and refutation.
- `RULE-2026-0028` - the multi-model checkpoint test, including "If distinct models are
  unavailable, disclose the limitation and do not claim that multi-model review occurred."
- `RULE-2026-0037` - delegated parallel work: depth one, at most four workers, workers write no
  canonical file and never commit.

## Proposed wording or exact diff

Insert in `/RULES.md` immediately before `## Contract restatements`:

```markdown
## RULE-2026-0043 – Evidence-driven learning

- **Check at the start; never hold up the work.** On entering a task, run the discovery check in `/shared/skills/learning-maintenance/`: one local index read, no corpus load. Maintenance runs
  only as bounded background work and never delays the owner's task. Where the host cannot run it, the work stays pending and recoverable on its `/tasks/`
  record, and no background execution is claimed.
- **Try, observe, capture.** Within safe bounds prefer trying and observing to asking; a contained
  failure is a result. Safeguards for consequential or irreversible actions are unchanged. Capture,
  at the natural checkpoint, durable discoveries, owner corrections and preferences, decisions and
  useful negative findings, into the owning subject's canonical store: the `knowledge/` folder of `RULE-2026-0022`, the node's `KNOWLEDGE.md`,
  or its `data/learnings/` when neither fits. One record for its whole life. Routine activity and
  anything already recorded need none; an unsurprising finding may still be worth keeping. A
  provisional claim is marked as one and stays out of established knowledge until its evidence
  supports it.
- **Then research outside, in proportion.** After implementation or investigation, including work
  that succeeded, research external experience in proportion to the decision, to enrich, confirm or
  correct what was captured. Never before experimenting as a matter of course, and never delaying
  the requested work. Record what a source recommends separately from what was verified
  here; the skill holds source selection, provenance and verification.
- **Search before repeating.** On a material unexpected outcome, a repeated failed approach, a
  contradiction, or an inability to proceed, use `/shared/skills/problem-recovery/` to run the
  internal-first search of `RULE-2026-0010` and `RULE-2026-0022` across every subject, not external
  APIs alone, weakening neither.
- **Review and retire on evidence.** Review pending records opportunistically. Evidence status and
  review status are independent: a verified result may be used before review, and agreement alone
  confirms nothing. A second model is `RULE-2026-0028`'s test, which another session, thread or
  persona does not meet; an unknown model is recorded as unknown. Reversible, evidence-backed
  maintenance needs no permission: deduplicate, repair, narrow, confirm, refute, supersede, or
  withdraw from routine retrieval, preserving history and known exceptions. Age and frequency
  direct where to look and settle nothing.
  Protected governance, owner decisions and `/raw/` are out of scope.
- **Prove a deliberate forgetting.** A significant supersession or withdrawal carries proportionate
  validation first: that the obsolete advice no longer directs action, and that a valid rare
  exception remains usable. A script check is not a fresh-agent behavioural trial.
- **Measure what can be observed.** Record whether an applied record proved helpful, ineffective or
  harmful, and how that is known: self-report, an observed outcome, or independent confirmation.
  `unknown` is permitted and preferred to a guess. Count retrieval and application separately.
- **Escalate narrowly; stay quiet otherwise.** Raise a matter at once when it needs the owner's
  authority, when a consequential trade-off needs their judgement, when uncertainty about their
  goals or assumptions blocks a useful decision, or when a finding materially affects the work in
  front of them. Merely relating to that work is not a reason to interrupt. Ordinary maintenance is
  silent. The weekly digest presents every new learning and substantive change since the one last
  presented, retirements and uncertainty included, offered once when due in a session already
  running; preparing or presenting is not acceptance.
- Background review is bounded by `RULE-2026-0037` and amendment A3 to `RULE-2026-0032`. Workers
  return results; the launching thread validates and integrates them by the integration procedure
  in `/shared/skills/learning-maintenance/`, which with `/shared/skills/problem-recovery/`
  implements these duties and may not expand them.
```

Append `0043` to the root ID list in `/RULES.md` and set `accepted_proposal: RULE-2026-0043`.

`/RULES.md` holds 29 em dashes predating `RULE-2026-0042`. That rule requires them corrected
"when its file is next touched for another reason, in the same commit", so this implementation
converts them, excluding none. That is a mechanical replacement of one character, named here
because it lands in the same commit as a governance change.

## Reason

One rule, four duties, and every mechanism somewhere else.

An earlier draft of this rule ran 515 words, longer than any rule in the file, and most of that
length was machinery: claim heartbeats, revision-aware review receipts, index repair. Root
`/RULES.md` is read on every bootstrap, so its cost is paid by every session forever
(`RULE-2026-0004`). Machinery belongs in a skill, where it can change without an acceptance
question, and where `RULE-2026-0028` has already set the pattern: "The mandatory semantics are
contained in this rule", with the skill supplying operational detail and permitted neither to
weaken the requirements nor to expand an agent's authority.

The rule therefore states only what an agent must do and what it is thereby permitted to do, and
it points at `0010`, `0022`, `0028` and `0037` rather than paraphrasing them. Three overlapping
statements of one duty is how an agent ends up following none of them precisely.

## Scope and behavioural consequences

Repository-wide, every agent, from acceptance onward.

What changes for the owner: discoveries stop depending on the owner asking at the right moment;
a weekly digest is offered once when due and never repeated; wrong records get refuted instead of
buried; and the owner keeps every decision that matters, because protected governance and owner
decisions are excluded from the maintenance authority.

What changes for agents: a capture duty at checkpoints, a search duty on surprise, an
opportunistic review duty, and a standing permission to fix and retire ordinary records
reversibly without asking.

What moved out of the rule and into `/shared/skills/learning-maintenance/`, where it binds just
as tightly but costs no bootstrap tokens and needs no acceptance question to change: the record
fields and categories, the review receipt and its revision check, the atomic claim and its
expiry, index generation and repair, board generation, the one-worker and three-record caps on a
background run, and the routing of evidence out of `/temp/` before a run closes. Two points that
sat in the earlier draft are not restated anywhere because an existing rule already carries them:
preparing a digest is not acceptance (CONTRACT §13.2), and a disclosure duty when distinct models
are unavailable (`RULE-2026-0028`).

What does not change: no scheduler, no vendor, no subscription, no credential, no new bootstrap
file. `/BOOTSTRAP.md` is untouched; the discovery check is a rule-level duty bounded to one local
index read, and on a missing index the record scan is a background repair task, never an
exhaustive grep in the foreground. `contract_version` stays `0.9.0` - a root rule, not contract
behaviour.

The rule creates no obligation a host cannot meet. Where background work is unavailable the duty
defers to a `/tasks/` record and says so, which CONTRACT §14 requires.

## Risks and conflicts

- **The agent often grades its own homework, and nothing here fixes that.** The rule therefore does
  not record an outcome alone; it records the outcome with its basis, one of `self_report`,
  `observed` or `independent`, and permits `unknown`. That makes the weakness visible in the data
  rather than removing it: a corpus of `helpful / self_report` says considerably less than the same
  count of `helpful / observed`, and a reader can tell the difference.
  **What the validation below does not show.** The baseline and the correction test demonstrate
  that the pipeline records, surfaces and corrects an outcome. Neither establishes that the
  self-reports are accurate, and no claim to that effect should be made from them. Measuring
  accuracy would need outcomes graded by someone other than the applying agent, which was
  considered and rejected as more owner work than the whole rule saves.
- **Generated views versus preflight.** The discovery index and the weekly board are generated
  Markdown, and CONTRACT §15 requires front matter and a `/CONTRACT.md` reference from every
  Markdown file outside `/raw/`, its parent README to list the folder, and `RULE-2026-0040` a
  declared order. The generator must emit all of that, and the migration step says so. An
  append-per-session event log would put a diff in nearly every commit, against
  `RULE-2026-0017`; the events therefore live under `/temp/` for the session and are folded into
  the durable record at the checkpoint that writes it.
- **Erroneous retirement.** Withdrawal is from routine retrieval, not deletion; history is
  preserved; `/raw/` is immutable; protected governance is excluded. A wrong retirement is undone
  by reversing a status.
- **Overlap with `RULE-2026-0022`.** That rule keeps its subject, its filenames and its status
  vocabulary unchanged. `0043` adds subjects beyond external APIs, and adds capture, measurement
  and retirement. `0022`'s preference for opportunistic promotion over a scheduled review is the
  same preference this rule states.
- **Overlap with `RULE-2026-0028`.** The second-model test is `0028`'s and is referenced, not
  restated, so there is one place to change it.
- **It cannot guarantee obedience.** Nothing in a rule makes a future model follow it. The
  measurement exists so the owner can see whether it is being followed at all.

## Migration

1. Add `/shared/skills/learning-maintenance/` and `/shared/skills/problem-recovery/` with
   `SKILL.md` under CONTRACT §10.2, carrying the mechanism this rule deliberately omits: record
   fields, review receipts identifying the exact revision reviewed, atomic task claims, index
   generation and repair, board generation.
2. Register both in the `/shared/skills/README.md` folder list and the shared-skill table in
   `/ONBOARDING_AGENT.md`, or preflight fails the README check.
3. Create `/projects/brain-development/data/learning/` for the generated index and board, with a
   README entry, front matter on every generated Markdown file, and a stated sort order. Add the
   learning-operation summary and the digest dates to `/projects/brain-development/STATE.md`.
4. Seed by reference only: a bounded set of existing lessons and HighLevel quirks, pointed at
   where they already live. Do not rewrite historical knowledge and do not invent historical
   usage.
5. Take the measurement baseline before capture is switched on, in the manner of
   `/projects/brain-development/data/ai-communication-efficiency-baseline-2026-08-12.json`.
6. Present the board to the owner before building any interactive feedback control. Until then
   feedback is given in any thread by learning ID and written to the canonical record.
7. Both skills are drafted for review under
   `/projects/brain-development/proposals/RULE-2026-0044-destination-skills/`:
   `learning-maintenance.SKILL.draft.md` covers the discovery check, per-run bounds, claims and
   their expiry, the single integration lock and its recovery, index repair, board generation,
   record fields, provisional versus established, external research and provenance, reviewer
   eligibility, review receipts, digest tracking across threads, owner feedback, measurement, the
   validation of a deliberate forgetting, and the tests.
   `problem-recovery.SKILL.draft.md` covers the ordered search, the bounded attempt and the report
   of what remains unresolved; it was missing from the first round, which named the skill in the
   rule without supplying its text. Both are deliberately outside `/shared/skills/`: an unaccepted
   obligation in an active instruction path would be read as policy. They are built and reviewed
   **before** this rule is made active, so the rule never names a skill that does not yet carry its
   procedure.

No change to protected schemas, `/BOOTSTRAP.md`, or the preflight validator is authorised here.
Any of those is a separate proposal.

## Rollback

Remove the `RULE-2026-0043` section from `/RULES.md`, drop `0043` from the root ID list, restore
`accepted_proposal`, and set this proposal to `reverted`. The em-dash correction stays; it is
required by `RULE-2026-0042` independently of this rule.

Captured records, their history and owner input are kept. A faulty mechanism is disabled by
withdrawing the skills, which stops the duty being actionable without destroying what it
collected.

## Validation

- Repository preflight before and after reports the same result. Current baseline:
  **PASS, 0 errors, 4 warnings** (2026-09-17: undocumented folders under
  `/projects/brain-development/README.md`, a CRM documentation project's `README.md`,
  `/README.md` and `/temp/README.md`).
- `grep -c "–" RULES.md` returns **`1`**, not `0`: the single remaining em dash is the character
  itself, quoted inside `RULE-2026-0042`, which cannot state its rule without naming the mark it
  forbids. The `0` here was wrong and would have failed. `RULE-2026-0044` was corrected in the
  previous round and this was missed.
- A fresh session finds an eligible pending record without reading unrelated record bodies.
- An identical-model review does not satisfy the second-model test, and an unknown model is
  recorded as unknown rather than assumed independent.
- Two threads claim the same maintenance task; one writes, the loser cannot integrate, and
  repeating the integration changes nothing.
- A changed record invalidates a review taken against its previous revision.
- A fictional API failure retrieves the right quirk, follows current advice, refuses superseded
  advice, keeps a valid rare exception, and surfaces a contradiction rather than resolving it.
- Retirement never follows from age alone, and touches no protected governance and no `/raw/`
  file.
- **The grader test:** a record is applied, the outcome is recorded as helpful, and the later
  evidence shows it was not. The record must be correctable, and the correction must be visible
  in the weekly digest.
- Structural results and model-behaviour results are reported separately, and any case not
  actually run is labelled as unrun.
- **Evidence may be gathered before acceptance, and an earlier report of mine wrongly said it could
  not.** Acceptance must precede an active governance change; it need not precede a test. Every
  concurrency case, the lock fencing, the journal recovery and the digest delivery cases can be
  prototyped now against fictional records in a scratch directory, outside `/shared/skills/` and
  outside any active instruction path, on the owner's authorisation. Doing so would convert the
  interruption behaviour from designed to demonstrated before the rule is accepted, which is the
  right order. The behavioural trials that need a fresh agent on a real host still wait for the
  skills to exist.

## Acceptance

This proposal is offered separately from amendment A3 to `RULE-2026-0032` and from
`RULE-2026-0044`. That separation is a deliberate choice, not a contractual requirement: CONTRACT
§13.2 permits acceptance of an "exact change set", so a clearly identified bundle would be valid.
They are kept apart because they carry different risks and a reader should be able to decline the
conductor exception without declining the learning rule.

**Question to ask:** 1. Accept `RULE-2026-0043` as written, with the em-dash correction of
`/RULES.md` in the same commit (recommended); 2. accept the rule, and defer the em-dash
correction to its own commit; 3. accept with wording changes; 4. reject.

Not yet requested at the time of writing. Do not treat silence, adjacent approval or general
agreement as acceptance.

## Implementation record

Not implemented. This proposal is `proposed` only, and no protected file has been changed.

## Accepted publication revision

Accepted by the owner at 2026-09-17T17:14:19+10:00 in the Codex task, exact response: "Accept both as written." The timestamp is when acceptance was recorded; the host did not expose a separate message timestamp. This revision supersedes all earlier proposed implementation and acceptance instructions above.

## RULE-2026-0043 – Evidence-driven learning

- **Keep the owner’s work first.** At task entry, check the compact learning index for relevant pending work. Do not load the learning corpus. Maintenance runs as bounded background work; when unavailable, leave it pending for a later session. Never claim background execution that did not occur.
- **Try, observe and capture.** Within existing safeguards, prefer bounded experimentation when appropriate. At natural checkpoints, capture useful discoveries, failures, recurring errors, negative findings, owner corrections, preferences and decisions without waiting for a reminder. Update an existing record rather than duplicate it. Routine activity needs no learning record.
- **Keep knowledge with its subject.** Each learning has one canonical home in the owning subject’s knowledge store or `data/learnings/`; other projects reference it. Record the observation, supporting evidence, applicability, assumptions, proposed response and unresolved questions. Keep provisional claims out of established `KNOWLEDGE.md`.
- **Search before repeating.** When something unexpected happens, an approach repeatedly fails, evidence conflicts or progress is blocked, use `/shared/skills/problem-recovery/` to search relevant brain knowledge before reinvestigating. Check the relevant API quirks when applicable. Bound recovery effort across the problem; a failed attempt may lead to research, a materially different hypothesis or a pending investigation.
- **Bring in external evidence.** After meaningful implementation or investigation, including successful work, research external experience proportionately to improve the learning. This is not a routine prerequisite to experimentation. Distinguish source recommendations from locally verified outcomes and preserve provenance. Six Thinking Hats remains optional.
- **Cross-check opportunistically.** Later sessions review eligible pending learning. Record the originating and reviewing models when known. Same-model and unknown-model reviews remain useful but do not count as independent-model review. Evidence status and review status are separate: model agreement alone never confirms an empirical claim. Investigate disagreements and their assumptions.
- **Maintain and forget deliberately.** Agents may reversibly deduplicate, repair, narrow, refute, supersede or withdraw ordinary learning from routine retrieval when evidence supports it. Preserve history and valid exceptions. Age and frequency guide investigation but do not establish truth or justify retirement alone. Validate significant retirement by testing both non-use of obsolete advice and continued access to valid exceptions. Protected governance, owner decisions and raw evidence remain outside this maintenance authority.
- **Learn from use and owner input.** Distinguish retrieval from application, and usefulness from truth. Record helpful, ineffective, harmful or unknown outcomes with their evidence basis. Preserve owner feedback and classify it as preference, decision, usefulness assessment or factual observation. Apply it within its stated scope; investigate factual contradictions.
- **Interrupt only when needed.** Contact the owner when authority is required, a consequential trade-off needs judgement, uncertainty about their goals blocks a useful decision, or a finding materially affects current work. Failure or disagreement alone is not an escalation trigger. Ordinary maintenance stays silent.
- **Present a weekly review.** When due during an active session, present new learning and substantive changes since the previous delivered review, including retirements and uncertainty. Track delivery; label a possible repeat after uncertain delivery. Presentation is not acceptance of proposed governance changes.
- **Use one integration writer.** Background workers return findings and do not edit canonical learning or shared views. One designated integration writer, recorded in brain-development state, validates and integrates results. Other threads leave findings in separate pending artifacts. Do not take over while that writer may still be active; defer when ownership is uncertain. `/shared/skills/learning-maintenance/` implements this process without expanding its authority.

Scope: the two portable skills, separate pending artifacts and canonical task routing, generated index and review board, digest delivery state, required registration and validation. One designated writer; no prototype code activated. RULE-2026-0044 is not accepted. Contract version remains 0.9.0.

Reason: make useful learning automatic without holding up foreground work. Risk: cooperative single-writer designation is not a distributed lock; uncertain ownership defers integration. Fresh-agent behaviour remains to be evaluated. Rollback removes 0043 and amendment A3 and disables their triggers, preserving evidence, records and history. Validation: exact accepted-text comparison, repository preflight, reference and scenario checks; fresh-agent trials explicitly tracked as unrun.

Implementation of the accepted publication revision completed at 2026-09-17T17:56:12+10:00. Supporting skills and state use the single designated writer; no concurrency prototype activated. Structural checks pending before commit; fresh-agent trials tracked explicitly as unrun in TASK-2026-0051.

Validation at 2026-09-17T17:57:06+10:00: repository preflight PASS, 0 errors and the four existing README warnings. Exact accepted 0043 and A3 wording verified in live RULES; other rule bodies preserved except the existing dash convention. Fresh-agent behavioural trials remain unrun under TASK-2026-0051. No prototype or 0044 activation.

## Amendment A1 (2026-09-17T23:30:00+10:00, revised 2026-09-18T00:00:00+10:00): one writer at a time, not one writer for all time

**Status of this amendment: accepted and implemented (2026-09-18T00:30:00+10:00).** Accepted by the owner in the word "1.", option 1, the revised wording as written. Revised at the owner's direction of
2026-09-17: "the single writer is important at any point in time, but it does not have to be the
same one for every write of that file." That distinction replaces the first draft of this
amendment, which proposed dropping the single writer altogether. A small change to a live rule keeps
its ID.

### Current problem

The rule ties exclusion to a **session** rather than to a **write**. One designated writer is
recorded in state and holds the role until it releases it. Two consequences followed within one
evening of activation, both structural:

- **Integration stalls.** A session ends; the designation does not. The role then names something
  unreachable, the inbox fills, and nothing integrates. The skill correctly refuses to let a session
  elect itself from silence or elapsed time, so the only way out is the owner intervening by hand.
  An owner-reassignment clause added the same evening makes the owner the manual unblocker rather
  than removing the stall.
- **The weekly review could not happen.** The skill restricted presentation to the writer, and the
  writer will usually not be the session active when the digest falls due. Repaired separately at
  `e57700b`.

The first draft of this amendment concluded that the single writer should go entirely, with Git
catching collisions. The owner's correction is more precise and is right: **the property that
prevents corruption is that only one writer writes at a time. Nothing requires it to be the same
writer each time.** Tying a momentary property to a durable identity is what produced both stalls,
and it bought nothing, because the exclusion that matters lasts for the seconds of a write.

### Current wording

`/RULES.md`, final bullet of `RULE-2026-0043`:

```markdown
- **Use one integration writer.** Background workers return findings and do not edit canonical learning or shared views. One designated integration writer, recorded in brain-development state, validates and integrates results. Other threads leave findings in separate pending artifacts. Do not take over while that writer may still be active; defer when ownership is uncertain. `/shared/skills/learning-maintenance/` implements this process without expanding its authority.
```

### Proposed wording

Replace that bullet with:

```markdown
- **One writer at a time, not one writer for all time.** Background workers return findings and do not edit canonical learning or shared views; the thread that launched a worker validates and integrates its results. Any session may integrate, and while it writes it must be the only writer: exclusion lasts for the write and never outlives the session holding it, so no designation goes stale and no work waits on a session that has ended. Re-read the target inside that window, stage only its own paths, and treat a Git conflict as the signal to reconcile rather than overwrite. Generated views are derived from the records and are regenerated after integration, never edited as source. `/shared/skills/learning-maintenance/` implements this process without expanding its authority.
```

Removed: the durable designation and its state record. Kept: exclusion during the write, workers out
of canonical files, the launching thread owning its worker's results, and the authority clause.

### Scope and behavioural consequences

Repository-wide, every agent, from acceptance.

**What changes.** Exclusion becomes a property of the operation rather than of a session. A session
with learning to record takes exclusion, writes, releases, and is done. The `Learning operation`
section stops naming a writer and stops being a thing that can go stale. The inbox stops being
mandatory for non-writers and becomes what it should have been: where a worker returns findings, and
where a session may leave a candidate when it does not want to choose the canonical home itself.

**What does not change.** `RULE-2026-0037` still keeps workers out of canonical files.
`RULE-2026-0017` still requires path-scoped staging. Generated views are still derived. The digest
works as repaired at `e57700b`.

**The mechanism, and why it is already measured.** An OS-held exclusive lock gives exactly the
property the owner named: `msvcrt.locking` on Windows, `fcntl.flock` on POSIX, taken for the write
and released by the kernel if the holder dies. It cannot go stale, because nothing about it outlives
the process. That was measured on this host on 2026-09-17 and the measurement survives as the
learning record `filesystem-primitives-on-this-host`, written the same day the prototype that
produced it was deleted. The prototype was deleted for proposing a durable lease with a fencing
token, which is the same mistake as a durable designation. The one finding worth keeping is now the
mechanism.

**Where it does not hold, stated rather than implied.** An OS lock serialises processes on one
machine and one filesystem. It does nothing across separate synced checkouts, which share no kernel.
There, Git is the backstop: a concurrent write is a merge conflict, visible and recoverable. That is
a weaker guarantee and the honest one.

### Migration

1. Replace the bullet in `/RULES.md`; set `accepted_proposal: RULE-2026-0043`.
2. `/shared/skills/learning-maintenance/SKILL.md`: replace `Single-writer integration`, including
   the owner-reassignment clause it no longer needs, with an `Integration` section specifying
   exclusion for the duration of the write by OS lock, re-read inside the window, path-scoped
   staging, conflict reconciliation and view regeneration. Remove the durable writer from `Purpose`,
   `Invocation and required inputs`, `Allowed operations and permissions`, `Capture and pending-work
   routing`, `Index, board and weekly delivery` and `Logging and state`. Make the inbox optional and
   say what it is still for.
3. `/projects/brain-development/STATE.md`: remove the writer fields from `Learning operation`,
   leaving the operational facts that are still true.
4. Regenerate `index.md` and `board.md`, whose headers currently name a writer.
5. Run preflight; expect PASS, 0 errors, 4 pre-existing warnings.

### Rollback

Restore the bullet from this record, restore `Single-writer integration` from `f8ed317`, and set this
amendment to `reverted`. Captured learning is unaffected: this changes who may write a record and
when, not what a record is.

### Validation

- Preflight unchanged from the 4-warning baseline.
- A session that was never designated records a learning directly to its canonical home and commits,
  with nothing left pending. This is the case that could not happen before.
- A session that dies mid-write leaves no exclusion behind, which is the property a durable
  designation could not provide and the OS lock gives for free.
- The inbox still accepts a worker's returned findings.
- The weekly digest still surfaces for any session, unchanged from `e57700b`.
- **Unrun, and honestly so:** no deliberate two-session write collision has been staged against the
  live records. The OS lock's behaviour was measured in an isolated prototype on this host, not
  against `/projects/brain-development/data/learnings/`, and the POSIX path remains unrun.

### Acceptance

**Question to ask:** 1. Accept amendment A1 as revised, exclusion per write rather than a designated
session (recommended, and the distinction you drew); 2. accept, but keep the inbox mandatory for
workers rather than optional; 3. accept with wording changes; 4. reject and keep the designated
writer.

**Accepted by the owner, 2026-09-18T00:30:00+10:00**, in the word "1." (option 1, as written).

### Implementation record

Implemented the same minute. `/RULES.md`: the final bullet of `RULE-2026-0043` replaced with the
accepted wording; `accepted_proposal` already `RULE-2026-0043`; `updated` set from the
implementation clock. One em dash remains in the file, the character quoted inside `RULE-2026-0042`,
unchanged and correct.

`/shared/skills/learning-maintenance/SKILL.md`: `Single-writer integration` replaced by
`Integration`, specifying exclusion by OS lock for the duration of each write, re-read inside the
window, path-scoped staging, conflict reconciliation and view regeneration, with the synced-checkout
limit stated. The owner-reassignment clause removed with the section it existed to unblock. The
durable writer removed from `Purpose`, `Invocation`, `Allowed operations`, `Capture routing`,
`Index, board and weekly delivery`, `Failure behaviour` and `Logging and state`. The inbox is now
optional, and the skill says what it is still for.

`/projects/brain-development/STATE.md`: `Learning operation` rewritten with no designation. The two
earlier designations are recorded as history rather than state.

Views regenerated. Preflight PASS, 0 errors, 4 pre-existing warnings, unchanged from the baseline.
Contract version unchanged at 0.9.0: a root rule, not contract behaviour.

Unresolved and stated rather than closed: no deliberate two-session write collision has been staged
against the live records, and the POSIX lock path remains unrun. The claim that this is safe rests on
a measurement made in an isolated prototype on this host plus the repository's own daily history.
