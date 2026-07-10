#!/usr/bin/env python3
"""Compact frugal segment for a Claude Code statusline.

Prints one short line like `frugal $0.03/$1.20 saved` (session/lifetime),
or nothing at all when no metrics exist, so the statusline stays clean.
Wire it into your statusline command; see README.
"""
import argparse
import os

from stats import baseline_cost, load, net_cost


def saved(records):
    return sum(baseline_cost(r) - net_cost(r) for r in records)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", help="session_id for a session-scoped figure")
    parser.add_argument("--path", default=os.environ.get(
        "FRUGAL_METRICS_PATH",
        os.path.expanduser("~/.claude/frugal/metrics.jsonl")))
    args = parser.parse_args()
    records = load(args.path)
    if not records:
        return
    total = saved(records)
    if args.session:
        session = saved([r for r in records if r.get("session_id") == args.session])
        print(f"frugal ${session:.2f}/${total:.2f} saved")
    else:
        print(f"frugal ${total:.2f} saved")


if __name__ == "__main__":
    main()
