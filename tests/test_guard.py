import json
import shutil
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


def test_blocks_bare_agent_call():
    # no subagent_type means general-purpose, which is reasoning-tier
    proc = run_guard({"tool_name": "Agent", "tool_input": {}})
    assert proc.returncode == 2


def test_namespaced_cheap_agents_allowed():
    # regression: these were all denied as 'general-purpose' on Windows
    for agent in ("frugal:mechanic", "frugal:builder", "frugal:extractor"):
        proc = run_guard({"tool_name": "Agent",
                          "tool_input": {"subagent_type": agent}})
        assert proc.returncode == 0, f"{agent} was blocked: {proc.stderr}"


def test_missing_interpreter_allows(tmp_path):
    # Windows has no python3; the guard must fail open rather than treat an
    # unreadable payload as a bare Agent call and deny every spawn.
    # PATH holds bash and nothing else, so no interpreter resolves.
    (tmp_path / "bash").symlink_to(shutil.which("bash"))
    proc = run_guard({"tool_name": "Agent",
                      "tool_input": {"subagent_type": "frugal:mechanic"}},
                     env={"PATH": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr


def test_garbage_input_allows():
    proc = subprocess.run(["bash", str(SCRIPT)], input="not json", text=True,
                          capture_output=True, env=ENV)
    assert proc.returncode == 0
