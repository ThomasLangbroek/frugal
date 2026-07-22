# Changelog

## [0.13.0](https://github.com/ThomasLangbroek/frugal/compare/v0.12.0...v0.13.0) (2026-07-22)


### Features

* format the router report as a bill ([#20](https://github.com/ThomasLangbroek/frugal/issues/20)) ([a0bc930](https://github.com/ThomasLangbroek/frugal/commit/a0bc9308cdce94950ae5563593cd7c19264249b7))

## [0.12.0](https://github.com/ThomasLangbroek/frugal/compare/v0.11.1...v0.12.0) (2026-07-22)


### Features

* gate sensitive data before tier selection ([#18](https://github.com/ThomasLangbroek/frugal/issues/18)) ([1982c6c](https://github.com/ThomasLangbroek/frugal/commit/1982c6ca09c12184a42009b583f9a94c5e45c297)), closes [#17](https://github.com/ThomasLangbroek/frugal/issues/17)

## 0.11.1 - 20-07-2026
- guard_inline resets the inline-search budget only on foreground (blocking) agent dispatches; background dispatches (the default) keep the counter climbing, so inline discovery racing a background worker is still throttled instead of getting a fresh budget.

## 0.10.0 - 13-07-2026
- Per-session savings table in the stats report: one row per `session_id`, newest first, using the same net-vs-baseline definition as the totals so rows reconcile. Sessions that ran opus-on-opus show negative savings (the true delta, no cheaper tier to route to).

## 0.9.0 - 10-07-2026
- Honest savings: net cost includes the worker reply re-ingested at main-loop rates (`handoff_output_tokens`, final response only); statusline and report both use it.
- Per-run `duration_ms` from transcript timestamps; average duration per agent in the report.
- Metrics-to-routing feedback: `stats.py --advice` flags miscalibrated routes (escalation >30%, net >= baseline, fat handoffs) at SessionStart; silent when healthy.
- Reply caps on mechanic (150 words), builder (250), sage (500, overflow to scratch file); code never echoed back.
- Context-handoff routing rule: pass pointers, not pasted content.
- guard_inline fixes: write-redirected commands (`cat >> f`) no longer counted; shell prefixes (`cd x && grep`) no longer dodge the counter.

## 0.8.0 - 09-07-2026
- Savings baseline follows the session's main-loop model instead of always the top tier.

## 0.7.2 - 09-07-2026
- Dependency bumps (GitHub Actions checkout, setup-python).

## 0.7.1 - 09-07-2026
- Pricing verification date refresh; first change through the gated PR flow.

## 0.7.0 - 08-07-2026
- `/frugal:models`: per-project model overrides via `.claude/routing-overrides.md`.

## 0.6.0 - 08-07-2026
- Token-lean worker output: scout/extractor compress replies, builder ships the shortest working diff.
- Metrics ignore typeless subagent stops (internal machinery, not routed work).

## 0.5.1 - 08-07-2026
- Metrics measured the main session instead of the subagent; usage snapshots double-counted; escalation false positives from the policy text. All fixed; old metrics invalidated.

## 0.5.0 - 08-07-2026
- Inline-exploration budget guard (PreToolUse): denies search-type calls past `FRUGAL_INLINE_BUDGET` per prompt, pointing at the cheap workers.
- Bright-line rule in the routing policy: third search/list/read operation on one question means delegate.

## 0.4.0 - 08-07-2026
- Enforcement hooks: SessionStart injects the routing policy, UserPromptSubmit re-pins it each prompt. Routing no longer depends on manually invoking the skill.

## 0.3.0 and earlier - 07-2026
- Routing skill and decision table, five worker agents, escalation protocol.
- Metrics hook, cost report (`/frugal:router-stats`), statusline savings segment, optional expensive-tier guard.
