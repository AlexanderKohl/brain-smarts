---
id: RULE-2026-0022
title: Per-API quirk knowledge base – check-first, log-on-resolution, skill scaffolding
type: governance_proposal
schema_version: 0.2
contract: /CONTRACT.md
status: verified
proposal_id: RULE-2026-0022
owner: brain-owner
created: 2026-08-24T20:45:00+10:00
updated: 2026-08-24T21:15:00+10:00
accepted_by: brain-owner
accepted_at: 2026-08-24T21:05:00+10:00
implemented_at: 2026-08-24T21:10:00+10:00
previous_contract_version: 0.6.2
new_contract_version: 0.6.2
target_files:
  - /RULES.md
  - /shared/templates/api-knowledge-entry.template.md
project_refs:
  - /memory/projects/brain-development
---

# RULE-2026-0022: Per-API quirk knowledge base

## Plain-language summary

Right now, when an agent and their human colleague work out something non-obvious about an external API (an undocumented field key, a write shape that only works for one object type, an error string that means something different than it says), that finding only lives buried in one project's `LOG.md` or in an external repo's commit message. The next time the same API surprises us – possibly in a different project, possibly months later – nobody checks for it and nobody finds it, so it gets rediscovered the hard way.

This proposal adds a rule that:

1. every `<system>-access` shared skill gets a `knowledge/` folder for small,
   one-fact-per-file quirk entries, scaffolded automatically when the skill
   is created (or retrofitted the first time a quirk is found for a system
   that has no skill yet);
2. before diagnosing unexpected API behaviour, an agent must search that
   folder first (by filename convention and by frontmatter tags – no
   hand-written index to keep in sync);
3. after resolving something genuinely non-obvious, an agent must write one
   small entry, not touch anything for routine work;
4. entries carry a `pending -> confirmed | refuted` / `confirmed ->
   deprecated` status lifecycle, so a fix based on an unverified guess is
   flagged as such until real evidence confirms or contradicts it, and stale
   knowledge is marked rather than silently trusted.

Nothing in this proposal touches `CONTRACT.md` or bumps `contract_version` –
it is root `RULES.md` operating-rule content only, plus one new shared
template.

## Current problem

Real example from a client form project's `LOG.md`
(2026-08-24 entries) and the linked external repo's commit history
(e.g. `e98e46c`, `7d46c35`, `dc974ed`,
`cbf37fa`): across a single day of work on one HighLevel integration, the
same category of fact had to be independently rediscovered multiple times –
that Monetary and Textbox List custom fields serialise differently per
*object type* (Business/Custom Object via the Objects API vs. Contact/
Opportunity via classic endpoints), that a Business Textbox List field
echoes back as two compound-key `customFields` entries rather than one, that
classic-endpoint reads need type-specific `valueString`/`valueNumber`/
`valueDate`/`valueCurrency`/`valueFiles` fallbacks, and that Opportunity's
single-file write endpoint silently drops the real filename unless sent
through the multi-file array shape. One of these was fixed, shipped, and
later found to be wrong for two of the four object types (`e98e46c` →
refuted and corrected by `7d46c35`) – a correction that itself is only
discoverable today by reading commit messages end to end.

None of this is durable or indexed anywhere:

- `LOG.md` is chronological and project-scoped – useful as a record, not as
  a lookup surface for "what do we already know about HighLevel's Business
  object write shapes."
- The external app repo's commit messages are excellent narratives but are
  not part of this repository and are not searchable by object/field/
  endpoint.
- No shared skill (`gohighlevel-access` or any other `*-access` skill)
  currently has any place to hold this kind of fact – confirmed by
  inspection: none of `gohighlevel-access`, `xero-access`, `railway-access`,
  `abr-access`, `google-drive-access`, `google-workspace-access` has a
  `knowledge/` folder or equivalent today.
- Root `RULES.md` already requires checking the brain before an external
  lookup for facts in general (`RULE-2026-0010`), but nothing requires
  checking, or contributing to, a specific per-API quirk store – there
  isn't one to check.

## Current wording

Root `/RULES.md` "Repository rules" has no bullet addressing API-specific
undocumented-behaviour knowledge. The closest existing rule is:

```markdown
- When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge, and other already-known canonical homes) with a **targeted** search. Do not run exhaustive repository grep theatre to prove absence.
- If the fact is absent or still uncertain after that internal check, use the authoritative external shared skill when one exists or is mandated (for example ABR Web Services for Australian Business Numbers and GST registration). After a verified external result, update the relevant durable brain record when the fact belongs in the repository.
```

This is general-purpose and does not define a canonical home, entry format,
write trigger, or status lifecycle for API-specific quirks.

## Proposed wording or exact diff

### 1. Add to root `/RULES.md` "Repository rules" (protected)

