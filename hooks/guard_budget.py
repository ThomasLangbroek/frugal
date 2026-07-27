#!/usr/bin/env python3
"""Budget thermostat: warn as session spend approaches FRUGAL_BUDGET_USD.

One script, two registrations:
  UserPromptSubmit   - inject a warning at 80% of budget, a stop notice at 100%
  PreToolUse (Agent) - deny reasoning-tier spawns once over budget

Off unless FRUGAL_BUDGET_USD is set. Spend counts the main loop, not only
workers: main-loop tokens are the bigger line item, and a thermostat that
sees delegated spend alone reads 5% while the plan is empty.

Fails open like the other cost hooks: any error exits 0 and the session
continues unmetered. Only the deliberate over-budget denial exits 2.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
from stats import cost_usd  # noqa: E402  (one price table, not two)

WARN_AT = 0.8
# the set guard_expensive.sh blocks; over budget they lose the
# FRUGAL_ALLOW_EXPENSIVE override, because they cost more than the main loop
EXPENSIVE = ("general-purpose", "Explore", "Plan", "claude", "sage")
ID_CACHE = 20  # responses whose counted cost is carried between scans


def metrics_path():
    return os.environ.get("FRUGAL_METRICS_PATH") or os.path.expanduser(
        "~/.claude/frugal/metrics.jsonl")


def state_path(session_id):
    return os.path.join(os.path.dirname(metrics_path()),
                        f"budget-{session_id or 'unknown'}.json")


def read_state(session_id):
    try:
        with open(state_path(session_id), encoding="utf-8") as handle:
            state = json.load(handle)
        return state if isinstance(state, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(session_id, state):
    path = state_path(session_id)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(state, handle)
    except OSError:
        pass


def main_loop_spend(path, state):
    """Cost of the main session's own API calls, scanned incrementally.

    Re-reading a multi-megabyte transcript on every prompt would stall the
    turn, so the byte offset and running total are cached per session.

    One API response spans several transcript lines whose usage snapshots
    grow as output streams, so the bill for a response is its largest
    snapshot. Those snapshots are contiguous, so carrying the last few
    responses' counted cost across scans is enough to stop a response that
    straddles two scans being billed twice.
    """
    counted = state.get("counted")
    counted = dict(counted) if isinstance(counted, dict) else {}
    offset = state.get("offset", 0)
    cost = state.get("cost", 0.0)
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            if handle.tell() < offset:  # transcript rotated or truncated
                offset, counted, cost = 0, {}, 0.0
            handle.seek(offset)
            blob = handle.read()
    except OSError:
        return cost, state
    cut = blob.rfind(b"\n") + 1  # leave any partial trailing line for next scan
    for line in blob[:cut].decode("utf-8", "replace").splitlines():
        try:
            message = (json.loads(line) or {}).get("message") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        usage = message.get("usage") if isinstance(message, dict) else None
        if not isinstance(usage, dict):
            continue
        record = {"model": message.get("model"),
                  **{k: v for k, v in usage.items()
                     if isinstance(v, (int, float))}}
        this = cost_usd(record)
        key = message.get("id")
        if not key:
            cost += this
            continue
        if this <= counted.get(key, 0.0):
            continue
        cost += this - counted.get(key, 0.0)
        counted[key] = this
    state.update(offset=offset + cut, cost=cost,
                 counted=dict(list(counted.items())[-ID_CACHE:]))
    return cost, state


def worker_spend(session_id):
    """Delegated spend for this session, from the metrics log.

    cost_usd, not net_cost: a worker's reply is re-ingested as main-loop
    input tokens, which the main transcript already bills.
    """
    total = 0.0
    try:
        with open(metrics_path(), encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("session_id") == session_id:
                    total += cost_usd(record)
    except OSError:
        pass
    return total


def main():
    try:
        budget = float(os.environ.get("FRUGAL_BUDGET_USD"))
    except (TypeError, ValueError):
        return  # unset or unparseable: thermostat off
    if budget <= 0:
        return
    payload = json.load(sys.stdin)
    session_id = payload.get("session_id")
    state = read_state(session_id)
    spend, state = main_loop_spend(payload.get("transcript_path") or "", state)
    write_state(session_id, state)
    spend += worker_spend(session_id)
    frac = spend / budget

    if payload.get("hook_event_name") == "PreToolUse":
        if frac < 1.0:
            return
        agent = (payload.get("tool_input") or {}).get("subagent_type") or ""
        if agent in EXPENSIVE or agent.split(":")[-1] in EXPENSIVE:
            sys.stderr.write(
                f"frugal: session spend ${spend:.2f} is over the "
                f"${budget:.2f} budget, and '{agent}' costs more than doing "
                "this in the main loop. Do it inline, or raise "
                "FRUGAL_BUDGET_USD if the work is worth it.\n")
            sys.exit(2)
        return

    if frac >= 1.0:
        print(f"FRUGAL BUDGET EXHAUSTED: ${spend:.2f} of ${budget:.2f} "
              f"({frac:.0%}) this session. Stop and confirm with the user "
              "before starting new work. Cheap workers stay allowed; "
              "reasoning-tier spawns are blocked.")
    elif frac >= WARN_AT:
        print(f"FRUGAL BUDGET WARNING: ${spend:.2f} of ${budget:.2f} "
              f"({frac:.0%}) this session. Delegate harder, keep worker "
              "replies terse, avoid sage.")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)
