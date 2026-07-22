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


def test_report_has_saved_column_and_total_row(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "| Saved |" in out           # bill line-item column
    assert "**Total**" in out           # bill total row
    # one haiku run: $1.00 net vs $10.00 baseline -> $9.00 saved, 90%
    assert "$9.00 (90.0%)" in out


def test_negative_saving_formats_with_leading_minus(tmp_path):
    # sonnet worker under haiku main loop: costs more than baseline
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:extractor", "model": "claude-sonnet-5",
         "main_model": "claude-haiku-4-5", "escalated": False,
         "input_tokens": 100_000, "output_tokens": 50_000,
         "handoff_output_tokens": 50_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "-$" in out  # minus outside the dollar sign


def test_empty_metrics_handled(tmp_path):
    path = tmp_path / "metrics.jsonl"
    path.write_text("")
    out = run_stats(path)
    assert "no metrics" in out.lower()


def test_statusline_session_and_total(tmp_path):
    path = write_metrics(tmp_path, [
        {"session_id": "s1", "agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "escalated": False, "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        {"session_id": "s2", "agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "escalated": False, "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "statusline.py"),
         "--path", str(path), "--session", "s1"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    # each run: haiku $1 vs fable $10 per MTok input -> $9 saved
    assert out == "frugal $9.00/$18.00 saved"


def test_statusline_silent_without_metrics(tmp_path):
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "statusline.py"),
         "--path", str(tmp_path / "missing.jsonl")],
        capture_output=True, text=True, check=True,
    ).stdout
    assert out == ""


def test_baseline_follows_main_model(tmp_path):
    # haiku worker ($1/MTok in) under an opus main loop ($5/MTok in):
    # baseline is opus, not the top tier -> $4 saved, not $9
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-opus-4-8", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "statusline.py"), "--path", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert out == "frugal $4.00 saved"


def test_unknown_model_priced_as_baseline(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "other", "model": "mystery-model", "escalated": False,
         "input_tokens": 1000, "output_tokens": 100,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "other" in out


def test_net_cost_includes_reply_reingestion(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 100_000,
         "handoff_output_tokens": 100_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "statusline.py"), "--path", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    # worker: 1M*$1 + 100k*$5 = $1.50; handoff: 100k*$10 = $1.00; net $2.50
    # baseline: 1M*$10 + 100k*$50 = $15.00 -> saved $12.50
    assert out == "frugal $12.50 saved"


def test_losing_delegation_flagged_when_net_exceeds_baseline(tmp_path):
    # wrong-direction route: sonnet worker under a haiku main loop
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:extractor", "model": "claude-sonnet-5",
         "main_model": "claude-haiku-4-5", "escalated": False,
         "input_tokens": 100_000, "output_tokens": 50_000,
         "handoff_output_tokens": 50_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    # worker (sonnet): 100k*$3 + 50k*$15 = $1.05; handoff 50k*$1 = $0.05
    # net $1.10 vs baseline (haiku): 100k*$1 + 50k*$5 = $0.35 -> loses
    assert "loses money" in out
    assert "frugal:extractor" in out


def test_winning_delegation_not_flagged(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 10_000,
         "handoff_output_tokens": 10_000,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "loses money" not in out


def test_avg_duration_in_report(tmp_path):
    path = write_metrics(tmp_path, [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "escalated": False, "duration_ms": 4000,
         "input_tokens": 1000, "output_tokens": 100,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "escalated": False, "duration_ms": 6000,
         "input_tokens": 1000, "output_tokens": 100,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "5.0" in out  # avg of 4s and 6s



def test_session_table_groups_sorts_and_saves(tmp_path):
    # two single-run sessions, haiku worker under fable main loop.
    # each: 1M*$1 = $1.00 net vs 1M*$10 = $10.00 baseline -> $9.00 saved.
    path = write_metrics(tmp_path, [
        {"session_id": "aaaaaaaa-old", "ts": 100.0,
         "agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
        {"session_id": "bbbbbbbb-new", "ts": 200.0,
         "agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": 1_000_000, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0},
    ])
    out = run_stats(path)
    assert "Per-session savings" in out
    assert "$9.00 (90.0%)" in out
    # newest first: the ts=200 session outranks the ts=100 one
    assert out.index("bbbbbbbb") < out.index("aaaaaaaa")


def run_advice(path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(path), "--advice"],
        capture_output=True, text=True, check=True,
    ).stdout


def recent(agent_type, n, **overrides):
    import time as _time
    base = {"agent_type": agent_type, "model": "claude-haiku-4-5",
            "main_model": "claude-fable-5", "escalated": False,
            "ts": _time.time(), "input_tokens": 100_000,
            "output_tokens": 5_000, "handoff_output_tokens": 500,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    return [{**base, **overrides} for _ in range(n)]


def test_advice_silent_when_healthy(tmp_path):
    path = write_metrics(tmp_path, recent("frugal:scout", 10))
    assert run_advice(path) == ""


def test_advice_flags_high_escalation(tmp_path):
    runs = recent("frugal:scout", 6) + recent("frugal:scout", 4, escalated=True)
    path = write_metrics(tmp_path, runs)
    out = run_advice(path)
    assert "frugal:scout" in out and "one tier up" in out


def test_advice_flags_losing_route(tmp_path):
    # sonnet worker under haiku main loop: net always exceeds baseline
    path = write_metrics(tmp_path, recent(
        "frugal:extractor", 6, model="claude-sonnet-5",
        main_model="claude-haiku-4-5"))
    out = run_advice(path)
    assert "loses money" in out


def test_advice_flags_fat_handoffs(tmp_path):
    path = write_metrics(tmp_path, recent(
        "frugal:mechanic", 6, handoff_output_tokens=5_000))
    out = run_advice(path)
    assert "reply cap is not holding" in out


def test_advice_needs_minimum_runs(tmp_path):
    path = write_metrics(tmp_path, recent("frugal:scout", 4, escalated=True))
    assert run_advice(path) == ""


def test_advice_ignores_stale_records(tmp_path):
    path = write_metrics(tmp_path, recent(
        "frugal:scout", 10, escalated=True, ts=1.0))  # 1970: far outside window
    assert run_advice(path) == ""
