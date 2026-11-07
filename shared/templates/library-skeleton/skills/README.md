---
id: template-library-skills-readme
title: Library Skills
type: node_readme
schema_version: 0.2
contract: /CONTRACT.md
node_type: skill_library
status: active
created: YYYY-MM-DDTHH:mm:ss+HH:MM
updated: YYYY-MM-DDTHH:mm:ss+HH:MM
---

# Library Skills

Read `/CONTRACT.md` first.

Optional skills: access to one outside system, or one way of working an owner may choose
(CONTRACT §3.4). An owner uses the skills listed in `active_skills` in `/memory/OWNER.md`. Each
skill directory contains a `SKILL.md` defining purpose, permissions, inputs, scripts, outputs,
failure handling and repository updates.

Like the mechanics, these skills hold instructions, scripts, tests and generic knowledge about
the systems they reach, and no personal data (`SMART-RULE-0008`). Owner configuration, data and
owner-specific notes live in `/memory/skills/<skill>/`. A script finds another skill, the vault
included, from the brain root – the nearest folder holding `CONTRACT.md` – never by a path
relative to its own folder (CONTRACT §3.5).

Plaintext credentials and recovery material must remain outside the repository; library skills
store secrets only through `/shared/skills/manage-credentials/`.

#### Folders

No skills yet. Folders are alphabetical; add one entry per skill folder as it is created or
installed, in this form:

```markdown
##### `<skill>/`

Contains <what the skill does and which outside system it reaches>. <What it needs: vault
entries, configuration in `/memory/skills/<skill>/`.>
```
