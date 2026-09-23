---
id: skill-crm-node-rules-template
title: Contacts Rules
type: rules
schema_version: 0.2
contract: /CONTRACT.md
scope: /memory/projects/contacts
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
skill_refs:
  - /shared/skills/crm
---

# Contacts Rules

Read `/CONTRACT.md` first. Procedures: `/shared/skills/crm/SKILL.md`.

These rules apply while `crm` is listed in `active_skills` in `/memory/OWNER.md`. While it is not,
agents leave this node alone. They are the owner's rules: a substantive change needs the owner's
acceptance (CONTRACT §13.2).

## Canonical home

- `contacts/` is the canonical register of the people, organisations, newsletter senders and
  systems the owner deals with; `personas/` holds the identities the owner communicates as.
  External directories supply identifiers only.

## Capture

- When the owner shares a durable fact about a person or organisation, create or update that
  contact in the same session, before relying on the fact. Do not leave it only in chat.
- Automatically create a contact for every newly observed remote party: a new sender address, a
  person or organisation mentioned with a durable identifier, or a directory person not yet in
  the register. Copy `contacts/_TEMPLATE.md`.
- One contact per real party. Search by every identifier first and merge into an existing match
  instead of creating a second file.
- On the first encounter of a new email party, read the full decoded message body, not the
  subject or preview alone, and record the identifiers and context it holds. After a contact is
  classified as a newsletter, honour its `newsletter_read_detail`.
- When merging from an external directory, merge identifiers and create missing contacts; never
  overwrite overview, relationship, reply guidance, notes or open loops from directory data alone.

## Personas and replies

- Before drafting a reply, resolve the contact, load its `preferred_reply_persona` and that
  persona's file, and confirm the sending account when more than one could apply (CONTRACT
  §10.5).
- Never invent a persona, a sending account, an email address or a contact identity. When the
  contact has no preferred persona, ask.
- Newsletters and systems keep `preferred_reply_persona: null` unless the owner sets one; their
  mail is read at subject level unless `newsletter_read_detail` says otherwise.
- Contacts reference a persona by `persona_key` only; the full definition lives in `personas/`.
- Email stays draft-first: nothing is sent until the owner approves that specific draft.

## Content

- Keep each contact brief: overview, identifiers, relationship, reply guidance, dated notes and
  open loops. Long background belongs in the owning project's knowledge, linked from the contact.
- Never store secrets, OAuth tokens, passwords, recovery material, bank account numbers or tax
  file numbers in this node.

## Optional: tax registration on invoices

Status: **disabled**. To enable, the owner accepts a change that sets this line to `enabled` and
names the register skill (for Australia, `/shared/skills/abr-access/`).

- When enabled: whenever an invoice is processed for a contact or organisation, check the party's
  tax registration with the named register. When an identifier or the registration status is
  missing or has changed, update the contact in the same session. When the register cannot be
  reached, record the check as an open loop on the contact instead of inventing a status.
