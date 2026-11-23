#!/usr/bin/env python3
"""Frugal metrics report: cost per agent tier and savings vs baseline.

Prices are USD per million tokens (verified 23-11-2026). Cache reads bill at
0.1x input unless the model has a CACHE_READ row, cache writes at 1.25x input
(5-minute TTL). Edit PRICES and CACHE_READ when Anthropic pricing changes.
"""
import argparse
import json
import os
import re
import time
from collections import Counter, defaultdict

# --advice thresholds: only speak when a route is measurably miscalibrated
ADVICE_MIN_RUNS = 5
ADVICE_WINDOW_DAYS = 14
ADVICE_HANDOFF_TOKENS = 2000
FLOOR_MIN_RUNS = 3  # below this the median per-spawn cost is noise
REPORT_MAX_ROWS = 25  # a longer agent table folds its one-off agents into "other"
SESSION_ROWS = 10  # newest sessions listed; older ones fold into one row

# substring match on the model id, first hit wins; values: (input, output) $/MTok
PRICES = [
    # ponytail: flat rate. Haiku 5.5 prompts over 100K tokens bill $0.50/$2.50,
    # but a record holds run totals, not request sizes; log per-request usage in
    # log_metrics.py if haiku workers start reading that much.
    ("haiku-5", (0.10, 0.50)),  # claude-haiku-5-5
    ("haiku", (1.00, 5.00)),  # haiku 4.5 and older
    ("sonnet-5", (2.00, 10.00)),  # claude-sonnet-5 (specific rows before generic ones)
    ("sonnet", (3.00, 15.00)),  # sonnet 4.6 and older
    ("opus-5-5", (4.00, 20.00)),  # claude-opus-5-5
    ("opus", (5.00, 25.00)),  # matches claude-opus-5 and the 4.x line, same rates
    ("fable-5-2", (8.00, 40.00)),  # claude-fable-5-2
    ("fable", (10.00, 50.00)),  # fable 5 and 5.1
]
BASELINE = ("fable", PRICES[-1][1])  # what everything would cost on the top tier
CACHE_READ_FACTOR = 0.1
CACHE_WRITE_FACTOR = 1.25
# cache-read $/MTok for models that discount it below 0.1x input. Worker and
# main-loop bills are almost all cache reads, so this row matters more than
# the input price beside it.
CACHE_READ = [
    ("sonnet-5-5", 0.10),
    ("opus-5-5", 0.20),
    ("fable-5-2", 0.20),
]


# exact ids whose PRICES and CACHE_READ rows were checked on the docstring's
# date. Any other id still gets its family's rate but is flagged, so a new
# generation cannot sit on its predecessor's price unnoticed.
VERIFIED = {
    "claude-haiku-5-5", "claude-haiku-4-5",
    "claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6",
    "claude-opus-5-5", "claude-opus-5", "claude-opus-4-8", "claude-opus-4-7",
    "claude-opus-4-6",
    "claude-fable-5-2", "claude-fable-5-1", "claude-fable-5",
}


def unverified(records):
    """Model ids in the records whose price is a family guess."""
    seen = set()
    for record in records:
        for key in ("model", "main_model"):
            model = record.get(key)
            # "<synthetic>" and friends are harness placeholders, not models
            if (isinstance(model, str) and model and model[0] != "<"
                    and re.sub(r"-\d{8}$", "", model) not in VERIFIED):
                seen.add(model)
    return sorted(seen)


def price_for(model):
    for needle, price in PRICES:
        if needle in (model or ""):
            return price
    return BASELINE[1]


def cache_read_price(model):
    for needle, price in CACHE_READ:
        if needle in (model or ""):
            return price
    return price_for(model)[0] * CACHE_READ_FACTOR


def cost_usd(record, model=None):
    """Cost of the record's tokens on `model` (default: the model that ran)."""
    model = model or record.get("model")
    p_in, p_out = price_for(model)
    return (
        record.get("input_tokens", 0) * p_in
        + record.get("output_tokens", 0) * p_out
        + record.get("cache_read_input_tokens", 0) * cache_read_price(model)
        + record.get("cache_creation_input_tokens", 0) * p_in * CACHE_WRITE_FACTOR
    ) / 1_000_000


def baseline_cost(record):
    """What this run would have cost on the session's main-loop model.
    Records predating the main_model field fall back to the top tier."""
    return cost_usd(record, record.get("main_model") or BASELINE[0])


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


