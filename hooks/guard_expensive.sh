#!/usr/bin/env bash
# PreToolUse guard: block expensive-tier subagent spawns unless explicitly allowed.
# Ships UNWIRED. To enable, add to your settings.json hooks under PreToolUse
# with matcher "Agent" (see README). Fail-open by design: any parse problem allows.
[ "${FRUGAL_ALLOW_EXPENSIVE:-0}" = "1" ] && exit 0

agent_type=$(python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    print((payload.get("tool_input") or {}).get("subagent_type", ""))
except Exception:
    print("")
' 2>/dev/null)

case "$agent_type" in
  *sage*)
    echo "frugal: blocked expensive-tier agent '$agent_type'. Set FRUGAL_ALLOW_EXPENSIVE=1 to allow this session." >&2
    exit 2
    ;;
esac
exit 0
