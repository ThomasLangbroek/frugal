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


def message_texts(content):
    if isinstance(content, str):
        return [content]
    if isinstance(content, list):
        return [b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"]
    return []


def parse_transcript(path):
    totals = dict.fromkeys(USAGE_KEYS, 0)
    by_id = {}
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
                # escalation re-dispatches prefix their prompt with the
                # marker; the policy text merely quotes it mid-sentence
                if any(t.startswith("[frugal-escalation")
                       for t in message_texts(message.get("content"))):
                    escalated = True
            usage = message.get("usage")
            if isinstance(usage, dict):
                model = message.get("model") or model
                # one API response spans several transcript lines whose
                # usage snapshots grow as output streams; per response
                # (message id) only the largest snapshot is the bill.
                # Lines without an id are assumed distinct responses.
                msg_id = message.get("id")
                if msg_id is None:
                    for key in USAGE_KEYS:
                        value = usage.get(key)
                        if isinstance(value, (int, float)):
                            totals[key] += value
                    continue
                bucket = by_id.setdefault(msg_id, dict.fromkeys(USAGE_KEYS, 0))
                for key in USAGE_KEYS:
                    value = usage.get(key)
                    if isinstance(value, (int, float)):
                        bucket[key] = max(bucket[key], value)
    for bucket in by_id.values():
        for key in USAGE_KEYS:
            totals[key] += bucket[key]
    return totals, model, escalated


def main():
    payload = json.load(sys.stdin)
    # agent_transcript_path is the subagent's own transcript;
    # transcript_path is the MAIN session's. Never bill the main
    # session as a subagent run: no agent transcript, no record.
    agent_transcript = payload.get("agent_transcript_path")
    if not agent_transcript:
        return
    totals, model, escalated = parse_transcript(agent_transcript)
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
