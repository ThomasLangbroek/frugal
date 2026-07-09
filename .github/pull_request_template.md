## What

<!-- one or two sentences -->

## Why

<!-- the problem this solves; link an issue if one exists -->

## Checks

- [ ] `pytest tests/ -q` passes locally
- [ ] version bumped in `.claude-plugin/plugin.json` if `hooks/`, `agents/`, `skills/` or `scripts/` changed
- [ ] hooks remain fail-open (no code path lets a hook break a session)
