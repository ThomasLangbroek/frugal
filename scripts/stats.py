#!/usr/bin/env python3
"""Frugal metrics report: cost per agent tier, escalation rate, savings vs baseline.

Prices are USD per million tokens (verified 09-07-2026). Cache reads bill at
0.1x input, cache writes at 1.25x input (5-minute TTL). Edit PRICES when
Anthropic pricing changes.
"""
import argparse
import json
import os
from collections import defaultdict

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
                                  "out": 0, "cost": 0.0, "baseline": 0.0})
    for record in records:
        group = groups[record.get("agent_type") or "unknown"]
        group["runs"] += 1
        group["escalations"] += 1 if record.get("escalated") else 0
        group["in"] += record.get("input_tokens", 0)
        group["out"] += record.get("output_tokens", 0)
        group["cost"] += cost_usd(record)
        group["baseline"] += cost_usd(record, BASELINE[1])
    lines = [
        "# Frugal routing report",
        "",
        "| Agent | Runs | Escalations | Input tok | Output tok | Cost | At baseline |",
        "|---|---|---|---|---|---|---|",
    ]
    total = {"runs": 0, "escalations": 0, "cost": 0.0, "baseline": 0.0}
    for name in sorted(groups):
        group = groups[name]
        lines.append(
            f"| {name} | {group['runs']} | {group['escalations']} "
            f"| {group['in']:,} | {group['out']:,} "
            f"| ${group['cost']:.2f} | ${group['baseline']:.2f} |"
        )
        for key in total:
            total[key] += group[key]
    saved = total["baseline"] - total["cost"]
    pct = (saved / total["baseline"] * 100) if total["baseline"] else 0.0
    rate = total["escalations"] / total["runs"] * 100
    lines += [
        "",
        f"**Total cost:** ${total['cost']:.2f} | "
        f"**baseline (all-{BASELINE[0]}):** ${total['baseline']:.2f} | "
        f"**saved:** ${saved:.2f} ({pct:.1f}%)",
        f"**Escalation rate:** {total['escalations']}/{total['runs']} runs ({rate:.1f}%)",
        "",
        "A high escalation rate on an agent means its decision-table row routes "
        "too low. Near-zero savings means work is not being delegated; check the "
        "routing skill triggers.",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=os.environ.get(
        "FRUGAL_METRICS_PATH",
        os.path.expanduser("~/.claude/frugal/metrics.jsonl")))
    print(report(load(parser.parse_args().path)))


if __name__ == "__main__":
    main()
