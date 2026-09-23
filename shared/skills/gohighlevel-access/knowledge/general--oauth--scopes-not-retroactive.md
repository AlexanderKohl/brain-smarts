---
id: ghl-general-oauth-scopes-not-retroactive
title: Adding a new OAuth scope does not retroactively grant it to already-installed locations
type: api_knowledge
schema_version: 0.2
contract: /CONTRACT.md
system: gohighlevel
object_type: general
field_type: null
endpoint: null
status: confirmed
superseded_by: null
refuted_by: null
discovered: '2026-08-20'
verified: '2026-08-20'
created: '2026-08-24T21:30:00+10:00'
updated: 2026-09-23T14:40:00+10:00
---

# OAuth scopes are not retroactive

## Behaviour

Adding a scope to the app's requested-scopes list only takes effect for a
**new** install or an explicit **reinstall/reauthorization**. HighLevel
does not retroactively grant a newly-added scope to a location that
installed before the change. A location still on the old scope set gets a
real, unhandled `GHL_UNAUTHORIZED`/403 the first time this app calls an
endpoint the new scope actually gates – not a graceful degrade or a clear
"scope missing" signal tied to the install event.

Concrete confirmed example: `pipelines.readonly` was added 2026-08-20 for
Opportunity Pipeline/Stage targeting (see
`opportunity--pipeline-stage--separate-scope-and-direct-write-keys.md`).
Every location installed before that date needs to reinstall before that
feature works for them – and the Marketplace app's own scope configuration
in HighLevel's dashboard has to be updated to request the new scope too, a
manual step outside application code.

## Why it's non-obvious

Deploying a code change that requests a new scope feels like it should
"just work" the next time the app runs, the way most config changes do –
the silent per-location gap (old installs keep the old grant until they
explicitly reauthorize) only surfaces as a runtime 403 much later, often
far from the deploy that added the scope.

## Evidence

Documented in the app's own maintained scope reference
(`GHL_SCOPES.md`), itself informed by the `pipelines.readonly` rollout.

Observed on a live account; the owner's record, with its real identifiers and sources, is kept in their memory.

## Applies to

Any OAuth scope addition, for any object or feature – this is a platform-
wide OAuth/install-lifecycle rule, not tied to one endpoint.
