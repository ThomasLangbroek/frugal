#!/usr/bin/env bash
# On-demand routing eval. Costs real tokens; not for CI.
# Runs each scenario headless inside evals/fixtures/ (real artefacts, so
# tool-first cannot trivially short-circuit) and checks which frugal agent
# was spawned. Runs on --model sonnet: cheaper, and it makes the sage row
# reachable (frugal only routes to sage when a task exceeds the main
# loop's own tier).
#
# Known limitation: other installed plugins' skills can win the trigger
# race for a prompt (e.g. a debugging skill claiming the sage scenario).
# That is real routing behaviour in your environment, not a frugal bug.
set -u
cd "$(dirname "$0")"
pass=0; fail=0
while IFS= read -r line; do
  prompt=$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["prompt"])')
  expect=$(printf '%s' "$line" | python3 -c 'import json,sys; print(json.load(sys.stdin)["expect"])')
  echo "--- expect=$expect prompt=$prompt"
  # --verbose is mandatory with --print + stream-json; without it the CLI exits 1
  output=$(cd fixtures && claude -p "$prompt" --model sonnet --output-format stream-json --verbose --max-turns 8 < /dev/null 2>&1)
  spawned=$(printf '%s' "$output" | grep -o '"subagent_type":"[^"]*"' | sort -u | tr '\n' ' ')
  if printf '%s' "$spawned" | grep -q "$expect"; then
    echo "PASS ($spawned)"; pass=$((pass+1))
  else
    echo "FAIL (expected $expect; spawned: ${spawned:-none})"; fail=$((fail+1))
  fi
  # scenarios may edit or create fixture files; reset between runs
  git checkout -q -- fixtures && git clean -fdq fixtures
done < scenarios.jsonl
echo "=== $pass passed, $fail failed"
exit $((fail > 0))
