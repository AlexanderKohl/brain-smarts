---
id: gohighlevel-access-data
title: GoHighLevel Access Skill Data
type: guide
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: 2026-08-08T14:45:00+10:00
updated: 2026-09-23T12:00:00+10:00
owner: brain-owner
---

# GoHighLevel access skill data

This folder holds no owner data. The owner's own reference data for this skill lives in the
memory layer at `/memory/skills/gohighlevel-access/data/`:

- `opportunity-stage-mappings.json` – known source→target pipeline/stage name mappings used by
  `ghl_review_pipeline_migrations.py` (its default `--mappings-file`, found through brain-root
  discovery). Names must match live pipeline/stage labels in the target sub-account.

Shape of one mapping (fictional example):

```json
[
  {
    "source_pipeline": "1. Enquiry",
    "source_stage": "New enquiry",
    "target_pipeline": "1. Enquiry to Sale",
    "target_stage": "New Lead"
  }
]
```
