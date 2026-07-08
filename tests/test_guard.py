import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "guard_expensive.sh"
ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin"}


def run_guard(payload, env=None):
    return subprocess.run(
        ["bash", str(SCRIPT)],
        input=json.dumps(payload),
        text=True, capture_output=True,
        env={**ENV, **(env or {})},
    )


def test_blocks_sage_by_default():
    proc = run_guard({"tool_name": "Agent",
                      "tool_input": {"subagent_type": "frugal:sage"}})
    assert proc.returncode == 2
    assert "FRUGAL_ALLOW_EXPENSIVE" in proc.stderr


def test_allows_sage_when_flagged():
    proc = run_guard({"tool_name": "Agent",
                      "tool_input": {"subagent_type": "frugal:sage"}},
                     env={"FRUGAL_ALLOW_EXPENSIVE": "1"})
    assert proc.returncode == 0


def test_allows_cheap_agents():
    proc = run_guard({"tool_name": "Agent",
                      "tool_input": {"subagent_type": "frugal:scout"}})
    assert proc.returncode == 0


def test_garbage_input_allows():
    proc = subprocess.run(["bash", str(SCRIPT)], input="not json", text=True,
                          capture_output=True, env=ENV)
    assert proc.returncode == 0
