---
id: ghl-opportunity-pipeline-stage-scope
title: Pipeline/Stage need their own pipelines.readonly scope and are set via trusted direct-write keys
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: opportunity
field_type: null
endpoint: GET /opportunities/pipelines, PUT /opportunities/:id
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-20'
verified: '2026-08-20'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T18:00:00+10:00
---

# Opportunity Pipeline/Stage: distinct scope, direct-write keys

## Behaviour

`GET /opportunities/pipelines` requires its **own** scope,
`pipelines.readonly` – distinct from `opportunities.readonly` despite
living under the same `/opportunities/*` path. It returns every pipeline
for the location with stages **nested inline**
(`{ pipelines: [{ id, name, stages: [{ id, name }] }] }`) – there is no
separate per-stage endpoint. A stage belongs to exactly one pipeline, so
resolving a chosen stage yields both `pipelineId` and `pipelineStageId`
with no separate pipeline input needed. Both are written directly as
`PUT /opportunities/:id` body keys – trusted as stable, well-documented
keys without a live-catalog lookup, since the live catalog's own key
spelling for these fields isn't guaranteed to match.

Scope non-retroactivity applies here concretely: adding `pipelines.readonly`
after locations were already installed does **not** retroactively grant it
to those locations – see `general--oauth--scopes-not-retroactive.md`. A
location installed before the scope was requested gets an unhandled
`GHL_UNAUTHORIZED`/403 the first time this feature actually calls the
gated endpoint, not a graceful degrade; it needs a reinstall/reauthorization
(and the Marketplace app's own scope configuration needs updating first).

## Why it's non-obvious

The path (`/opportunities/pipelines`) strongly suggests it falls under the
general `opportunities.*` scope family; it doesn't. And a scope added after
go-live silently does nothing for existing installs rather than erroring
at request time until the feature is actually exercised.

## Evidence

Documented in a maintained API/scope reference (last verified
2026-08-15), itself built from confirmed live behaviour (2026-08-20).

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Opportunity only (Pipeline/Stage is an Opportunity-specific concept). The
scope-non-retroactivity fact is general – see the `general--oauth--*`
entry for the reusable rule.
