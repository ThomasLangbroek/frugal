import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "log_metrics.py"


def run_hook(tmp_path, payload):
    metrics = tmp_path / "metrics.jsonl"
    subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        text=True,
        env={"FRUGAL_METRICS_PATH": str(metrics)},
        check=True,
    )
    return metrics


def make_transcript(tmp_path, lines):
    path = tmp_path / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines))
    return path


def test_sums_usage_and_detects_escalation(tmp_path):
    transcript = make_transcript(tmp_path, [
        {"message": {"role": "user",
                     "content": "[frugal-escalation from scout] retry this"}},
        {"message": {"role": "assistant", "model": "claude-sonnet-5",
                     "usage": {"input_tokens": 100, "output_tokens": 20,
                               "cache_read_input_tokens": 5,
                               "cache_creation_input_tokens": 7}}},
        {"message": {"role": "assistant", "model": "claude-sonnet-5",
                     "usage": {"input_tokens": 50, "output_tokens": 10,
                               "cache_read_input_tokens": 0,
                               "cache_creation_input_tokens": 0}}},
        {"not_a_message": True},
    ])
    metrics = run_hook(tmp_path, {
        "agent_id": "abc", "agent_type": "frugal:mechanic",
        "session_id": "s1", "transcript_path": str(transcript),
        "hook_event_name": "SubagentStop",
    })
    record = json.loads(metrics.read_text().strip())
    assert record["agent_type"] == "frugal:mechanic"
    assert record["model"] == "claude-sonnet-5"
    assert record["escalated"] is True
    assert record["input_tokens"] == 150
    assert record["output_tokens"] == 30
    assert record["cache_read_input_tokens"] == 5
    assert record["cache_creation_input_tokens"] == 7


def test_no_escalation_marker(tmp_path):
    transcript = make_transcript(tmp_path, [
        {"message": {"role": "user", "content": "find the config"}},
        {"message": {"role": "assistant", "model": "claude-haiku-4-5",
                     "usage": {"input_tokens": 10, "output_tokens": 2,
                               "cache_read_input_tokens": 0,
                               "cache_creation_input_tokens": 0}}},
    ])
    metrics = run_hook(tmp_path, {
        "agent_id": "x", "agent_type": "frugal:scout",
        "session_id": "s1", "transcript_path": str(transcript),
    })
    record = json.loads(metrics.read_text().strip())
    assert record["escalated"] is False
    assert record["model"] == "claude-haiku-4-5"


def test_never_crashes_on_garbage(tmp_path):
    metrics = tmp_path / "metrics.jsonl"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="not json at all",
        text=True,
        env={"FRUGAL_METRICS_PATH": str(metrics)},
    )
    assert proc.returncode == 0
    assert not metrics.exists()


def test_missing_transcript_still_logs(tmp_path):
    metrics = run_hook(tmp_path, {
        "agent_id": "y", "agent_type": "frugal:scout",
        "session_id": "s1", "transcript_path": str(tmp_path / "nope.jsonl"),
    })
    record = json.loads(metrics.read_text().strip())
    assert record["model"] is None
    assert record["input_tokens"] == 0
