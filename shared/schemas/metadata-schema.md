---
id: schema-metadata
title: Markdown Metadata Schema
type: schema
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-04T03:31:56+10:00
updated: 2026-09-23T12:00:00+10:00
---

# Markdown Metadata Schema

## Required

```yaml
id: unique-stable-id
title: Human-readable title
type: document-type
schema_version: 0.2
contract: /CONTRACT.md
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
```

Use second precision with an explicit timezone designator. `Z` is valid for UTC. Keep `created` immutable and advance `updated` for each substantive change.

## Common optional fields

```yaml
status: active
owner: brain-owner
parent: /memory/projects/example
node_type: project
tags: []
project_refs: []
knowledge_refs: []
skill_refs: []
source_refs: []
```

Add a field only when it improves retrieval, routing, responsibility, automation or traceability.

