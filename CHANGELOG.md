# Changelog

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
