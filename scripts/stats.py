#!/usr/bin/env python3
"""Frugal metrics report: cost per agent tier, escalation rate, savings vs baseline.

Prices are USD per million tokens (verified 09-07-2026). Cache reads bill at
0.1x input, cache writes at 1.25x input (5-minute TTL). Edit PRICES when
Anthropic pricing changes.
"""
import argparse
import json
import os
import time
from collections import defaultdict

# --advice thresholds: only speak when a route is measurably miscalibrated
ADVICE_MIN_RUNS = 5
ADVICE_WINDOW_DAYS = 14
ADVICE_ESCALATION_RATE = 0.30
ADVICE_HANDOFF_TOKENS = 2000

# substring match on the model id, first hit wins; values: (input, output) $/MTok
PRICES = [
    ("haiku", (1.00, 5.00)),
    ("sonnet", (3.00, 15.00)),
    ("opus", (5.00, 25.00)),
    ("fable", (10.00, 50.00)),
]
BASELINE = ("fable", PRICES[-1][1])  # what everything would cost on the top tier
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25


def price_for(model):
    for needle, price in PRICES:
        if needle in (model or ""):
            return price
    return BASELINE[1]


def cost_usd(record, price=None):
    p_in, p_out = price or price_for(record.get("model"))
    return (
        record.get("input_tokens", 0) * p_in
        + record.get("output_tokens", 0) * p_out
        + record.get("cache_read_input_tokens", 0) * p_in * CACHE_READ_FACTOR
        + record.get("cache_creation_input_tokens", 0) * p_in * CACHE_WRITE_FACTOR
    ) / 1_000_000


def baseline_cost(record):
    """What this run would have cost on the session's main-loop model.
    Records predating the main_model field fall back to the top tier."""
    return cost_usd(record, price_for(record.get("main_model")))


def handoff_cost(record):
    """The worker's final reply is re-ingested by the main loop as input
    tokens at main-loop rates. Records predating handoff_output_tokens
    fall back to total output_tokens (a conservative overestimate)."""
    p_in, _ = price_for(record.get("main_model"))
    tokens = record.get("handoff_output_tokens",
                        record.get("output_tokens", 0))
    return tokens * p_in / 1_000_000


def net_cost(record):
    """True cost of the delegation: worker spend plus re-ingestion."""
    return cost_usd(record) + handoff_cost(record)


def load(path):
    records = []
    try:
        with open(path) as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    return records


def report(records):
    if not records:
        return "No metrics recorded yet (no subagent runs logged)."
    groups = defaultdict(lambda: {"runs": 0, "escalations": 0, "in": 0,
                                  "out": 0, "net": 0.0, "baseline": 0.0,
                                  "dur_ms": 0, "dur_n": 0})
    for record in records:
        group = groups[record.get("agent_type") or "unknown"]
        group["runs"] += 1
        group["escalations"] += 1 if record.get("escalated") else 0
        group["in"] += record.get("input_tokens", 0)
        group["out"] += record.get("output_tokens", 0)
        group["net"] += net_cost(record)
        group["baseline"] += baseline_cost(record)
        if isinstance(record.get("duration_ms"), (int, float)):
            group["dur_ms"] += record["duration_ms"]
            group["dur_n"] += 1
    lines = [
        "# Frugal routing report",
        "",
        "| Agent | Runs | Escalations | Input tok | Output tok "
        "| Net cost | At baseline | Avg s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total = {"runs": 0, "escalations": 0, "net": 0.0, "baseline": 0.0}
    losing = []
    for name in sorted(groups):
        group = groups[name]
        avg_s = (f"{group['dur_ms'] / group['dur_n'] / 1000:.1f}"
                 if group["dur_n"] else "-")
        lines.append(
            f"| {name} | {group['runs']} | {group['escalations']} "
            f"| {group['in']:,} | {group['out']:,} "
            f"| ${group['net']:.2f} | ${group['baseline']:.2f} | {avg_s} |"
        )
        if group["net"] >= group["baseline"]:
            losing.append(name)
        for key in total:
            total[key] += group[key]
    saved = total["baseline"] - total["net"]
    pct = (saved / total["baseline"] * 100) if total["baseline"] else 0.0
    rate = total["escalations"] / total["runs"] * 100
    lines += [
        "",
        f"**Net cost (worker + reply re-ingestion):** ${total['net']:.2f} | "
        f"**baseline (main-loop rates):** ${total['baseline']:.2f} | "
        f"**saved:** ${saved:.2f} ({pct:.1f}%)",
        f"**Escalation rate:** {total['escalations']}/{total['runs']} runs ({rate:.1f}%)",
    ]
    if losing:
        lines += [
            "",
            f"**Delegation loses money on:** {', '.join(losing)} — net cost "
            "meets or exceeds the main-loop baseline; do this work inline or "
            "route it cheaper.",
        ]
    lines += [
        "",
        "A high escalation rate on an agent means its decision-table row routes "
        "too low. Near-zero savings means work is not being delegated; check the "
        "routing skill triggers.",
    ]
    return "\n".join(lines)


def advice(records, now=None):
    """Routing feedback: 0-3 one-liners, only when a route is measurably
    miscalibrated over enough recent runs. Silent when healthy, so the
    SessionStart hook stays clean."""
    now = time.time() if now is None else now
    cutoff = now - ADVICE_WINDOW_DAYS * 86400
    recent = [r for r in records if r.get("ts", 0) >= cutoff]
    groups = defaultdict(list)
    for record in recent:
        agent_type = record.get("agent_type")
        if agent_type:
            groups[agent_type].append(record)
    lines = []
    for name in sorted(groups):
        runs = groups[name]
        if len(runs) < ADVICE_MIN_RUNS:
            continue
        escalations = sum(1 for r in runs if r.get("escalated"))
        rate = escalations / len(runs)
        if rate > ADVICE_ESCALATION_RATE:
            lines.append(
                f"frugal advice: {name} escalated {rate:.0%} of "
                f"{len(runs)} recent runs - its decision-table row routes "
                "too low; send that task class one tier up.")
        net = sum(net_cost(r) for r in runs)
        base = sum(baseline_cost(r) for r in runs)
        if net >= base:
            lines.append(
                f"frugal advice: {name} net cost (${net:.2f}) meets or "
                f"exceeds the main-loop baseline (${base:.2f}) over "
                f"{len(runs)} recent runs - delegation loses money; do this "
                "work inline or route it cheaper.")
        handoffs = [r.get("handoff_output_tokens") for r in runs
                    if isinstance(r.get("handoff_output_tokens"), (int, float))]
        if handoffs and sum(handoffs) / len(handoffs) > ADVICE_HANDOFF_TOKENS:
            avg = sum(handoffs) / len(handoffs)
            lines.append(
                f"frugal advice: {name} replies average {avg:,.0f} tokens "
                "re-ingested per run - its reply cap is not holding; demand "
                "terser output or pointers to files.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=os.environ.get(
        "FRUGAL_METRICS_PATH",
        os.path.expanduser("~/.claude/frugal/metrics.jsonl")))
    parser.add_argument("--advice", action="store_true",
                        help="print routing feedback lines only (empty when healthy)")
    args = parser.parse_args()
    records = load(args.path)
    if args.advice:
        text = advice(records)
        if text:
            print(text)
        return
    print(report(records))


if __name__ == "__main__":
    main()