```diff
 - When looking up a fact or identifier, check the brain first (CRM contacts, project knowledge, and other already-known canonical homes) with a **targeted** search. Do not run exhaustive repository grep theatre to prove absence.
 - If the fact is absent or still uncertain after that internal check, use the authoritative external shared skill when one exists or is mandated (for example ABR Web Services for Australian Business Numbers and GST registration). After a verified external result, update the relevant durable brain record when the fact belongs in the repository.
+- Every shared `<system>-access` skill owns a `knowledge/` folder beside its `SKILL.md`, holding one small file per confirmed or hypothesised piece of non-obvious external-API behaviour for that system. Scaffold it (empty, plus one `_CONVENTION.md` copied from `/shared/templates/api-knowledge-convention.template.md`) whenever a new `<system>-access` skill is created. If a quirk worth logging is found for a system with no shared skill yet, create the minimal skill folder and its `knowledge/` scaffold first rather than leaving the finding without a canonical home.
+- Before diagnosing unexpected, undocumented or previously-surprising behaviour from an external API, search that system's `knowledge/` folder first – by filename convention (for example `Glob "business--*"` for one object type, `Glob "*--textbox-list--*"` for one field type across objects) and by frontmatter (`Grep` for `object_type:`, `field_type:`, `endpoint:` or `status:`) – before re-investigating from scratch. Treat a `refuted` entry as a warning against repeating that exact hypothesis; treat a `deprecated` entry as a pointer to its `superseded_by` replacement, not as current fact.
+- After a fix or investigation resolves genuinely unexpected or undocumented external-API behaviour, write one entry under that system's `knowledge/` folder, copied from `/shared/templates/api-knowledge-entry.template.md`, named `<object_type>--<field_or_topic>--<short-slug>.md`, with `system`, `object_type`, `field_type`, `endpoint`, `status` and `source_refs` set. Do not create an entry for routine work that reveals nothing unexpected about the external API – this store is for quirks and workarounds, not a general changelog.
+- Set a new entry's `status` to `pending` when the fix it documents relies on a hypothesis not yet independently confirmed; set `confirmed` only once a live probe or observed real subsequent use corroborates it. When later evidence contradicts a `pending` or `confirmed` entry, do not delete it: set `status: refuted` for a wrong hypothesis or `status: deprecated` for behaviour that has genuinely changed, add a one-line note of what changed and when, and set `superseded_by` or leave it for the correcting entry to backlink via `refuted_by` once one exists.
+- Promote, refute or deprecate an existing entry opportunistically – the next time work touches that same quirk and turns up corroborating or contradicting evidence – rather than deferring it to a scheduled review that does not otherwise exist in this repository.
```

### 2. New shared templates (not protected governance – created on acceptance)

`/shared/templates/api-knowledge-entry.template.md`:

```markdown
---
id: SYSTEM-OBJECT-TOPIC-SLUG
title: One-line description of the specific behaviour
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: SYSTEM_SLUG
object_type: OBJECT_TYPE
field_type: FIELD_TYPE_OR_NULL
endpoint: METHOD /path
status: pending
superseded_by: null
refuted_by: null
discovered: YYYY-MM-DD
verified: null
source_refs:
  - /projects/EXAMPLE/LOG.md#TIMESTAMP
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---

# Title

## Behaviour

What actually happens, stated precisely – exact wire shape, exact error
string, exact field/key names. Prefer a literal request/response fragment
over a paraphrase.

## Why it's non-obvious

What the official docs say or imply instead, or why this could not have
been guessed without trial and error.

## Evidence

How this was confirmed and when: a live raw-API probe, a production log,
an official SDK example, etc. State whether this is a `pending` hypothesis
or independently `confirmed`.

## Applies to

Which object type(s)/field type(s)/endpoint(s) this is confirmed for.
State explicitly when a sibling object type or endpoint is known to behave
*differently* – do not let a future reader assume this generalises.
```

