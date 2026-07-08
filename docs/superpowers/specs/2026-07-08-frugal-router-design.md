# frugal - Cost-Optimised Agent Router for Claude Code

**Date:** 08-07-2026
**Status:** Approved design, pre-implementation
**Shape:** Claude Code plugin (skill + agents + hooks). Not a standalone framework.

## Problem

Expensive reasoning models spend most of their tokens on commodity work:
locating files, extracting data, applying mechanical edits. Frugal teaches the
main loop to route every sub-task to the cheapest execution strategy that can
succeed, and to escalate only on verified failure.

## Design decisions (resolved)

| Question | Decision |
|---|---|
| Shape | Claude Code plugin. A skill is instructions, not a runtime; the harness (Agent tool, hooks, Bash) already provides execution, parallelism, and enforcement. A standalone router would compete with LiteLLM Router, RouteLLM, Not Diamond with no differentiation. |
| Providers | Anthropic tiers only in v1 (Haiku / Sonnet / main model). Multi-provider is a documented LiteLLM-proxy recipe, not a code path. |
| Escalation trigger | Verification-first. Deterministic checks decide where possible; main-model spot-read otherwise. Worker self-reported confidence is advisory only (self-reported confidence is poorly calibrated). |
| Learning | Metrics jsonl + offline report (`/router-stats`). Human reads report, edits routing table. No online adaptation in v1. |
| Audience | General developers. |
| Classifier | The main model. It reads every request anyway, so classification cost is sunk. This dissolves the cheap-vs-expensive classifier paradox that standalone routers face. |

## Priorities (in order)

1. Correctness
2. Cost efficiency
3. Latency
4. Extensibility
5. Simplicity of use (and of implementation: fewest moving parts that satisfy 1-4)

## Architecture

```
frugal/
├── .claude-plugin/plugin.json      # marketplace manifest
├── skills/
│   ├── routing/SKILL.md            # the router: policy, decision table, escalation protocol
│   └── router-stats/SKILL.md       # /router-stats: cost report from metrics log
├── agents/
│   ├── scout.md      # haiku  - locate, grep, map, "where is X" (read-only)
│   ├── extractor.md  # haiku  - extraction, classification, single-doc summarisation
│   ├── mechanic.md   # sonnet - mechanical edits from a full spec, renames, boilerplate
│   ├── builder.md    # sonnet - scoped implementation from an approved plan
│   └── sage.md       # fable  - deep reasoning: architecture, debugging, security analysis
├── hooks/
│   ├── hooks.json
│   └── log_metrics.py              # SubagentStop -> append metrics jsonl
├── scripts/
│   └── stats.py                    # report generator + static price table
├── evals/                          # routing scenarios: prompt -> expected route
├── tests/                          # pytest for scripts and hooks
└── docs/                           # README, extending.md, litellm-recipe.md
```

The main model is the planner. It delegates downward and takes over when
escalation exhausts below its own tier. `sage` (Fable) is the escalation
ceiling above the main loop: used when the main-loop model is a cheaper tier
(e.g. Sonnet main loop) and a task needs top-tier reasoning, or when a
Fable-level task benefits from an isolated fresh context (parallel deep
reviews, final synthesis over merged summaries). If the main loop already
runs Fable, `sage` adds capability nothing - the skill says so and restricts
it to context-isolation use. `sage` is never a routing default; it is
reached only via the decision table's high-risk rows or escalation rule 1.

### Component mapping (vision -> plugin)

| Vision component | Plugin realisation |
|---|---|
| Routing engine | Decision table in `skills/routing/SKILL.md` |
| Provider abstraction | Agent `model:` frontmatter; LiteLLM proxy recipe for non-Anthropic |
| Worker framework | Claude Code Agent tool + `agents/*.md` |
| Planner | Main model guided by the skill's decomposition rules |
| Confidence evaluator / escalation engine | Worker output contract + verification-first protocol (below) |
| Deterministic tool executor | Tool-first policy section in SKILL.md; harness Bash |
| Cost estimator | Static price table in `scripts/`; actuals from token logs |
| Metrics collector | SubagentStop hook -> jsonl |
| Configuration | Defaults in SKILL.md; optional per-project override file |
| Logging | Metrics jsonl + harness transcripts |

