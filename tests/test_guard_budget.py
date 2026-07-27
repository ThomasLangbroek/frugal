import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "guard_budget.py"


def run_hook(tmp_path, payload, budget=None):
    env = {"FRUGAL_METRICS_PATH": str(tmp_path / "metrics.jsonl")}
    if budget is not None:
        env["FRUGAL_BUDGET_USD"] = str(budget)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True, capture_output=True, env=env,
    )


def transcript(tmp_path, *turns, name="transcript.jsonl"):
    """One assistant turn per (msg_id, output_tokens) pair. Haiku output bills
    at $5/MTok, so 200_000 output tokens is exactly $1.00."""
    path = tmp_path / name
    with open(path, "a", encoding="utf-8") as handle:
        for msg_id, out in turns:
            handle.write(json.dumps({"message": {
                "role": "assistant", "model": "claude-haiku-4-5",
                "id": msg_id, "usage": {"output_tokens": out}}}) + "\n")
    return path


def prompt(path, session="s1"):
    return {"hook_event_name": "UserPromptSubmit", "session_id": session,
            "transcript_path": str(path)}


def spawn(path, agent, session="s1"):
    return {"hook_event_name": "PreToolUse", "session_id": session,
            "transcript_path": str(path), "tool_name": "Agent",
            "tool_input": {"subagent_type": agent}}


def test_off_without_budget(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))
    proc = run_hook(tmp_path, prompt(path))
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_silent_under_warn_threshold(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))  # $1.00 of $2.00
    proc = run_hook(tmp_path, prompt(path), budget=2.00)
    assert proc.stdout == "", proc.stdout


def test_warns_at_eighty_percent(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))  # $1.00 of $1.25
    proc = run_hook(tmp_path, prompt(path), budget=1.25)
    assert "FRUGAL BUDGET WARNING" in proc.stdout
    assert "$1.00 of $1.25" in proc.stdout


def test_exhausted_notice_at_budget(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))
    proc = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "FRUGAL BUDGET EXHAUSTED" in proc.stdout


def test_counts_worker_spend_for_this_session(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))  # $1.00 main loop
    (tmp_path / "metrics.jsonl").write_text("".join(
        json.dumps({"session_id": sid, "model": "claude-haiku-4-5",
                    "output_tokens": 100_000}) + "\n"  # $0.50 each
        for sid in ("s1", "other")), encoding="utf-8")
    proc = run_hook(tmp_path, prompt(path), budget=1.75)
    # $1.00 main + $0.50 this session, and not the other session's $0.50
    assert "$1.50 of $1.75" in proc.stdout


def test_streaming_snapshots_billed_once(tmp_path):
    # usage snapshots for one response grow as output streams; the bill is
    # the largest, not the sum
    path = transcript(tmp_path, ("msg_1", 100_000), ("msg_1", 200_000))
    proc = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "$1.00 of $1.00" in proc.stdout


def test_incremental_scan_does_not_double_count(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))
    first = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "$1.00 of $1.00" in first.stdout
    second = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "$1.00 of $1.00" in second.stdout, "rescanned already-billed lines"
    transcript(tmp_path, ("msg_2", 200_000))
    third = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "$2.00 of $1.00" in third.stdout, "new turn not billed"


def test_response_straddling_two_scans_billed_once(tmp_path):
    path = transcript(tmp_path, ("msg_1", 100_000))
    run_hook(tmp_path, prompt(path), budget=1.00)
    transcript(tmp_path, ("msg_1", 200_000))  # same response, fuller snapshot
    proc = run_hook(tmp_path, prompt(path), budget=1.00)
    assert "$1.00 of $1.00" in proc.stdout, "double-billed across scans"


def test_blocks_sage_over_budget(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))
    proc = run_hook(tmp_path, spawn(path, "frugal:sage"), budget=1.00)
    assert proc.returncode == 2
    assert "over the $1.00 budget" in proc.stderr


def test_allows_cheap_workers_over_budget(tmp_path):
    # cheap workers reduce spend; blocking them would push work back into the
    # main loop, which is what emptied the budget
    path = transcript(tmp_path, ("msg_1", 200_000))
    for agent in ("frugal:scout", "frugal:extractor", "frugal:mechanic"):
        proc = run_hook(tmp_path, spawn(path, agent), budget=1.00)
        assert proc.returncode == 0, f"{agent} blocked: {proc.stderr}"


def test_allows_sage_under_budget(tmp_path):
    path = transcript(tmp_path, ("msg_1", 200_000))
    proc = run_hook(tmp_path, spawn(path, "frugal:sage"), budget=10.00)
    assert proc.returncode == 0, proc.stderr


def test_missing_transcript_fails_open(tmp_path):
    proc = run_hook(tmp_path, prompt(tmp_path / "absent.jsonl"), budget=1.00)
    assert proc.returncode == 0
    assert proc.stdout == ""


def test_garbage_input_fails_open(tmp_path):
    proc = subprocess.run([sys.executable, str(SCRIPT)], input="not json",
                          text=True, capture_output=True,
                          env={"FRUGAL_BUDGET_USD": "1.00"})
    assert proc.returncode == 0
