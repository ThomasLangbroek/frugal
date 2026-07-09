# Contributing

## Setup

```sh
git clone git@github.com:ThomasLangbroek/frugal.git
cd frugal
pip install pytest
pytest tests/ -q
```

No other dependencies. Everything is stdlib Python and bash.

## Making a change

1. Branch from `main`.
2. Make the change. Every non-trivial behaviour needs a test in `tests/`;
   hooks must stay fail-open (a broken hook must never break a session).
3. If you touch anything under `hooks/`, `agents/`, `skills/` or `scripts/`,
   bump the version in `.claude-plugin/plugin.json` (CI enforces this).
4. `pytest tests/ -q` must pass.
5. Open a PR against `main`. Direct pushes to `main` are blocked; CI must be
   green before merge.

## Commit style

Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `test:`.
Subject ≤ 72 chars; body explains why, not what.

## What fits this plugin

Frugal routes work to the cheapest capable model. Changes should reduce cost,
improve routing decisions, or improve measurement. New agents need a row in
the routing decision table (`skills/routing/SKILL.md`) and a case in the
escalation protocol. Anything that adds a hard dependency beyond Python 3.10
stdlib + bash needs a very good reason.
