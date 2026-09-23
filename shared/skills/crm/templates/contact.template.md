---
id: skill-crm-contact-template
title: FULL NAME OR ORGANISATION
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

# FULL NAME OR ORGANISATION

Copy this file to `contact-<slug>.md`, set `id` to `contact-<slug>`, and replace every
upper-case placeholder. `contact_kind` is `person`, `organisation`, `newsletter` or `system`
(`/shared/skills/crm/SKILL.md`). Delete this paragraph.

## Overview

One short paragraph: who this is and why they matter to the owner.

## Identifiers

- Emails:
- Phones:
- Organisations:
- Social accounts (platform → handle or URL):
- Google Contacts (account alias → resource name):

## Relationship

How the owner knows this person or organisation, and the current context.

## Reply guidance

- Preferred persona: (`persona_key`, or `null` to ask)
- Receiving personas (the owner identities they write to):
- Tone / do:
- Don't:

## Newsletter handling (when `contact_kind: newsletter` or `newsletter: true`)

- `newsletter_read_detail`: `subject` (default) | `body` | `body_and_images`
- Agents load only what the flag allows; images only at `body_and_images` or on request.
- No reply persona is invented; `preferred_reply_persona` stays `null`.

## Notes

- YYYY-MM-DD: fact the owner shared, or what a message revealed.

## Open loops

- None.
