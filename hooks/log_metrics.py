#!/usr/bin/env python3
"""SubagentStop hook: append one metrics line per completed subagent.

Reads the hook payload on stdin, sums token usage from the subagent
transcript, and appends a jsonl record. Must never break a session:
always exits 0, swallows every error.
"""
import json
import os
import sys
import time

USAGE_KEYS = (
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
)


def parse_transcript(path):
    totals = dict.fromkeys(USAGE_KEYS, 0)
    model = None
    escalated = False
    try:
        handle = open(path)
    except OSError:
        return totals, model, escalated
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = entry.get("message")
            if not isinstance(message, dict):
                continue
            if not escalated and message.get("role") == "user":
                content = message.get("content")
                text = content if isinstance(content, str) else json.dumps(content)
                if "[frugal-escalation" in text:
                    escalated = True
            usage = message.get("usage")
            if isinstance(usage, dict):
                model = message.get("model") or model
                for key in USAGE_KEYS:
                    value = usage.get(key)
                    if isinstance(value, (int, float)):
                        totals[key] += value
    return totals, model, escalated


def main():
    payload = json.load(sys.stdin)
    totals, model, escalated = parse_transcript(payload.get("transcript_path") or "")
    record = {
        "ts": round(time.time(), 3),
        "session_id": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type"),
        "model": model,
        "escalated": escalated,
        **totals,
    }
    path = os.environ.get("FRUGAL_METRICS_PATH") or os.path.expanduser(
        "~/.claude/frugal/metrics.jsonl"
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as handle:
        handle.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)
