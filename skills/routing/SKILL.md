---
name: routing
description: Cost-optimised task routing. Use at the start of any coding, search, extraction, review, or multi-step task to pick the cheapest execution strategy (deterministic tool, haiku worker, sonnet worker, main model, fable worker) and to handle escalation when a worker fails. Also triggers on mentions of cost, budget, routing, or delegation.
---

# Frugal routing

Route every sub-task to the cheapest strategy that can succeed. Priorities, in order: correctness, cost, latency, extensibility, simplicity.

## Step 0: overrides

If `.claude/routing-overrides.md` exists in the project, read it first. Its rules win over everything below.

## Step 1: tool first

Before any delegation: if a deterministic command solves the task (grep, rg, jq, yq, sed, awk, git, terraform, kubectl, helm, docker, a compiler, a test runner), run it. No LLM call. Reasoning models are for reasoning.

Step 1 covers **one-shot** commands only: you know the exact command and its output answers the question directly. The moment discovery turns iterative — a second search informed by the first, listing directories to decide what to read next, reading files to summarise them — it is no longer a tool call, it is a locate/extract task. Bright line: the third search/list/read operation on the same question means you are exploring inline; stop and hand the whole question to `scout` or `extractor`, including what you already learned. Every raw tool result you ingest is paid at main-loop rates; a haiku worker reads the same bytes at a fraction of the cost and returns a summary.

## Step 2: decision table

Decompose the request into sub-tasks. For each, match signals to the cheapest capable agent:

| Task signals | Required capabilities | Route |
|---|---|---|
| "where is X", "what uses Y", map directory, grep logs | locate | `scout` (haiku) |
| pull fields from docs/logs, classify against given categories, summarise one file or diff, format conversion | extract | `extractor` (haiku) |
| rename, boilerplate, apply known pattern, config value change, test scaffold from example, with a complete spec | mechanical-edit | `mechanic` (sonnet) |
| implement one scoped task from an approved plan, write tests from given cases, fix a simple reproduced bug | implement-from-plan | `builder` (sonnet) |
| design, debugging, ambiguous requirements, reviews, trade-offs, anything regulated or risky | reasoning | main loop (you) |
| task exceeds the main loop's own tier, or Fable-level work needs an isolated fresh context (parallel deep reviews, synthesis over merged summaries) | deep-reasoning | `sage` (fable) |

`sage` is never a routing default. If the main loop already runs Fable, use `sage` only for context isolation, not capability.

## Never delegate

Security-sensitive changes, destructive operations, ambiguous requirements, anything needing user judgement. These stay in the main loop, always.

## Delegation rules

- Delegate only self-contained sub-tasks the prompt can fully specify. If specifying takes longer than doing: do it inline.
- Context handoff: pass pointers (`path:line` ranges, commit SHAs, URLs), never pasted file content. Pasting is billed as main-loop output tokens (fable ~$50/MTok, and generating them takes wall-clock time); a worker reads the same bytes as haiku input (~$1/MTok) in one round trip. Paste only what the worker cannot retrieve itself — text that exists solely in the conversation (user message, prior tool output, fetched page) — or trivially small snippets (<~200 tokens).
- Batch independent delegations in one message so they run in parallel. Large fan-outs (e.g. review 50 modules): fan out `scout`/`extractor` workers, merge their summaries, do one final reasoning pass yourself.
- Workers end with a footer (`RESULT:` / `CHECKS-RUN:` / `UNCERTAINTIES:` / `ESCALATE:`). A worker reporting ambiguity: resolve it yourself; never re-prompt the worker to guess.

## Escalation protocol (verification first)

1. A deterministic check exists for the worker's output (tests, compiler, schema validation, diff applies, `terraform validate`): run it. Pass = done. Fail = re-dispatch one tier up (haiku worker -> equivalent sonnet worker; sonnet worker -> take over yourself), maximum one retry. Prefix the retry prompt with `[frugal-escalation from <agent>]` and include the failed attempt's footer.
2. No deterministic check: spot-read the result yourself. You receive it anyway; judging it costs almost nothing.
3. The worker's `ESCALATE: yes` is advisory input to rules 1 and 2, never the sole trigger.
4. If the task still exceeds your own tier after you take over: hand it to `sage` with the full failure history, prefixed `[frugal-escalation from main]`. One attempt, final.
5. Never start at an expensive tier unless the decision table sends you there.
