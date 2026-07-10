#!/usr/bin/env python3
"""PreToolUse inline-exploration budget.

The routing policy allows one-shot deterministic commands in the main loop
but wants iterative discovery delegated to cheap workers. This guard makes
that deterministic: after FRUGAL_INLINE_BUDGET search-type tool calls within
one user prompt, further ones are denied with a pointer to scout/extractor.
An Agent call resets the budget. Subagent tool calls are never counted or
blocked. Fail-open by design: any parse problem allows.
"""
import json
import os
import re
import sys
import tempfile

SEARCHY_TOOLS = {"Read", "Grep", "Glob"}
# a searchy word counts at any command position (start, or after ; && || | ` $( or
# newline, with optional VAR=x assignments), so prefixes like `cd x && grep` or
# `export F=1; rg` cannot dodge the counter. Words in ordinary arguments do not match.
SEARCHY_BASH = re.compile(
    r"(?:^|[;&|`\n]|\$\()\s*(?:\w+=\S*\s+)*"
    r"(rg|grep|find|fd|ls|tree|cat|head|tail|awk|jq|yq)\b")
# stdout redirected to a file means the command writes, it does not explore.
# `2>` / `2>&1` are stderr plumbing common in real searches; keep counting those.
WRITE_REDIRECT = re.compile(r"(?<![\d&])>|&>")
DEFAULT_BUDGET = 5


def counter_path(payload):
    key = f"{payload.get('session_id', 'unknown')}-{payload.get('prompt_id', 'unknown')}"
    return os.path.join(tempfile.gettempdir(), f"frugal-inline-{key}")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("agent_id") or payload.get("agent_type"):
        return 0  # subagent doing its job; never throttle workers
    tool = payload.get("tool_name", "")
    if tool == "Agent":
        try:
            os.remove(counter_path(payload))
        except OSError:
            pass
        return 0
    if os.environ.get("FRUGAL_ALLOW_INLINE") == "1":
        return 0
    if tool not in SEARCHY_TOOLS:
        if tool != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command", "")
        if not SEARCHY_BASH.search(command):
            return 0
        if WRITE_REDIRECT.search(command):
            return 0  # cat/awk/etc. writing a file is not exploration
    path = counter_path(payload)
    try:
        count = int(open(path).read())
    except Exception:
        count = 0
    count += 1
    try:
        with open(path, "w") as f:
            f.write(str(count))
    except OSError:
        return 0
    try:
        budget = int(os.environ.get("FRUGAL_INLINE_BUDGET", DEFAULT_BUDGET))
    except ValueError:
        budget = DEFAULT_BUDGET
    if count <= budget:
        return 0
    print(
        f"frugal: inline search op {count} this prompt exceeds budget of {budget}. "
        "You are exploring inline at main-loop rates. Delegate the remaining "
        "discovery to frugal:scout (locate) or frugal:extractor (read/summarise) "
        "in one Agent call; the budget resets when you delegate. "
        "Set FRUGAL_ALLOW_INLINE=1 to disable this guard.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
