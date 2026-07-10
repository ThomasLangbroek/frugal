import json
import subprocess
import uuid
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "guard_inline.py"
ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin"}


def run_guard(payload, env=None):
    return subprocess.run(
        ["python3", str(SCRIPT)],
        input=json.dumps(payload),
        text=True, capture_output=True,
        env={**ENV, **(env or {})},
    )


def payload(tool, session, prompt="p1", **tool_input):
    return {"session_id": session, "prompt_id": prompt,
            "tool_name": tool, "tool_input": tool_input}


def test_blocks_after_budget():
    session = uuid.uuid4().hex
    for _ in range(5):
        assert run_guard(payload("Grep", session)).returncode == 0
    proc = run_guard(payload("Grep", session))
    assert proc.returncode == 2
    assert "frugal:scout" in proc.stderr


def test_agent_call_resets_budget():
    session = uuid.uuid4().hex
    for _ in range(6):
        run_guard(payload("Grep", session))
    assert run_guard(payload("Agent", session)).returncode == 0
    assert run_guard(payload("Grep", session)).returncode == 0


def test_new_prompt_resets_budget():
    session = uuid.uuid4().hex
    for _ in range(6):
        run_guard(payload("Grep", session, prompt="p1"))
    assert run_guard(payload("Grep", session, prompt="p2")).returncode == 0


def test_subagent_calls_never_counted():
    session = uuid.uuid4().hex
    for _ in range(10):
        p = payload("Grep", session)
        p["agent_type"] = "frugal:scout"
        assert run_guard(p).returncode == 0


def test_non_searchy_bash_ignored():
    session = uuid.uuid4().hex
    for _ in range(10):
        assert run_guard(payload("Bash", session, command="git commit -m x")).returncode == 0


def test_searchy_bash_counted():
    session = uuid.uuid4().hex
    for _ in range(5):
        run_guard(payload("Bash", session, command="rg pattern src/"))
    assert run_guard(payload("Bash", session, command="find . -name x")).returncode == 2


def test_env_disable():
    session = uuid.uuid4().hex
    for _ in range(10):
        proc = run_guard(payload("Grep", session), env={"FRUGAL_ALLOW_INLINE": "1"})
        assert proc.returncode == 0


def test_custom_budget():
    session = uuid.uuid4().hex
    env = {"FRUGAL_INLINE_BUDGET": "1"}
    assert run_guard(payload("Grep", session), env=env).returncode == 0
    assert run_guard(payload("Grep", session), env=env).returncode == 2


def test_garbage_input_allows():
    proc = subprocess.run(["python3", str(SCRIPT)], input="not json",
                          text=True, capture_output=True, env=ENV)
    assert proc.returncode == 0


def test_write_redirect_not_counted():
    # `cat >> file` is a write, not exploration (the bug that bit us live)
    session = uuid.uuid4().hex
    for _ in range(10):
        assert run_guard(payload(
            "Bash", session, command="cat >> tests/test_x.py <<'EOF'\nx\nEOF")).returncode == 0
    assert run_guard(payload("Bash", session, command="awk '{print}' a > b")).returncode == 0


def test_stderr_redirect_still_counted():
    # 2>/dev/null and 2>&1 are search plumbing, not writes
    session = uuid.uuid4().hex
    for _ in range(5):
        run_guard(payload("Bash", session, command="rg pattern src/ 2>/dev/null"))
    assert run_guard(payload("Bash", session, command="find . -name x 2>&1")).returncode == 2


def test_prefixed_search_commands_counted():
    # prefixes must not dodge the counter
    session = uuid.uuid4().hex
    cmds = [
        "export FOO=1; rg pattern src/",
        "cd /tmp && grep -r x .",
        "FOO=bar rg pattern",
        "true || find . -name x",
        "echo start\nls -la",
    ]
    for c in cmds:
        run_guard(payload("Bash", session, command=c))
    assert run_guard(payload("Bash", session, command="cd /x && cat file")).returncode == 2


def test_searchy_word_as_argument_ignored():
    session = uuid.uuid4().hex
    for _ in range(10):
        assert run_guard(payload(
            "Bash", session, command='git commit -m "fix cat and grep handling"')).returncode == 0
