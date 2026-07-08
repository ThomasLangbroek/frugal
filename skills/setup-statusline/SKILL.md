---
name: setup-statusline
description: Wire the frugal savings segment into the user's Claude Code statusline - creates a minimal statusline if none exists, or merges the segment into an existing one.
disable-model-invocation: true
---

Add the frugal savings badge to the user's statusline. The badge comes from `scripts/statusline.py` in this plugin, which prints `frugal $<session>/$<lifetime> saved` (or nothing when no metrics exist yet).

## Steps

1. **Locate the segment script.** Find the installed copy:
   ```
   ls -d ~/.claude/plugins/cache/*/frugal/*/scripts/statusline.py 2>/dev/null | head -1
   ```
   Use the resulting absolute glob pattern (`$HOME/.claude/plugins/cache/<marketplace>/frugal/*/scripts/statusline.py` with a literal `*` for the version directory, resolved via `ls ... | head -1` at runtime) so plugin updates keep working.

2. **Read `~/.claude/settings.json`** and check the `statusLine` field. Three cases:

   **a. Already references `statusline.py` from this plugin** (in the command itself or inside the script the command runs): report that it is already configured and stop.

   **b. No `statusLine` configured:** create `~/.claude/frugal-statusline.sh` with the content below, make it executable, and set `"statusLine": {"type": "command", "command": "bash \"$HOME/.claude/frugal-statusline.sh\""}` in settings.json (ask the user before writing settings.json).

   ```bash
   #!/bin/bash
   # Minimal statusline: model + cwd + frugal savings badge
   INPUT=$(cat)
   MODEL=$(echo "$INPUT" | jq -r '.model.display_name // empty' 2>/dev/null)
   DIR=$(basename "$(echo "$INPUT" | jq -r '.cwd // "~"' 2>/dev/null)")
   SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
   FRUGAL=""
   FRUGAL_SCRIPT=$(ls -d "$HOME"/.claude/plugins/cache/*/frugal/*/scripts/statusline.py 2>/dev/null | head -1)
   if [ -n "$FRUGAL_SCRIPT" ]; then
     TXT=$(python3 "$FRUGAL_SCRIPT" ${SESSION_ID:+--session "$SESSION_ID"} 2>/dev/null)
     [ -n "$TXT" ] && FRUGAL=" \033[38;5;114m[${TXT}]\033[0m"
   fi
   printf '%b\n' "[${MODEL:-claude}] [${DIR}]${FRUGAL}"
   ```

   **c. An existing statusline is configured:** read the script or command it points at, then merge the segment into it. Preferred merge: compute the badge early and append it to the script's assembled output, following this shape:

   ```bash
   FRUGAL=""
   FRUGAL_SCRIPT=$(ls -d "$HOME"/.claude/plugins/cache/*/frugal/*/scripts/statusline.py 2>/dev/null | head -1)
   if [ -n "$FRUGAL_SCRIPT" ]; then
     SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty' 2>/dev/null)
     TXT=$(python3 "$FRUGAL_SCRIPT" ${SESSION_ID:+--session "$SESSION_ID"} 2>/dev/null)
     [ -n "$TXT" ] && FRUGAL="\033[38;5;114m[${TXT}]\033[0m"
   fi
   ```

   Adapt to the script's own conventions (variable names, how it reads stdin, how it assembles the final line). If the statusline is an inline command rather than a script, wrap it: create `~/.claude/frugal-statusline.sh` that pipes `$INPUT` to the original command and appends the badge to its output, then point `statusLine.command` at the wrapper. **Show the user the proposed edit and get consent before modifying their statusline or settings.json.**

3. **Verify.** Pipe a fake payload through the final statusline command and confirm it exits 0 and renders (badge may be absent if no metrics exist yet - that is correct behaviour, not a failure):
   ```
   echo '{"session_id":"test","cwd":"'$HOME'","model":{"display_name":"test"}}' | <statusline command>
   ```

4. Tell the user the badge appears after the first frugal worker runs (metrics land in `~/.claude/frugal/metrics.jsonl`), and that the statusline refreshes on its own.

Notes: never delete or rewrite unrelated parts of an existing statusline; make the smallest edit that adds the badge. `jq` and `python3` are required; if missing, say so instead of installing anything.
