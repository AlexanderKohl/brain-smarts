---
name: crm
description: Keep a flat-file contact register (CRM) in the owner's memory – one Markdown file per remote party, owner personas bound to sending accounts, automatic contact creation on first encounter, deduplication, newsletter handling and Google Contacts merge. Use whenever a person or organisation is mentioned with a durable fact, a new sender or correspondent appears, or a reply, appointment or contact-linked task is being prepared.
metadata:
  id: skill-crm
  title: Contact Register (CRM)
  type: skill
  schema_version: 0.2
  contract: /CONTRACT.md
  status: active
  scope: shared
  owner: brain-owner
  canonical_source: /shared/skills/crm
  script_paths:
    - /shared/skills/crm/scripts/crm_check.py
  skill_refs:
    - /shared/skills/abr-access
    - /shared/skills/google-workspace-access
  created: 2026-09-23T13:10:00+10:00
  updated: 2026-09-23T13:10:00+10:00
---

# Contact Register (CRM)

Read `/CONTRACT.md` first. This skill supplies the model, procedures, templates and a checker. The
operating rules of a CRM are node-owned: they live in the CRM node's own `RULES.md`, which starts
as a copy of `templates/node-RULES.template.md` and changes only under CONTRACT §13.2.

## Purpose

Give every agent one canonical place to remember the people and organisations the owner deals
with, and one way to decide **who the owner is being** when replying to them. The register is
plain Markdown in the owner's memory, so it works with any host, any mail system and no vendor
CRM. External directories (Google Contacts, a vendor CRM) supply identifiers; the narrative stays
here.

## Model

| Record | Where | What it holds |
|---|---|---|
| Contact | `<crm-node>/contacts/contact-<slug>.md` | One remote party: a person, an organisation, a newsletter sender or an automated system. Brief overview, identifiers, relationship, reply guidance, dated notes, open loops |
| Persona | `<crm-node>/personas/persona-<key>.md` | One owner identity used when communicating – personal capacity or a company the owner acts for: channels, voice, sign-off, bound sending account |
| Account registry | `<crm-node>/data/google-accounts.json` (and similar per system) | Non-secret account aliases and the vault entry each one uses; never a secret |

`<crm-node>` is the owner's CRM node in memory. A new brain ships it at
`/memory/projects/contacts/` (from `/shared/templates/memory-skeleton/projects/contacts/`); an
existing owner may keep another path and name it in `crm_root` of
`/memory/skills/google-workspace-access/config/crm.json`.

There is no separate organisation record. An organisation the owner deals with as a party is a
contact with `contact_kind: organisation`; a person's employer is a string in that person's
`organisations` list. A company the owner **acts for** is a persona, not a contact. Add an
organisation record type only when a real need appears (CONTRACT §8.4).

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

### Persona fields

| Field | Meaning |
|---|---|
| `persona_key` | Stable key; the file is `persona-<key>.md` |
| `company` | `personal`, or the company the owner acts for in this capacity |
| `google_account_alias` | Alias in `data/google-accounts.json` whose mailbox sends for this persona; `/shared/skills/google-workspace-access/` resolves it |
| `primary_from_email`, `additional_from_emails`, `phones`, `social_sending_accounts` | Outbound channels of this identity |

A persona is not an account. Several personas may share one mailbox, and one company may use a
mailbox of its own. Resolve the persona first, then take the account from the persona.

## Allowed operations

- Create, update and merge contact and persona files in the owner's CRM node.
- Read external directories through their own skills (Google Contacts through
  `google-workspace-access`) and merge identifiers into contacts.
- Run `scripts/crm_check.py` (read-only) to find, validate and deduplicate records.
- Record a tax-registration lookup result on a contact when the optional hook below is enabled.

Not allowed: deleting a contact that has notes or open loops (merge it instead and leave a
pointer), sending anything, writing to an external directory, storing any secret.

## Required inputs

- The CRM node path (above).
- For a new contact: at least one durable identifier (email, phone, handle, registered business
  number or a clear full name with context).
- For a reply: the contact and the channel; the persona comes from the contact or from the owner.

## Data sources

- The owner's own statements (the primary source for relationship notes).
- Messages the owner receives or sends, read through a mail skill.
- External directories such as Google Contacts, for identifiers only.
- Public registers for tax registration (optional hook).

## Procedures

### 1. The owner shares a fact about a person or organisation

1. Find the contact (`crm_check.py find --email … | --name … | --handle …`, or a targeted
   search of `contacts/`). Several matches: show them and ask; never guess.
2. None: create one (procedure 2).
3. Append a dated note; update overview, identifiers or reply guidance where the fact belongs
   there. Do this in the same session, before relying on the fact.
4. Set `preferred_reply_persona` when the owner says in which capacity they deal with them.

### 2. A new remote party appears – create on first encounter

A party is new when a message arrives from an address no contact holds, when a person or
organisation is mentioned with a durable identifier, or when a directory sync returns someone
not yet in the register.

1. **Deduplicate first**: search by every identifier (email case-insensitively, phone digits,
   handle, normalised name). Merge into an existing match rather than creating a second file
   for the same party.
2. Copy `contacts/_TEMPLATE.md` to `contacts/contact-<slug>.md`; `<slug>` is the lower-case,
   hyphenated name (add the organisation or place when names collide).
3. **First encounter – read the whole message.** For a new email party, read the full decoded
   body once, not the subject or preview alone, and extract names, emails, phones, organisation,
   signature details and any promise or request into the file. This one read also decides the
   kind.
