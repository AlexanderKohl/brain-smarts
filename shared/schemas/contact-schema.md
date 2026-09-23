---
id: schema-contact
title: Contact and Persona Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-09-23T19:35:27+10:00
updated: 2026-09-23T20:15:32+10:00
---

# Contact and Persona Schema

Read `/CONTRACT.md` first. The brain-wide definition of a **contact** (a party the owner deals
with) and a **persona** (an identity the owner communicates as), so that any project, skill or
tool reads and writes them the same way whether or not the `crm` skill is switched on. The
procedures that keep a register – creation on first encounter, deduplication, newsletter
handling, directory sync – are in `/library/skills/crm/`, whose `crm_check.py validate` enforces
this schema; a test there fails when the checker and this schema disagree.

Contacts and personas are owner content, kept in memory in one contact register (by default
`/memory/projects/contacts/`): `contacts/contact-<slug>.md` and `personas/persona-<key>.md`.

## Contact

```yaml
---
id: contact-<slug>
title: Full name or organisation label
type: contact
schema_version: 0.2
contract: /CONTRACT.md
status: active
contact_kind: person
receiving_personas: []
preferred_reply_persona: null
newsletter: false
newsletter_read_detail: null
emails: []
phones: []
organisations: []
social_accounts: []
google_contact_refs: []
related_task_refs: []
related_project_refs: []
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---
```

### Contact fields

| Field | Values | Meaning |
|---|---|---|
| `contact_kind` | `person` (default) \| `organisation` \| `newsletter` \| `system` | What kind of party this is |
| `emails`, `phones`, `organisations`, `social_accounts` | lists | Identifiers used for lookup and deduplication |
| `google_contact_refs` | list of `alias:resourceName` strings | Google Contacts resource names per account alias, for example `personal:people/cEXAMPLE0001`; another directory adds its own `<system>_contact_refs` list when first needed |
| `receiving_personas` | list of `persona_key` | Owner identities this party writes to (the To or delivery address); may accumulate |
| `preferred_reply_persona` | `persona_key` or `null` | Identity to reply as; `null` means ask. Always `null` for newsletters and systems unless the owner sets one |
| `newsletter` | `true` \| `false` | Apply newsletter handling |
| `newsletter_read_detail` | `subject` \| `body` \| `body_and_images` \| `null` | How much of a newsletter to load; `subject` by default, `null` when not a newsletter |
| `related_task_refs`, `related_project_refs` | repository-root paths | Links to `/memory/tasks/` and project nodes |

Required on every contact and persona: `id`, `title`, `type`, `contract`, `created`, `updated`.

A contact merged into another becomes a pointer: `status: merged` and `merged_into: <kept id>`,
with its identifiers and notes moved to the kept record. Readers skip pointers.

Body sections, in order: Overview, Identifiers, Relationship, Reply guidance, Newsletter handling
(newsletters only), Notes (dated), To do.

There is no separate organisation record. An organisation the owner deals with as a party is a
contact with `contact_kind: organisation`; a person's employer is a string in that person's
`organisations` list. A company the owner **acts for** is a persona, not a contact. Add an
organisation record type only when a real need appears (CONTRACT §8.4).

## Persona

```yaml
---
id: persona-<key>
title: Persona display name
type: persona
schema_version: 0.2
contract: /CONTRACT.md
status: active
persona_key: <key>
company: personal
google_account_alias: null
primary_from_email: null
additional_from_emails: []
phones: []
social_sending_accounts: []
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---
```

### Persona fields

| Field | Meaning |
|---|---|
| `persona_key` | Stable key; the file is `persona-<key>.md` |
| `company` | `personal`, or the company the owner acts for in this capacity |
| `google_account_alias` | Alias in `data/google-accounts.json` whose mailbox sends for this persona; `/library/skills/google-workspace-access/` resolves it |
| `primary_from_email`, `additional_from_emails`, `phones`, `social_sending_accounts` | Outbound channels of this identity |

A persona is not an account. Several personas may share one mailbox, and one company may use a
mailbox of its own. Resolve the persona first, then take the account from the persona.

## Rules

- One file per real party; the owner's own addresses and numbers are never a contact's
  identifiers (they belong in `receiving_personas` or a persona).
- Never store a secret, token or recovery material in a contact or persona.
- Do not invent `preferred_reply_persona`; `null` means ask.
