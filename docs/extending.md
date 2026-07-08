# Extending frugal

Frugal routes on capabilities, not model names. Adding a tier changes no logic anywhere: it is one agent file, one decision-table row, and optionally one price entry.

## 1. Add an agent file

Create `agents/<name>.md`. The `description` frontmatter advertises capabilities; the router matches task signals against it. Keep the body short and end with the worker footer contract, verbatim:

```markdown
---
name: summariser
description: Batch summarisation across many sources. Capabilities - multi-doc-summarise, merge-summaries. Use when many documents need independent summaries merged into one. Inputs must be fully provided.
tools: Read, Grep, Glob
model: haiku
---

You are summariser, frugal's batch summarisation worker.

Rules:
- Summarise only material provided or explicitly pointed to.
- One summary per source, then a merged overview if asked.
- If interpretation or judgement is needed: stop, set ESCALATE: yes, name the ambiguity.

End every reply with exactly this footer:

RESULT: <one line>
CHECKS-RUN: <commands run and outcomes, or "none">
UNCERTAINTIES: <or "none">
ESCALATE: yes|no - <reason>
```

`model` accepts `haiku`, `sonnet`, `opus`, `fable`, `inherit`, or a full model ID.

## 2. Add a decision-table row

In `skills/routing/SKILL.md`, add one row to the table in Step 2:

```markdown
| summarise many documents and merge the results | multi-doc-summarise | `summariser` (haiku) |
```

## 3. Optionally: price entry

If the new agent uses a model family not in `scripts/stats.py` `PRICES`, add a `(substring, (input, output))` entry so `/frugal:router-stats` prices it correctly. Unknown models are priced at the baseline (top tier), which overstates their cost.

## 4. Test

`tests/test_agents.py` checks frontmatter and the footer contract. Add your agent to `EXPECTED` there. Optionally add a scenario line to `evals/scenarios.jsonl`.

That is the whole extension surface. If you find yourself wanting to edit routing logic, the design has failed; open an issue instead.
