---
id: ghl-general-conversations-send-and-status-live-shapes
title: Conversations send accepts omitted destinations and status; message detail is nested
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: POST /conversations/messages; GET /conversations/messages/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-08-26
verified: 2026-08-26
source_refs: []
created: 2026-08-26T18:20:00+10:00
updated: 2026-09-23T14:40:00+10:00
---

# Conversations send and status live shapes

## Behaviour

A live Location-token probe successfully sent both SMS and Email with `Version: v3` and these
minimal shapes:

```json
{"type":"SMS","contactId":"<contact-id>","message":"<message>"}
```

```json
{"type":"Email","contactId":"<contact-id>","subject":"<subject>","html":"<html>"}
```

Both returned HTTP 201. `status` was omitted for both. `toNumber` was omitted for SMS and
`emailTo` was omitted for Email; HighLevel used the Contact's saved primary destination.

The SMS send response contained `conversationId`, `messageId` and `traceId`. The Email response
also contained `emailMessageId`, `msg` and `threadId`.

For the SMS message, `GET /conversations/messages/:id` returned HTTP 200 with the actual record
nested under `message`, not at the response top level:

```json
{"message":{"messageType":"TYPE_SMS","direction":"outbound","status":"delivered"},"traceId":"..."}
```

The Email send response's main `messageId` returned HTTP 400 from that general detail endpoint.
The Contact's conversation listing exposed an Email record ID that the general detail endpoint
did accept, but the resulting Email record had no `status`. Do not generalise SMS-style delivery
polling to Email from this endpoint.

## Why it's non-obvious

The published send DTO marks `status` as required and documents a 200 response, while the live
accepted calls omitted it and returned 201. The published message-detail example places fields
at the response top level, while the live response wraps them under `message`. Email also uses
multiple message identifiers with different endpoint behaviour.

## Evidence

Confirmed 2026-08-26 through one explicitly authorised SMS and one explicitly authorised Email
against Contact `id_EXAMPLE_01` in `Example Co (Staging)`
(`loc_EXAMPLE_01`, company `comp_EXAMPLE_01`). The Contact had both primary methods
present. No destination value, message body, OAuth material or broker state was stored in this
entry. A follow-up read of the Contact's recent conversation found both messages and confirmed
the SMS as `delivered`.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Confirmed for the built-in SMS and Email channels on `POST /conversations/messages`, and for an
SMS record on `GET /conversations/messages/:id`, using a Location OAuth token in the named
staging sub-account. Whether other sending providers, account configurations or message types
behave identically remains untested. Email delivery-status detection remains unsupported by this
finding.
