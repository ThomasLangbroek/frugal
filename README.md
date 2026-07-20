# frugal

[![ci](https://github.com/ThomasLangbroek/frugal/actions/workflows/ci.yml/badge.svg)](https://github.com/ThomasLangbroek/frugal/actions/workflows/ci.yml)

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

to get cost per tier, escalation rate, and estimated savings versus running the same work on your session's actual main-loop model (recorded per run; older records without it are compared against the top tier). Prices live in `scripts/stats.py` (`PRICES`); update them when Anthropic pricing changes. Learning is deliberately offline: read the report, edit the decision table.

## Enforcement

Routing policy in a skill is advisory: the model follows it well, but a prompt cannot *forcibly* prevent anything. Frugal therefore enforces on three levels, the first two active out of the box:

1. **Policy injection.** A `SessionStart` hook puts the routing policy in context at every session start; a `UserPromptSubmit` hook re-pins a one-line reminder on every prompt. No drift, nothing to invoke manually.
2. **Inline-exploration budget.** A `PreToolUse` guard counts search-type tool calls (Read, Grep, Glob, search-y Bash) in the main loop. Past the budget (default 5 per prompt) further ones are denied with a pointer to the cheap workers. The budget resets on any delegation or new prompt; worker agents are never throttled. Non-search commands (git, test runners, builds) are never blocked.
3. **Expensive-tier guard (opt-in).** `hooks/guard_expensive.sh` blocks `sage` spawns entirely. Wire it as a `PreToolUse` hook with matcher `Agent` in your `settings.json` if you want a hard ceiling.

Judgement lives in prompts; enforcement lives in hooks.

## Knobs

| Knob | Default | Effect |
|---|---|---|
| `FRUGAL_INLINE_BUDGET` | `5` | Inline search ops allowed per prompt before the guard denies |
| `FRUGAL_ALLOW_INLINE=1` | unset | Disables the inline-exploration guard for the session |
| `FRUGAL_ALLOW_EXPENSIVE=1` | unset | Allows `sage` spawns past the opt-in expensive-tier guard |
| `FRUGAL_METRICS_PATH` | `~/.claude/frugal/metrics.jsonl` | Where worker-run metrics are written |
| `/frugal:models` | agent defaults | Per-project model overrides, e.g. `/frugal:models scout=sonnet` |
| `.claude/routing-overrides.md` | none | Per-project routing rules; read first, always win |

Too aggressive for your taste? `FRUGAL_ALLOW_INLINE=1` in your environment turns the hard guard off while keeping the advisory policy. Want it gone entirely? `/plugin uninstall frugal` — frugal keeps no state outside the metrics file.

## Configuration

- Defaults are the decision table in `skills/routing/SKILL.md`.
- Per-project overrides: create `.claude/routing-overrides.md` in your project. The skill reads it first and its rules win.
- Per-project model mapping: `/frugal:models` shows it, `/frugal:models scout=sonnet builder=opus` changes it, `/frugal:models reset` restores defaults. Overrides live in the project, not the plugin, and survive updates.
- No Fable access on your plan? `/frugal:models sage=opus`, or edit `agents/sage.md` frontmatter.
- Multi-provider: see [docs/litellm-recipe.md](docs/litellm-recipe.md).

## Statusline segment (optional)

Run once:

```
/frugal:setup-statusline
```

It adds a `frugal $0.03/$1.20 saved` badge (session/lifetime) to your statusline: it creates a minimal statusline if you have none, or merges the segment into your existing one (with your consent, smallest possible edit). A plugin cannot configure `statusLine` automatically - that field is user-owned - so this one-time command is as close as it gets.

Manual alternative: call `scripts/statusline.py` from your own statusline command, passing the session id from the statusline stdin JSON:

```bash
FRUGAL_TXT=$(python3 "$(ls -d ~/.claude/plugins/cache/*/frugal/*/scripts/statusline.py 2>/dev/null | head -1)" \
  ${SESSION_ID:+--session "$SESSION_ID"} 2>/dev/null)
```

It prints nothing when no metrics exist yet, so your statusline stays clean.

## Evaluating routing quality

Deliberately no synthetic eval harness: headless scenario evals proved flaky (other plugins' skills win trigger races, model nondeterminism) while measuring little. Evaluate with real usage instead: work normally for a few days, then run `/frugal:router-stats` and read delegation rate, tier mix, and escalation rate. High escalations on one agent means its table row routes too low; near-zero savings means work is not being delegated.

## Privacy

Metrics are agent names, model ids, token counts and an escalation flag — one local jsonl line per worker run, written to `~/.claude/frugal/metrics.jsonl`. No prompt content, no file paths from your projects, no telemetry, nothing leaves your machine. Delete the file at any time; the report simply starts over.

## For teams

Rollout is two commands per person (see Install) and no workflow change; routing is automatic. Work normally for a week, then review `/frugal:router-stats` together and tune the decision table or `FRUGAL_INLINE_BUDGET` if the guard fires too often or too rarely.

Be precise about the cost claim when you pitch it internally: in our measurements delegated work costs **~85% less** than the same work on the top-tier model — cents instead of dollars per task. That saving applies to the *delegated* portion of a session, not the whole bill. Design, debugging and review stay on the expensive model on purpose; what frugal removes is paying reasoning rates for grep. Every install measures itself locally, so nobody has to take this README's word for anything.

## Honest trade-offs

- **Advisory unless the guard hook is enabled.** The skill steers routing; only the hook enforces it.
- **Claude Code only.** The router leans on the harness (Agent tool, hooks, parallel delegation). Multi-provider is a documented recipe, not a tested code path.
- **Metrics are limited** to fields hook events and transcripts expose. Escalations are detected via a prompt marker, so escalations performed without the marker are not counted.

## Extending

Adding a model tier is one agent file plus one table row; see [docs/extending.md](docs/extending.md).

## Releases

Releases are automated with [release-please](https://github.com/googleapis/release-please). Merges to `main` accumulate into a release PR that bumps `.claude-plugin/plugin.json` and regenerates the changelog from conventional-commit history; merging that PR tags the version and publishes a GitHub Release. Contributors never touch the version by hand, and PR titles must be valid conventional commits (a `pr-title` CI check enforces it). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT.
