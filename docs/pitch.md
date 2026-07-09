# The pitch: why your team should run frugal

One page for the colleague or manager deciding whether to roll this out.

## The problem

Claude Code runs every session on one model — usually the most capable one
available, because that is what you want for design, debugging and judgement.
But most tool calls in a real session are not judgement: they are finding
files, grepping logs, reading configs, summarising diffs, applying mechanical
edits. Top-tier models bill top-tier rates for that commodity work, and a
single exploratory session can ingest hundreds of thousands of tokens of raw
file content at those rates.

## What frugal does

Frugal makes the expensive model the *router* instead of the *workhorse*.
It reads the request (it does anyway), splits off the commodity work, and
delegates it to cheap workers:

- locate / grep / map → Haiku (~10x cheaper than the top tier)
- extract / classify / summarise → Haiku
- mechanical edits and scoped implementation → Sonnet (~3x cheaper)
- design, debugging, ambiguity, anything risky → stays on the top model

Workers return compressed summaries, not raw file dumps, so the expensive
main loop also ingests less. A deterministic guard backs the policy up: past
a small budget of inline searches, the main loop is actively pushed to
delegate rather than explore at top-tier rates.

## Honest numbers

In our measurements, delegated work costs **~85% less** than the same work on
the top-tier model (cents instead of dollars per task). Be precise about the
claim: that saving applies to the *delegated* portion of a session, not the
whole bill. Design and review work stays on the expensive model on purpose —
that is where it earns its price. What frugal removes is paying reasoning
rates for grep.

Every install measures itself: `/frugal:router-stats` reports real cost per
tier, escalation rate, and savings versus an everything-on-top-tier baseline,
from local data. You do not have to take this document's word for anything.

## Quality control

Cheap models make more mistakes; frugal assumes so. Worker output is verified
against deterministic checks (tests, compilers, validators) where they exist,
spot-read by the main model where they do not, and escalated one tier up on
verified failure — maximum one retry, then the top model takes over. Security
sensitive changes, destructive operations and ambiguous requirements are never
delegated at all.

## Privacy and footprint

Local-only: metrics are token counts and agent names in one jsonl file on the
user's machine. No prompt content is logged, nothing is transmitted anywhere.
No dependencies beyond Python stdlib and bash; no API keys; uninstalling the
plugin removes everything except that one local file.

## Rollout suggestion

1. Two commands per person: `/plugin marketplace add ThomasLangbroek/frugal`,
   then `/plugin install frugal@frugal-marketplace`.
2. Work normally for a week. No workflow change is required; routing is
   automatic.
3. Review `/frugal:router-stats` together: delegation rate, tier mix,
   escalation rate. Tune the decision table or the `FRUGAL_INLINE_BUDGET`
   knob if the guard fires too often or too rarely.
4. Anyone who dislikes it: `FRUGAL_ALLOW_INLINE=1` softens it to advisory,
   `/plugin uninstall frugal` removes it.
