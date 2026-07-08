#!/usr/bin/env bash
# On-demand routing eval. Costs real tokens; not for CI.
# For each scenario, runs claude -p and checks which frugal agent was spawned.
# Requires: the frugal plugin installed, claude CLI on PATH.
set -u
cd "$(dirname "$0")"
pass=0; fail=0
while IFS= read -r line; do
  prompt=$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["prompt"])')
  expect=$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["expect"])')
  echo "--- expect=$expect prompt=$prompt"
  # --verbose is mandatory with --print + stream-json; without it the CLI exits 1
  output=$(claude -p "$prompt" --output-format stream-json --verbose --max-turns 6 < /dev/null 2>&1)
  if printf '%s' "$output" | grep -q "\"subagent_type\"[^,}]*$expect"; then
    echo "PASS"; pass=$((pass+1))
  else
    echo "FAIL (expected $expect not spawned)"; fail=$((fail+1))
  fi
done < scenarios.jsonl
echo "=== $pass passed, $fail failed"
exit $((fail > 0))
