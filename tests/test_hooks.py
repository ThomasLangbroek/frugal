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
