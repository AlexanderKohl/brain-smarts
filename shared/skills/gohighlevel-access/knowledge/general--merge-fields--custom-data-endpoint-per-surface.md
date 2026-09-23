---
id: ghl-general-merge-fields-custom-data-endpoint-per-surface
title: HighLevel publishes the merge-field picker vocabulary per surface at /custom-data/{surface}
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: merge_field
endpoint: GET /custom-data/{surface}
status: confirmed
superseded_by: null
refuted_by: null
discovered: 2026-09-12
verified: 2026-09-12
source_refs:
  - /memory/skills/gohighlevel-access/knowledge/general--merge-fields--custom-data-endpoint-per-surface.md
created: 2026-09-12T16:40:00+10:00
updated: 2026-09-23T12:00:00+10:00
---

# The merge-field picker has an endpoint, one per surface

## Behaviour

```text
GET /custom-data/{surface}?locationId={loc}&types=custom-values,custom-fields
200 {
  "for": "emails",
  "static":        [ {"label": "Account", "value": "__account__", "children": [
                       {"label": "Name", "value": "{{location.name}}"}, ... ]}, ... ],
  "custom-values": [ ... ],
  "custom-fields": [ ... ],
  "trigger-links": [ ... ],
  "traceId": "..."
}
```

Every leaf is `{label, value}` where `value` is the literal token to insert. `static` is
always present and holds HighLevel's built-in vocabulary for that surface; the other
sections are selected by `types` and are built from the location's own configuration.

`types` is accepted in two spellings, and which one is sent varies by caller:
`types=custom-values,custom-fields` and `types[]=custom-values&types[]=custom-fields`.

Surfaces observed: `emails`, `conversations`, `estimates`, `invoices`, `orders`,
`abandoned-cart`, `social-media`, `funnels` on `backend.leadconnectorhq.com`;
`emails`, `conversations`, `proposals`, `trigger-links` on
`services.leadconnectorhq.com`.

`funnels` is called by `page-builder.leadconnectorhq.com` when a page opens in the
builder. Courses and membership offers have **no surface of their own**: the course
creator studio and the offers list both call the `services` host's `emails` surface.

The two hosts are not mirrors. `services` returns the richer document for `conversations` –
it is the host that carries `custom-fields` and `trigger-links` for that surface, where
`backend` returns only `static` and `custom-values`.

Responses are large: 30 KB for `emails`, 110-142 KB for `invoices`, `proposals`,
`trigger-links` and the `services` `conversations`.

## Why it's non-obvious

The picker looks like a client-side widget assembled from the field and custom-value lists,
because those lists are fetched on the same pages. They are not the same thing: the picker
document carries surface-specific built-in vocabulary that appears in no field list –
`{{order.*}}`, `{{receipt.*}}`, `{{membership_contact.*}}`, `{{invoice.*}}`,
`{{right_now.*}}` – and it carries the exact token, which the field list does not.

Nothing in the URL says "merge fields" or "variables".

## Consequence

"Which variables can be used here" is answerable by a single call per surface against the
live account, rather than by enumerating editors. A surface HighLevel adds later answers for
itself. This is the capture surface for the vocabulary half of impact analysis; the usage
half still has to come from each surface's own stored configuration.

Namespaces visible through it that a contact/opportunity-centric model will not expect:
`object`, `order`, `receipt`, `membership_contact`, `right_now`, `estimate`, `document`,
`campaign`. `object.*` is how a custom object field is addressed in a token.

## Evidence

Observed against `Example Co` (`loc_EXAMPLE_01`) on 2026-09-12 during a walk of every
menu-accessible page, captured by a browser extension's traffic
recorder. Ten distinct surface responses; the full vocabulary is extracted to
an owner project data file (memory layer).

## Applies to

Confirmed for the twelve surface/host pairs listed. Three surfaces are known **not** to
use this mechanism, each for its own reason, and all three were checked by opening the
editor:

- **Workflows** – the builder composes its own picker and issues no `/custom-data/` call.
- **Quizzes, and the form and survey builders** – structured field inputs only. They call
  `locations/{loc}/customFields/search`, `locations/{loc}/customValues` and `objects`, and
  no merge-field vocabulary endpoint.
- **Dashboards and custom reports** – neither `/custom-data/` nor `customFields/search`.
  The dashboard calls `reporting/dashboards/widgets-definitions` and
  `reporting/custom-metrics`. Whatever backs the newer custom-value substitution in
  dashboard titles, text boxes and embed URLs was not identified; treat it as unknown
  rather than absent.

Ad manager remains unvisited.
