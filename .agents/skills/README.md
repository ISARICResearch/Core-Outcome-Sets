# Agent skills in this repo

Each skill is a directory with a `SKILL.md`:

```text
<skill-name>/
├── SKILL.md
├── scripts/     (optional)
└── references/  (optional)
```

`SKILL.md` starts with YAML front-matter `name` and `description`, example for `email-send` skill:
```
---
name: email-send
description: >-
  Email newsletters
---
```

`./setup.sh` symlinks every skill into `~/.agents/skills/` so it's gonna be accessible outside of this repo. To optional out for a single run, prefix with `SYNC_SKILLS=0`:

```bash
SYNC_SKILLS=0 ./setup.sh
```
