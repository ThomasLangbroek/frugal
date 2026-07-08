# frugal

A cost-optimised agent router for [Claude Code](https://code.claude.com). Frugal teaches the main loop to send every sub-task to the cheapest execution strategy that can succeed, and to escalate only on verified failure:

```
deterministic tool → haiku worker → sonnet worker → main model → fable (escalation ceiling)
```

The expensive reasoning model plans and judges; commodity work (locating files, extracting data, mechanical edits) runs on cheap tiers. No framework, no runtime, no API keys: frugal is a plugin made of a routing skill, five agent definitions, and two small hooks. The harness does the rest.

## Install

```
/plugin marketplace add ThomasLangbroek/frugal
/plugin install frugal@frugal-marketplace
```

## How it works

The main model already reads every request, so it acts as the router at zero marginal cost. The routing skill gives it one decision table:

| Task | Agent | Model |
|---|---|---|
| locate, grep, map structure, find usages | `scout` | Haiku |
| extract, classify, summarise one source | `extractor` | Haiku |
| mechanical edits from a complete spec | `mechanic` | Sonnet |
| implement one scoped task from an approved plan | `builder` | Sonnet |
| design, debugging, ambiguity, risk | main loop | whatever you run |
| beyond the main loop's tier, or isolated deep reviews | `sage` | Fable |

Plus a tool-first rule: if grep, jq, git, terraform or any deterministic command solves the task, no model is called at all.

### Escalation (verification first)

Workers do not self-grade their way up the ladder. Every worker ends with a fixed footer:

```
RESULT: <one line>
CHECKS-RUN: <commands run and outcomes, or "none">
UNCERTAINTIES: <or "none">
ESCALATE: yes|no - <reason>
```

The router then applies four rules:

1. If a deterministic check exists (tests, compiler, schema validation, `terraform validate`), run it. Pass = done. Fail = escalate one tier, maximum one retry, then the main loop takes over.
2. No check available: the main model spot-reads the result. It receives it anyway, so judging it costs almost nothing.
3. The worker's `ESCALATE: yes` is advisory input, never the sole trigger. Self-reported confidence from a cheap model is poorly calibrated; observable failure is not.
4. Never start at an expensive tier unless the decision table requires it. `sage` (Fable) is reached only via high-risk table rows or after escalation exhausts, one attempt, final.

## Metrics and the cost report

A `SubagentStop` hook logs one jsonl line per worker run (agent, model, token usage, escalation flag) to `~/.claude/frugal/metrics.jsonl`. Run:

```
/frugal:router-stats
```

to get cost per tier, escalation rate, and estimated savings versus running everything on the top-tier model. Prices live in `scripts/stats.py` (`PRICES`); update them when Anthropic pricing changes. Learning is deliberately offline: read the report, edit the decision table.

## Hard budget control (optional)

Routing policy in a skill is advisory: the model follows it well, but a prompt cannot *forcibly* prevent anything. If you need enforcement, wire the shipped guard as a PreToolUse hook in your `settings.json`. It blocks expensive-tier agent spawns unless `FRUGAL_ALLOW_EXPENSIVE=1` is set:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "bash ~/.claude/plugins/cache/frugal-marketplace/frugal/*/hooks/guard_expensive.sh"
          }
        ]
      }
    ]
  }
}
```

Judgement lives in prompts; enforcement lives in hooks.

## Configuration

- Defaults are the decision table in `skills/routing/SKILL.md`.
- Per-project overrides: create `.claude/routing-overrides.md` in your project. The skill reads it first and its rules win.
- No Fable access on your plan? Edit `agents/sage.md` frontmatter to `model: opus` for an Opus ceiling.
- Multi-provider: see [docs/litellm-recipe.md](docs/litellm-recipe.md).

## Statusline segment (optional)

`scripts/statusline.py` prints a compact `frugal $0.03/$1.20 saved` segment (session/lifetime) and prints nothing when there are no metrics yet. Call it from your existing statusline command, passing the session id from the statusline stdin JSON:

```bash
FRUGAL_TXT=$(python3 "$(ls -d ~/.claude/plugins/cache/frugal-marketplace/frugal/*/scripts/statusline.py 2>/dev/null | head -1)" \
  ${SESSION_ID:+--session "$SESSION_ID"} 2>/dev/null)
```

Append `$FRUGAL_TXT` to your statusline output. No statusline yet? Ask Claude Code to set one up with this segment included.

## Evaluating routing quality

Deliberately no synthetic eval harness: headless scenario evals proved flaky (other plugins' skills win trigger races, model nondeterminism) while measuring little. Evaluate with real usage instead: work normally for a few days, then run `/frugal:router-stats` and read delegation rate, tier mix, and escalation rate. High escalations on one agent means its table row routes too low; near-zero savings means work is not being delegated.

## Honest trade-offs

- **Advisory unless the guard hook is enabled.** The skill steers routing; only the hook enforces it.
- **Claude Code only.** The router leans on the harness (Agent tool, hooks, parallel delegation). Multi-provider is a documented recipe, not a tested code path.
- **Metrics are limited** to fields hook events and transcripts expose. Escalations are detected via a prompt marker, so escalations performed without the marker are not counted.

## Extending

Adding a model tier is one agent file plus one table row; see [docs/extending.md](docs/extending.md).

## Licence

MIT.