def median(values):
    values = sorted(values)
    if not values:
        return 0.0
    mid = len(values) // 2
    if len(values) % 2:
        return values[mid]
    return (values[mid - 1] + values[mid]) / 2


def money(x):
    """Signed dollar amount with the minus outside the sign, e.g. -$0.06."""
    return f"-${abs(x):.2f}" if x < 0 else f"${x:.2f}"


def saved_cell(net, base):
    """Bill-style savings cell: dollar difference and percent of baseline."""
    saved = base - net
    pct = (saved / base * 100) if base else 0.0
    return f"{money(saved)} ({pct:.1f}%)"


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
    groups = defaultdict(lambda: {"runs": 0, "in": 0,
                                  "out": 0, "net": 0.0, "baseline": 0.0,
                                  "dur_ms": 0, "dur_n": 0})
    def row_name(record, fold=()):
        agent = record.get("agent_type") or "unknown"
        if agent in fold:
            agent = "other"
        model = (record.get("model") or "?").removeprefix("claude-")
        return f"{agent} [{model}]"

    # ad-hoc agents (workflow steps, named teammates) run once or twice each
    # and would bury the recurring routes under hundreds of single-run rows
    fold = ()
    if len({row_name(r) for r in records}) > REPORT_MAX_ROWS:
        runs = Counter(r.get("agent_type") or "unknown" for r in records)
        fold = {name for name, n in runs.items() if n < FLOOR_MIN_RUNS}
    for record in records:
        group = groups[row_name(record, fold)]
        group["runs"] += 1
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
        "| Agent [model] | Runs | Input tok | Output tok "
        "| Net cost | At baseline | Saved | Avg s |",
        "|---|---|---|---|---|---|---|---|",
    ]
    total = {"runs": 0, "in": 0, "out": 0,
             "net": 0.0, "baseline": 0.0}
    losing = []
    for name in sorted(groups):
        group = groups[name]
        avg_s = (f"{group['dur_ms'] / group['dur_n'] / 1000:.1f}"
                 if group["dur_n"] else "-")
        lines.append(
            f"| {name} | {group['runs']} "
            f"| {group['in']:,} | {group['out']:,} "
            f"| ${group['net']:.2f} | ${group['baseline']:.2f} "
            f"| {saved_cell(group['net'], group['baseline'])} | {avg_s} |"
        )
        if group["net"] >= group["baseline"]:
            losing.append(name)
        for key in total:
            total[key] += group[key]
    lines.append(
        f"| **Total** | **{total['runs']}** "
        f"| **{total['in']:,}** | **{total['out']:,}** "
        f"| **${total['net']:.2f}** | **${total['baseline']:.2f}** "
        f"| **{saved_cell(total['net'], total['baseline'])}** | |"
    )
    lines += [
        "",
        "*Net cost = what you paid (worker spend plus reply re-ingestion). "
        "At baseline = the same work on the main-loop model. Saved is the "
        "difference.*",
    ]
    if fold:
        lines.append(
            f"*other = {len(fold)} agent types with fewer than "
            f"{FLOOR_MIN_RUNS} runs each, folded per model.*")
    if losing:
        lines += [
            "",
            f"**Delegation loses money on:** {', '.join(losing)} — net cost "
            "meets or exceeds the main-loop baseline; do this work inline or "
            "route it cheaper.",
        ]
    guessed = unverified(records)
    if guessed:
        lines += [
            "",
            f"**Unverified prices:** {', '.join(guessed)} — priced at the "
            "family's last known rate (unknown families at top-tier rates). "
            "Check `PRICES` and `VERIFIED` in scripts/stats.py.",
        ]
    lines += [
        "",
        "Near-zero savings means work is not being delegated; check the "
        "routing skill triggers.",
    ]
    return "\n".join(lines)


