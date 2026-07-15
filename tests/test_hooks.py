import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]


def hook_command(event):
    return HOOKS[event][0]["hooks"][0]["command"]


def test_events_present():
    assert {"SessionStart", "UserPromptSubmit", "SubagentStop"} <= HOOKS.keys()


def test_session_start_emits_policy():
    proc = subprocess.run(
        ["bash", "-c", hook_command("SessionStart")],
        capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "CLAUDE_PLUGIN_ROOT": str(ROOT)},
    )
    assert proc.returncode == 0
    assert "FRUGAL ROUTING ACTIVE" in proc.stdout
    assert "decision table" in proc.stdout
    assert "---" not in proc.stdout.splitlines()  # frontmatter stripped


def test_user_prompt_submit_reminder():
    proc = subprocess.run(
        ["bash", "-c", hook_command("UserPromptSubmit")],
        capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"},
    )
    assert proc.returncode == 0
    assert "FRUGAL ROUTING ACTIVE" in proc.stdout


GUARD = ROOT / "hooks" / "guard_expensive.sh"


def run_guard(payload, env_extra=None):
    env = {"PATH": "/usr/bin:/bin"}
    if env_extra:
        env.update(env_extra)
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        ["bash", str(GUARD)],
        input=body, capture_output=True, text=True, env=env,
    )


def test_guard_wired_on_agent():
    matchers = [b.get("matcher") for b in HOOKS["PreToolUse"]]
    assert "Agent" in matchers
    cmds = [h["command"] for b in HOOKS["PreToolUse"] for h in b["hooks"]]
    assert any("guard_expensive.sh" in c for c in cmds)


def test_guard_blocks_expensive_agents():
    for atype in ("Explore", "general-purpose", "claude", "Plan", "sage", "frugal:sage"):
        proc = run_guard({"tool_name": "Agent", "tool_input": {"subagent_type": atype}})
        assert proc.returncode == 2, f"{atype} should be blocked"
        assert "frugal:scout" in proc.stderr


def test_guard_blocks_bare_agent_call():
    # no subagent_type -> defaults to general-purpose -> blocked
    proc = run_guard({"tool_name": "Agent", "tool_input": {}})
    assert proc.returncode == 2
    assert "general-purpose" in proc.stderr


def test_guard_allows_cheap_and_specialised_agents():
    # exact "claude" is blocked, but "claude-code-guide" (substring) must not be
    for atype in ("frugal:scout", "frugal:extractor", "frugal:mechanic",
                  "frugal:builder", "fast-explorer", "claude-code-guide"):
        proc = run_guard({"tool_name": "Agent", "tool_input": {"subagent_type": atype}})
        assert proc.returncode == 0, f"{atype} should be allowed"


def test_guard_escape_hatch():
    proc = run_guard({"tool_name": "Agent", "tool_input": {"subagent_type": "Explore"}},
                     env_extra={"FRUGAL_ALLOW_EXPENSIVE": "1"})
    assert proc.returncode == 0


def test_guard_fails_open_on_bad_json():
    proc = run_guard("not json {{{")
    assert proc.returncode == 0
