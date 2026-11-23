#!/usr/bin/env bash
# PreToolUse guard (matcher: Agent): block reasoning/expensive-tier subagent
# spawns so locate/extract/summarise work is routed to cheap workers instead.
# Wired in hooks.json under PreToolUse matcher "Agent".
# Escape hatch: export FRUGAL_ALLOW_EXPENSIVE=1 to allow expensive agents this
# session. Fail-open on unparseable input; a bare Agent call (no subagent_type)
# is treated as general-purpose and blocked.
# A spawn that pins a cheap tier through the Agent tool's `model` parameter
# (haiku or sonnet) is not expensive whatever its type, so it passes. `fork`
# is the exception: it ignores `model` and always runs on the main-loop model.
[ "${FRUGAL_ALLOW_EXPENSIVE:-0}" = "1" ] && exit 0

# Windows has no `python3` on PATH — it ships `python` and the `py` launcher.
# Resolving this matters for more than tidiness: an unresolvable interpreter
# left agent_type empty, and the omitted-type default below then read that as
# a bare Agent call and blocked it, so every spawn on Windows was denied and
# reported as 'general-purpose' regardless of the subagent_type asked for.
for candidate in python3 python py; do
  command -v "$candidate" >/dev/null 2>&1 && frugal_py="$candidate" && break
done
[ -z "${frugal_py:-}" ] && exit 0                       # no interpreter: fail open

agent_type=$("$frugal_py" -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except Exception:
    print("__PARSE_FAIL__"); sys.exit(0)
tool_input = payload.get("tool_input") or {}
print(tool_input.get("subagent_type") or "", tool_input.get("model") or "", sep="|")
' 2>/dev/null) || exit 0                                # interpreter failed: fail open

[ "$agent_type" = "__PARSE_FAIL__" ] && exit 0          # bad input: fail open
agent_model=${agent_type#*|}
agent_type=${agent_type%%|*}
[ -z "$agent_type" ] && agent_type="general-purpose"    # omitted type defaults to general-purpose

if [ "$agent_type" != "fork" ]; then
  case "$agent_model" in haiku|sonnet) exit 0 ;; esac
fi

case "$agent_type" in
  general-purpose|Explore|Plan|claude|fork|sage|*:sage)
    echo "frugal: blocked reasoning-tier agent '$agent_type'. Route locate/map -> frugal:scout, extract/summarise/classify -> frugal:extractor, mechanical edits -> frugal:mechanic or frugal:builder. A generic agent pinned to a cheap tier (Agent model: haiku or sonnet) is allowed. If the task genuinely needs main-loop breadth, set FRUGAL_ALLOW_EXPENSIVE=1 to allow this session." >&2
    exit 2
    ;;
esac
exit 0