def session_table(records):
    """Per-session savings: one row per session_id, newest first. Uses the
    same net-vs-baseline definition as report(), so rows reconcile with the
    totals above.

    Main loop is the session's own spend as last seen by the SubagentStop
    hook; Delegated is worker spend as a share of worker plus main-loop
    spend. Sessions logged before main_spend_usd existed show "-" and are
    left out of the summed rows' last two cells.
    """
    if not records:
        return ""
    groups = defaultdict(lambda: {"runs": 0, "net": 0.0, "baseline": 0.0,
                                  "worker": 0.0, "main": None, "first": None})
    for record in records:
        group = groups[record.get("session_id") or "unknown"]
        group["runs"] += 1
        group["net"] += net_cost(record)
        group["baseline"] += baseline_cost(record)
        # cost_usd, not net_cost: the main-loop figure already bills the
        # worker's reply being read back
        group["worker"] += cost_usd(record)
        main = record.get("main_spend_usd")
        if isinstance(main, (int, float)):
            group["main"] = max(group["main"] or 0.0, main)
        ts = record.get("ts")
        if ts is not None and (group["first"] is None or ts < group["first"]):
            group["first"] = ts

    def row(label, when, rows, wrap="{}"):
        net = sum(g["net"] for g in rows)
        base = sum(g["baseline"] for g in rows)
        cells = [str(sum(g["runs"] for g in rows)), f"${net:.2f}",
                 f"${base:.2f}", saved_cell(net, base)]
        metered = [g for g in rows if g["main"] is not None]
        if metered:
            main = sum(g["main"] for g in metered)
            worker = sum(g["worker"] for g in metered)
            share = worker / (worker + main) * 100 if worker + main else 0.0
            cells += [f"${main:.2f}", f"{share:.0f}%"]
        else:
            cells += ["-", "-"]
        return (f"| {wrap.format(label)} | {when} | "
                + " | ".join(wrap.format(c) for c in cells) + " |")

    lines = [
        "## Per-session savings",
        "",
        "| Session | When | Runs | Net cost | Baseline | Saved "
        "| Main loop | Delegated |",
        "|---|---|---|---|---|---|---|---|",
    ]
    ordered = sorted(groups, key=lambda s: groups[s]["first"] or 0, reverse=True)
    for sid in ordered[:SESSION_ROWS]:
        first = groups[sid]["first"]
        when = (time.strftime("%d-%m-%Y %H:%M", time.localtime(first))
                if first is not None else "?")
        lines.append(row(sid[:8], when, [groups[sid]]))
    older = [groups[sid] for sid in ordered[SESSION_ROWS:]]
    if older:
        lines.append(row(f"{len(older)} older", "", older))
    lines.append(row("Total", "", list(groups.values()), "**{}**"))
    lines += [
        "",
        "*Main loop = the session's own spend up to its last worker run, at "
        "the prices in force when it was logged. Delegated = worker spend as "
        "a share of worker plus main-loop spend.*",
    ]
    return "\n".join(lines)


def floor_table(records):
    """Prospective break-even: the smallest job worth delegating.

    A spawn costs about the same whether the task is tiny or large, so below
    some size doing the work in the main loop is cheaper. Dividing net cost
    per spawn by the main-loop input rate expresses that size in the only
    currency the routing decision has: tokens of reading avoided.

    Deliberately optimistic. It ignores that the worker re-reads bytes the
    main loop would have read once, so the true floor is higher.
    """
    per_agent = defaultdict(list)
    for record in records:
        name = record.get("agent_type")
        p_in, _ = price_for(record.get("main_model"))
        if name and p_in:
            per_agent[name].append(net_cost(record) / p_in * 1_000_000)
    rows = [(name, median(costs), len(costs))
            for name, costs in per_agent.items()
            if len(costs) >= FLOOR_MIN_RUNS]
    if not rows:
        return ""
    lines = [
        "## Delegation floor",
        "",
        "| Agent | Runs | Delegating pays off above |",
        "|---|---|---|",
    ]
    for name, tokens, runs in sorted(rows):
        lines.append(f"| {name} | {runs} | ~{tokens:,.0f} tokens of reading |")
    lines += [
        "",
        "*Median net cost per spawn, expressed as main-loop input tokens. "
        "Under that, read it yourself. An optimistic floor: the worker also "
        "re-reads what you would have read once.*",
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
    guessed = unverified(recent)
    if guessed:
        lines.append(
            f"frugal advice: no verified price for {', '.join(guessed)} - "
            "costs use the family's last known rate; update PRICES and "
            "VERIFIED in scripts/stats.py.")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=os.environ.get(
        "FRUGAL_METRICS_PATH",
        os.path.expanduser("~/.claude/frugal/metrics.jsonl")))
    parser.add_argument("--advice", action="store_true",
                        help="print routing feedback lines only (empty when healthy)")
    parser.add_argument("--days", type=float,
                        help="only count runs from the last N days")
    args = parser.parse_args()
    records = load(args.path)
    if args.days is not None:
        cutoff = time.time() - args.days * 86400
        records = [r for r in records if r.get("ts", 0) >= cutoff]
    if args.advice:
        text = advice(records)
        if text:
            print(text)
        return
    print(report(records))
    for table in (floor_table(records), session_table(records)):
        if table:
            print("\n" + table)


if __name__ == "__main__":
    main()
