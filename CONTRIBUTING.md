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
3. `pytest tests/ -q` must pass.
4. Open a PR against `main`. Direct pushes to `main` are blocked, and every PR
   needs the code owner's approval before merge. Do not bump the version by
   hand: release-please derives it from commit types and opens a release PR.

## Commit style and releases

Conventional commits, because release-please reads them to version the plugin:

- `fix:` -> patch, `feat:` -> minor, `feat!:` or a `BREAKING CHANGE:` footer -> major.
- `docs:`, `chore:`, `ci:`, `test:`, `refactor:` do not trigger a release.

Subject ≤ 72 chars; body explains why, not what.

PRs are squash-merged and the **PR title** becomes the commit on `main`, so the
PR title must be a valid conventional commit. A CI check (`pr-title`) enforces
this. On merge, release-please opens or updates a release PR; merging that PR
bumps `.claude-plugin/plugin.json`, updates the changelog, tags the version and
cuts a GitHub Release.

## What fits this plugin

Frugal routes work to the cheapest capable model. Changes should reduce cost,
improve routing decisions, or improve measurement. New agents need a row in
the routing decision table (`skills/routing/SKILL.md`) and a case in the
escalation protocol. Anything that adds a hard dependency beyond Python 3.10
stdlib + bash needs a very good reason.