`/shared/templates/api-knowledge-convention.template.md` (copied into each
skill's `knowledge/_CONVENTION.md` at scaffold time):

```markdown
---
id: SYSTEM-knowledge-convention
title: Knowledge base convention for this skill
type: api_knowledge_convention
schema_version: 0.2
contract: /CONTRACT.md
---

# Knowledge base convention

One file per confirmed or hypothesised piece of non-obvious API behaviour.
Copy `/shared/templates/api-knowledge-entry.template.md` for a new entry.

## Filename

`<object_type>--<field_or_topic>--<short-slug>.md` – lowercase,
hyphen-separated segments, double-hyphen between the three parts.

## Status lifecycle

`pending` -> `confirmed` | `refuted`
`confirmed` -> `deprecated`

See root `/RULES.md` for when to create, promote, refute or deprecate an
entry.

## Finding entries

No hand-maintained index – use `Glob`/`Grep` directly against this folder:

- By object type: `Glob "business--*"`
- By field type: `Grep "field_type: textbox_list"`
- By endpoint: `Grep "endpoint: .*businesses/:id"`
- By status: `Grep "status: refuted"`
```

## Reason

The owner asked for a durable, structured, per-API record of quirky and
non-obvious behaviour, populated automatically as a by-product of ordinary
debugging work rather than as a separate task, checked automatically before
re-diagnosing something, and with an explicit way to mark a fix that later
turns out to be wrong or a behaviour that stops holding. Colocating each
system's knowledge with its existing `<system>-access` skill keeps one
canonical home per durable item (Contract §3.3) instead of creating a
second, competing "home" concept alongside skills. Filename convention plus
mandatory frontmatter was chosen over a hand-written index specifically
because the primary consumer is an agent with `Grep`/`Glob`, and a
hand-maintained index would duplicate frontmatter content and drift.

## Scope and behavioural consequences

- Applies to every external system an agent works with in this repository,
  not only ones that already have a `<system>-access` skill – the rule
  requires scaffolding one when a quirk is found for a system that has
  none yet.
- Changes agent behaviour going forward: a quirk-resolving fix session now
  ends with one additional small file write (not a chore for the owner –
  the agent does it as part of finishing the task), and a
  behaviour-diagnosis session now opens with a targeted `Grep`/`Glob`
  against the relevant skill's `knowledge/` folder before re-investigating.
- Does not create any new task type, project, or contract-level type
  enumeration change – `api_knowledge` and `api_knowledge_convention` are
  used as illustrative `type:` values under Contract §8.1, which already
  says the type list is non-exhaustive ("such as").
- Does not by itself backfill the client form project /
  `gohighlevel-access` history described above – that is separate,
  explicitly deferred implementation work the owner can request once this
  rule is active.
- No `contract_version` change – this is `RULES.md` operating-rule content
  and two new non-protected shared templates only.

## Risks and conflicts

- Judgement call risk: "genuinely unexpected" vs. "routine" is not
  mechanically checkable, so entry quality depends on the same agent
  judgement the rest of this repository already relies on (matches the
  existing pattern for `LOG.md` significance and `KNOWLEDGE.md` durability
  decisions – no new kind of risk introduced).
- A skill with a very active integration (like `gohighlevel-access`) could
  accumulate many small files over time; the filename-convention/frontmatter
  approach is chosen specifically to keep that scaling cheap (no index
  file to rewrite), but folder size itself is unbounded by this rule.
- `pending` entries are unverified by definition; an agent that trusts a
  `pending` entry as if it were `confirmed` would be repeating exactly the
  failure mode this proposal exists to prevent. The rule text calls out
  `refuted`/`deprecated` handling explicitly but relies on the reading
  agent to also respect the `pending` vs `confirmed` distinction.

## Migration

1. On acceptance, create the two new shared templates exactly as specified
   above.
2. Retrofit a `knowledge/` folder (empty, with `_CONVENTION.md`) into each
   existing `<system>-access` skill on first touch, not all at once – no
   bulk migration commit is required by this rule.
3. Backfilling the client form project's HighLevel quirks already
   known today is a separate follow-up task, not part of this proposal's
   acceptance.

## Rollback

Revert the root `/RULES.md` diff and delete the two new template files.
Any `knowledge/` folders and entries already created under this rule are
plain Markdown content – leave them in place (they remain useful reference
material) or remove them explicitly if the owner wants a full rollback.

## Validation

1. Apply only the accepted `/RULES.md` diff and create the two templates.
2. Confirm repository preflight still passes (front matter, contract
   reference, no protected-governance drift beyond this accepted change).
3. Report the exact files changed and commit hash.

## Acceptance

the owner explicitly accepted with "I accept" at 2026-08-24T21:05:00+10:00,
authorising the five new root `RULES.md` bullets exactly as written and
creation of the two new shared templates.

## Implementation record

Applied on 2026-08-24T21:10:00+10:00:

- `/RULES.md`: added the five bullets exactly as diffed above (skill
  scaffolding, check-first, write-on-resolution, status lifecycle,
  opportunistic promotion); `updated` and `accepted_proposal:
  RULE-2026-0022` set.
- `/shared/templates/api-knowledge-entry.template.md`: created exactly as
  specified.
- `/shared/templates/api-knowledge-convention.template.md`: created
  exactly as specified.

No `CONTRACT.md` change; `contract_version` remains `0.6.2`.

Per-skill `knowledge/` scaffolding is deliberately deferred to first touch
per the accepted rule's own migration text, not applied to every existing
`*-access` skill in this commit. Backfilling the
client form project's HighLevel quirks remains a separate,
not-yet-requested follow-up task.

Repository preflight: `python shared/skills/repository-preflight/scripts/preflight.py --root .`
→ **PASS** (`contract 0.6.2`; 2359 Markdown files; 2359 unique IDs) after
one fix during implementation (the convention template was initially
missing required `created`/`updated` metadata). Remaining preflight
warnings (undocumented immediate folders under `/temp/` and
`/projects/brain-development/`) are pre-existing and unrelated to this
change. Status → **verified**.
