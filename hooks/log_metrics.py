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
from datetime import datetime

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


def entry_ts(entry):
    raw = entry.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_transcript(path):
    totals = dict.fromkeys(USAGE_KEYS, 0)
    by_id = {}
    model = None
    escalated = False
    first_ts = last_ts = None
    # the LAST response's output is (approximately) the reply the main
    # loop re-ingests; intermediate turns' output stays in the worker
    final = None  # ("id", msg_id) or ("direct", output_tokens)
    try:
        handle = open(path)
    except OSError:
        return totals, model, escalated, None, 0
    with handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry_ts(entry)
            if ts is not None:
                first_ts = ts if first_ts is None else first_ts
                last_ts = ts
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
                    out = usage.get("output_tokens")
                    if isinstance(out, (int, float)):
                        final = ("direct", out)
                    continue
                bucket = by_id.setdefault(msg_id, dict.fromkeys(USAGE_KEYS, 0))
                for key in USAGE_KEYS:
                    value = usage.get(key)
                    if isinstance(value, (int, float)):
                        bucket[key] = max(bucket[key], value)
                final = ("id", msg_id)
    for bucket in by_id.values():
        for key in USAGE_KEYS:
            totals[key] += bucket[key]
    if final is None:
        handoff = 0
    elif final[0] == "id":
        handoff = by_id[final[1]]["output_tokens"]
    else:
        handoff = final[1]
    duration_ms = None
    if first_ts is not None and last_ts is not None:
        duration_ms = int(round((last_ts - first_ts) * 1000))
    return totals, model, escalated, duration_ms, handoff


def main_model_from(path, tail_bytes=65536):
    """Last assistant model in the main session transcript: the main-loop
    model at the time this worker ran. Tail-read only, so the hook stays
    cheap however long the session grows."""
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - tail_bytes))
            lines = handle.read().decode("utf-8", "replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            message = json.loads(line).get("message") or {}
        except (json.JSONDecodeError, AttributeError):
            continue
        if isinstance(message, dict) and message.get("role") == "assistant" \
                and message.get("model"):
            return message["model"]
    return None


def main():
    payload = json.load(sys.stdin)
    # agent_transcript_path is the subagent's own transcript;
    # transcript_path is the MAIN session's. Never bill the main
    # session as a subagent run: no agent transcript, no record.
    agent_transcript = payload.get("agent_transcript_path")
    if not agent_transcript or not payload.get("agent_type"):
        return  # typeless stops are internal machinery, not routed work
    totals, model, escalated, duration_ms, handoff = parse_transcript(
        agent_transcript)
    record = {
        "ts": round(time.time(), 3),
        "session_id": payload.get("session_id"),
        "agent_id": payload.get("agent_id"),
        "agent_type": payload.get("agent_type"),
        "model": model,
        "main_model": main_model_from(payload.get("transcript_path") or ""),
        "escalated": escalated,
        "duration_ms": duration_ms,
        "handoff_output_tokens": handoff,
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
