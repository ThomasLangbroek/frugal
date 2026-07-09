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


def payload_for(transcript, agent_type="frugal:mechanic"):
    return {
        "agent_id": "abc", "agent_type": agent_type,
        "session_id": "s1", "hook_event_name": "SubagentStop",
        "transcript_path": "/nonexistent/main-session.jsonl",
        "agent_transcript_path": str(transcript),
    }


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
    metrics = run_hook(tmp_path, payload_for(transcript))
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
    metrics = run_hook(tmp_path, payload_for(transcript, "frugal:scout"))
    record = json.loads(metrics.read_text().strip())
    assert record["escalated"] is False
    assert record["model"] == "claude-haiku-4-5"


def test_marker_mid_text_is_not_escalation(tmp_path):
    # the routing policy itself quotes "[frugal-escalation" mid-sentence;
    # only a prefix on a user message counts
    transcript = make_transcript(tmp_path, [
        {"message": {"role": "user",
                     "content": "Prefix retries with [frugal-escalation from x]."}},
        {"message": {"role": "user", "content": [
            {"type": "text",
             "text": "policy says: use [frugal-escalation from main] markers"}]}},
    ])
    metrics = run_hook(tmp_path, payload_for(transcript))
    record = json.loads(metrics.read_text().strip())
    assert record["escalated"] is False


def test_duplicate_message_ids_billed_once_at_max(tmp_path):
    # streamed responses log several snapshots per message id with
    # growing output_tokens; the largest snapshot is the bill
    def usage(out):
        return {"input_tokens": 100, "output_tokens": out,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    transcript = make_transcript(tmp_path, [
        {"message": {"role": "assistant", "id": "msg_1",
                     "model": "claude-haiku-4-5", "usage": usage(1)}},
        {"message": {"role": "assistant", "id": "msg_1",
                     "model": "claude-haiku-4-5", "usage": usage(20)}},
        {"message": {"role": "assistant", "id": "msg_2",
                     "model": "claude-haiku-4-5", "usage": usage(20)}},
    ])
    metrics = run_hook(tmp_path, payload_for(transcript, "frugal:scout"))
    record = json.loads(metrics.read_text().strip())
    assert record["input_tokens"] == 200
    assert record["output_tokens"] == 40


def test_no_agent_transcript_no_record(tmp_path):
    # main-loop Stop payloads carry only transcript_path; never bill
    # the main session as a subagent run
    metrics = run_hook(tmp_path, {
        "session_id": "s1", "hook_event_name": "SubagentStop",
        "transcript_path": str(make_transcript(tmp_path, [
            {"message": {"role": "assistant", "model": "claude-fable-5",
                         "usage": {"input_tokens": 999, "output_tokens": 999}}},
        ])),
    })
    assert not metrics.exists()


def test_records_main_loop_model_from_main_transcript(tmp_path):
    worker = make_transcript(tmp_path, [
        {"message": {"role": "assistant", "model": "claude-haiku-4-5",
                     "usage": {"input_tokens": 10, "output_tokens": 2}}},
    ])
    main_transcript = tmp_path / "main.jsonl"
    main_transcript.write_text("\n".join(json.dumps(l) for l in [
        {"message": {"role": "user", "content": "hi"}},
        {"message": {"role": "assistant", "model": "claude-fable-5",
                     "usage": {"input_tokens": 1, "output_tokens": 1}}},
    ]))
    payload = payload_for(worker, "frugal:scout")
    payload["transcript_path"] = str(main_transcript)
    metrics = run_hook(tmp_path, payload)
    record = json.loads(metrics.read_text().strip())
    assert record["main_model"] == "claude-fable-5"
    assert record["model"] == "claude-haiku-4-5"


def test_missing_main_transcript_gives_null_main_model(tmp_path):
    worker = make_transcript(tmp_path, [
        {"message": {"role": "assistant", "model": "claude-haiku-4-5",
                     "usage": {"input_tokens": 10, "output_tokens": 2}}},
    ])
    metrics = run_hook(tmp_path, payload_for(worker, "frugal:scout"))
    record = json.loads(metrics.read_text().strip())
    assert record["main_model"] is None


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
    metrics = run_hook(tmp_path, payload_for(tmp_path / "nope.jsonl", "frugal:scout"))
    record = json.loads(metrics.read_text().strip())
    assert record["model"] is None
    assert record["input_tokens"] == 0
