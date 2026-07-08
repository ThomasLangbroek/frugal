import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "stats.py"


def write_metrics(tmp_path, records):
    path = tmp_path / "metrics.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    return path


def run_stats(path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout


def test_report_aggregates_and_shows_savings(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "escalated": False, "input_tokens": 1_000_000, "output_tokens": 100_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        {"agent_type": "frugal:mechanic", "model": "claude-sonnet-5",
         "escalated": True, "input_tokens": 500_000, "output_tokens": 50_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "frugal:scout" in out and "frugal:mechanic" in out
    assert "escalation" in out.lower()
    assert "baseline" in out.lower()
    assert "$" in out


def test_empty_metrics_handled(tmp_path):
    path = tmp_path / "metrics.jsonl"
    path.write_text("")
    out = run_stats(path)
    assert "no metrics" in out.lower()


def test_unknown_model_priced_as_baseline(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "other", "model": "mystery-model", "escalated": False,
         "input_tokens": 1000, "output_tokens": 100,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "other" in out