## Capability routing

The router never routes on model names. Each agent's `description`
frontmatter advertises capabilities (`locate`, `extract`, `classify`,
`mechanical-edit`, `implement-from-plan`, ...). SKILL.md holds one decision
table:

    task signals -> required capabilities -> cheapest agent advertising them

Adding a model tier = new agent file + one table row. No logic changes.

Routing inputs per task: required reasoning level, context size, risk,
latency tolerance, and whether a deterministic tool solves it outright.

### Tool-first rule

Before any delegation: if grep/jq/sed/git/terraform/kubectl or any
deterministic command solves the task, run it. No LLM call. Reasoning models
are for reasoning.

### Never delegate

Security-sensitive changes, destructive operations, ambiguous requirements,
anything needing user judgement. These stay in the main loop.

## Escalation protocol (verification-first)

Every worker ends its output with a fixed footer:

```
RESULT: <one-line outcome>
CHECKS-RUN: <commands run and results, or "none">
UNCERTAINTIES: <what the worker is unsure about, or "none">
ESCALATE: yes|no - <reason>
```

Router rules:

1. A deterministic check exists (tests, compile, schema validation, diff
   applies, `terraform validate`) -> run it. Pass = done. Fail = escalate one
   tier, maximum one retry, then the main loop takes the task itself. If the
   task then still exceeds the main loop's own tier, hand to `sage` (one
   attempt, final).
2. No deterministic check -> the main model spot-reads the result (it
   receives it anyway; marginal cost near zero).
3. Worker `ESCALATE: yes` is advisory input to 1-2, never the sole trigger.
4. Never start at an expensive tier unless the decision table requires it.

## Enforcement split

Judgement lives in prompts; enforcement lives in hooks. The model can drift
from prompt policy; hooks cannot be ignored. An optional PreToolUse hook
blocks agent spawns that violate policy (e.g. expensive-tier agents without
an explicit flag). Ships disabled by default; documented as the hard budget
control.

## Configuration

- Defaults: the decision table inside `skills/routing/SKILL.md`.
- Overrides: optional `.claude/routing-overrides.md` in the user's project;
  the skill reads it if present and it wins over defaults.
- No YAML config engine in v1. Add only if real users need machine-edited
  config.

## Metrics and learning

`SubagentStop` hook appends one jsonl line per worker run to
`~/.claude/frugal/metrics.jsonl`: timestamp, agent type, model, token usage,
duration, escalated flag, task-type label. `/router-stats` renders cost per
tier, escalation rate, and estimated savings versus an all-main-model
baseline using the static price table.

Learning in v1 is offline: read the report, edit the decision table.
Adaptive table regeneration is explicitly deferred (tiny per-task-type sample
sizes; silent policy drift is hard to debug).

## Parallelism

The harness already runs independent Agent calls concurrently. The skill's
decomposition rules instruct the main model to batch independent delegations
in one message (e.g. 50-module review: fan out scouts/extractors, merge
summaries, one final reasoning pass in the main loop).

## Testing

- `pytest` for `log_metrics.py` and `stats.py` (real code, real tests).
- `evals/`: scenario files (prompt + expected routing decision). Runner
  executes each via `claude -p`, asserts the chosen agent from the
  transcript. On-demand, not default CI (costs money).

## Accepted trade-offs

- Routing is advisory unless the blocking hook is enabled. Documented
  honestly in the README.
- Claude Code only. Multi-provider is a recipe, not a tested code path.
- Metrics limited to fields hook events expose.
- Fable access varies by plan/deployment. README documents editing `sage.md`
  frontmatter to `opus` as the fallback ceiling.

## Build phases

1. **Core:** routing skill + 5 agents + escalation contract. Usable
   immediately after this phase.
2. **Metrics:** SubagentStop hook + `/router-stats` + price table.
3. **Polish:** evals, docs (README, extending guide, LiteLLM recipe),
   marketplace packaging.

Each phase: design confirmation, implementation, review before the next.