4. Classify: bulk mail (unsubscribe footer, `no-reply` sender, list headers) becomes
   `contact_kind: newsletter`, `newsletter: true`, `newsletter_read_detail: subject`; machine
   senders (receipts, alerts) become `system`.
5. Record the receiving persona from the address the message was sent to.
6. Leave `preferred_reply_persona: null` unless the owner has said; never infer it from the
   message content alone.

### 3. Newsletter handling

1. Resolve the contact from the sender before reading deeply.
2. Load only what `newsletter_read_detail` allows: `subject` (default), `body`, or
   `body_and_images`. Images only at `body_and_images` or when the owner asks.
3. Do not draft a reply unless the owner asks; do not invent a reply persona.
4. Add each new receiving persona to `receiving_personas`.

### 4. Preparing a reply, appointment or contact-linked task

1. Resolve the contact from its identifiers.
2. Load `preferred_reply_persona`; when it is `null` (and the party is not a newsletter), ask
   which capacity to use, with a suggested answer.
3. Load the persona file and its bound account. With
   `google-workspace-access`, `google_crm_resolve.py` does steps 1 to 3 and reports when a
   confirmation is needed.
4. When more than one persona or account is plausible, confirm the target for this operation
   (CONTRACT §10.5).
5. Draft in the persona's voice. Email stays draft-first: nothing is sent until the owner
   approves that specific draft.

### 5. Merging an external directory (Google Contacts or similar)

1. Match each directory person to contacts by email, then phone, then name.
2. Merge identifiers (emails, phones, organisations, resource names in `google_contact_refs`) into the
   match; create a contact for each unmatched person.
3. Never overwrite overview, relationship, reply guidance, notes or open loops from directory
   data alone; the directory is not the relationship memory.
4. For Google Contacts, `google_contacts.py sync-to-crm` and `sync-all-to-crm` in
   `/shared/skills/google-workspace-access/` implement this merge.

### 6. Optional hook – tax registration on invoices

When the CRM node's `RULES.md` enables it: whenever an invoice is processed for a contact or an
organisation, check the party's tax registration with the authoritative register for that
jurisdiction, and update the contact when an identifier or status is missing or has changed.

- Australia: `/shared/skills/abr-access/` looks up the Australian Business Number and GST
  registration (for example for "Example Plumbing Pty Ltd").
- Elsewhere: the equivalent public register, through its own skill; with no skill available,
  record the check as an open loop on the contact rather than inventing a status.

### 7. Keeping the register healthy

Run `crm_check.py validate` after a batch of changes and `crm_check.py duplicates` after a
directory sync or bulk creation. Merge confirmed duplicates by hand: keep the older file, fold
the other's identifiers and dated notes into it, and leave the removed id in a note.

## Scripts or commands

| Command | Role |
|---|---|
| `python shared/skills/crm/scripts/crm_check.py find --email ada@example.com` | Contacts holding that email (also `--name`, `--handle`, `--phone`) |
| `python shared/skills/crm/scripts/crm_check.py validate` | Front matter, kinds, newsletter invariants, persona references |
| `python shared/skills/crm/scripts/crm_check.py duplicates` | Contacts sharing an email or phone, or with the same normalised name |

All three are read-only and standard-library only. `--node <path>` selects the node (a
repository-root path such as `/memory/projects/contacts`, or an absolute path); without it the
script uses `crm_root` from `/memory/skills/google-workspace-access/config/crm.json`, then
`/memory/projects/contacts`. `--json` prints machine-readable output. Exit code 1 means errors
were found (validate) or duplicates exist (duplicates).

Tests: `python -m unittest discover -s shared/skills/crm/scripts/tests -v`.

## Templates

| Template | Copied to |
|---|---|
| `templates/contact.template.md` | `<crm-node>/contacts/_TEMPLATE.md` |
| `templates/persona.template.md` | `<crm-node>/personas/_TEMPLATE.md` |
| `templates/node-README.template.md` | `<crm-node>/README.md` |
| `templates/node-RULES.template.md` | `<crm-node>/RULES.md` (the node's operating rules) |

The memory skeleton's starter node `/shared/templates/memory-skeleton/projects/contacts/` holds
the same bodies; a test keeps them in step.

## Outputs

- Contact and persona files in the CRM node.
- Checker reports on stdout; nothing is written by the script.

## Permissions

- Writes only inside the owner's CRM node.
- No secrets, OAuth tokens, passwords or recovery material in any CRM file; bank and tax file
  numbers are secrets for this purpose.
- External directories and mail are read through their own skills and under their permissions.

## Failure behaviour

- Ambiguous identity (several matches, or a name without an identifier): stop and ask with the
  candidates listed.
- Missing persona or account for a reply: ask; never invent a persona, an address or an account.
- CRM node missing: say so and offer to create it from the skeleton starter node.
- Checker errors: fix the records in the same session, or report the ones that need the owner.

## Logging behaviour

Contact notes carry their own dated history. Structural decisions (a new persona, a changed
rule, a bulk import or merge) get one entry in the CRM node's `LOG.md`.

## State, knowledge and task update behaviour

- `STATE.md` of the CRM node: counts and open work only when they change materially (a bulk
  import, a new persona).
- `KNOWLEDGE.md`: persona catalogue and durable principles.
- Promises and waiting items found on a contact become tasks under `/memory/tasks/` and are
  linked from the contact's open loops.
