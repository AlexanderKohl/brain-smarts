---
id: template-owner-skills-readme
title: Owner Skill Configuration
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
owner: OWNER_SHORT_NAME
---

# Owner Skill Configuration

Read `/CONTRACT.md` first.

Owner configuration, data and notes for shared skills (CONTRACT §3.5). A folder here is named
exactly like the skill in `/shared/skills/` and mirrors its inner layout (`config/`, `data/`,
`knowledge/`). The skill itself, and generic knowledge about the external system it reaches,
stay canonical in `/shared/skills/`. Never store a secret here.

#### Folders

Listed alphabetically. Add one per skill that needs owner configuration, and summarise it here.

##### `owner-board/`

Contains `config/boards.json`, the owner-board registry (`/shared/skills/owner-board/SKILL.md`,
section "Configuration"). It ships with no project boards, so the personal task board and the
directory at `/memory/boards/` are generated from the first task. Harmless when the
`owner-board` skill is not in `active_skills`.
