import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

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
    assert "scalation" not in out
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
    # worker (sonnet 5): 100k*$2 + 50k*$10 = $0.70; handoff 50k*$1 = $0.05
    # net $0.75 vs baseline (haiku): 100k*$1 + 50k*$5 = $0.35 -> loses
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


def floor_records(*input_tokens):
    return [
        {"agent_type": "frugal:scout", "model": "claude-haiku-4-5",
         "main_model": "claude-fable-5", "escalated": False,
         "input_tokens": n, "output_tokens": 0,
         "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
        for n in input_tokens
    ]


def test_floor_reports_median_break_even(tmp_path):
    # haiku worker under a fable main loop, no reply to re-ingest:
    # net is $1/$2/$3, and fable reads at $10/MTok -> 100k/200k/300k tokens.
    # the median run is the floor, so 200,000.
    path = write_metrics(tmp_path, floor_records(1_000_000, 2_000_000, 3_000_000))
    out = run_stats(path)
    assert "Delegation floor" in out
    assert "~200,000 tokens of reading" in out


def test_floor_hidden_below_minimum_runs(tmp_path):
    path = write_metrics(tmp_path, floor_records(1_000_000, 2_000_000))
    assert "Delegation floor" not in run_stats(path)


def run_advice(path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(path), "--advice"],
        capture_output=True, text=True, check=True,
    ).stdout


def recent(agent_type, n, **overrides):
    import time as _time
    base = {"agent_type": agent_type, "model": "claude-haiku-4-5",
            "main_model": "claude-fable-5",
            "ts": _time.time(), "input_tokens": 100_000,
            "output_tokens": 5_000, "handoff_output_tokens": 500,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    return [{**base, **overrides} for _ in range(n)]


def test_advice_silent_when_healthy(tmp_path):
    path = write_metrics(tmp_path, recent("frugal:scout", 10))
    assert run_advice(path) == ""


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
    path = write_metrics(tmp_path, recent("frugal:scout", 4, handoff_output_tokens=5_000))
    assert run_advice(path) == ""


def test_advice_ignores_stale_records(tmp_path):
    path = write_metrics(tmp_path, recent(
        "frugal:scout", 10, handoff_output_tokens=5_000, ts=1.0))  # 1970: far outside window
    assert run_advice(path) == ""


def test_price_for_distinguishes_generations():
    sys.path.insert(0, str(ROOT / "scripts"))
    from stats import price_for
    assert price_for("claude-sonnet-5") == (2.00, 10.00)
    assert price_for("claude-sonnet-4-6") == (3.00, 15.00)
    assert price_for("claude-fable-5-1") == (10.00, 50.00)
    assert price_for("claude-haiku-5-5") == (0.10, 0.50)
    assert price_for("claude-haiku-4-5-20251001") == (1.00, 5.00)
    assert price_for("claude-sonnet-5-5") == (2.00, 10.00)
    assert price_for("claude-opus-5-5") == (4.00, 20.00)
    assert price_for("claude-opus-5") == (5.00, 25.00)
    assert price_for("claude-fable-5-2") == (8.00, 40.00)
    assert price_for("claude-fable-5") == (10.00, 50.00)


def test_cache_read_price_per_model():
    sys.path.insert(0, str(ROOT / "scripts"))
    from stats import cache_read_price, cost_usd
    assert cache_read_price("claude-fable-5-2") == 0.20
    assert cache_read_price("claude-opus-5-5") == 0.20
    assert cache_read_price("claude-sonnet-5-5") == 0.10
    assert cache_read_price("claude-sonnet-5") == pytest.approx(0.20)
    assert cache_read_price("claude-haiku-4-5") == pytest.approx(0.10)
    assert cache_read_price("claude-fable-5-1") == pytest.approx(1.00)
    rec = {"model": "claude-fable-5-2", "cache_read_input_tokens": 1_000_000}
    assert cost_usd(rec) == pytest.approx(0.20)
    assert cost_usd(rec, "claude-fable-5") == pytest.approx(1.00)


def test_baseline_falls_back_to_top_tier_without_main_model():
    sys.path.insert(0, str(ROOT / "scripts"))
    from stats import baseline_cost
    rec = {"model": "claude-haiku-5-5", "input_tokens": 1_000_000}
    assert baseline_cost(rec) == pytest.approx(10.00)
    assert baseline_cost({**rec, "main_model": "claude-opus-5-5"}) == pytest.approx(4.00)


def test_report_folds_one_off_agents_when_table_is_long(tmp_path):
    runs = [dict(r, agent_type=f"adhoc-{i}", model="claude-sonnet-5")
            for i, r in enumerate(recent("x", 30))]
    runs += recent("frugal:scout", 3, model="claude-haiku-5-5")
    out = run_stats(write_metrics(tmp_path, runs))
    assert "frugal:scout [haiku-5-5]" in out
    assert "other [sonnet-5]" in out
    assert "30 agent types" in out
    assert "adhoc-0 " not in out


def test_report_keeps_short_table_unfolded(tmp_path):
    runs = [dict(r, agent_type=f"adhoc-{i}") for i, r in enumerate(recent("x", 2))]
    out = run_stats(write_metrics(tmp_path, runs))
    assert "adhoc-0" in out and "adhoc-1" in out
    assert "other [" not in out


def test_session_table_folds_older_sessions(tmp_path):
    runs = [dict(r, session_id=f"sess{i:04d}-xxxx", ts=100.0 + i)
            for i, r in enumerate(recent("frugal:scout", 12))]
    out = run_stats(write_metrics(tmp_path, runs))
    assert "2 older" in out
    assert "sess0011" in out
    assert "sess0000" not in out


def test_days_filter(tmp_path):
    path = write_metrics(tmp_path, recent("frugal:scout", 1, ts=1.0)
                         + recent("frugal:scout", 1, ts=time.time()))
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--path", str(path), "--days", "1"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "| **Total** | **1** |" in out


def _rec(model, **kw):
    return {"agent_type": "frugal:scout", "model": model,
            "input_tokens": 1_000_000, "output_tokens": 0,
            "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
            **kw}


def test_unverified_models_flagged_in_report(tmp_path):
    out = run_stats(write_metrics(tmp_path, [
        _rec("claude-haiku-6", main_model="claude-fable-5-2")]))
    assert "Unverified prices:" in out and "claude-haiku-6" in out
    line = next(l for l in out.splitlines() if "Unverified prices:" in l)
    assert "claude-fable-5-2" not in line.split("Unverified prices:")[1]
    out = run_stats(write_metrics(tmp_path, [
        _rec("claude-haiku-4-5-20251001", main_model="claude-fable-5-2")]))
    assert "Unverified prices" not in out
    out = run_stats(write_metrics(tmp_path, [_rec("<synthetic>")]))
    assert "Unverified prices" not in out


def test_advice_flags_unverified_model(tmp_path):
    path = write_metrics(tmp_path, [
        _rec("claude-sonnet-6", ts=time.time()) for _ in range(3)])
    assert "no verified price for claude-sonnet-6" in run_advice(path)
    path = write_metrics(tmp_path, [
        _rec("claude-sonnet-6", ts=1.0) for _ in range(3)])
    assert run_advice(path) == ""


def _metered(sid="sessionA", **kw):
    return [_rec("claude-haiku-5-5", session_id=sid, ts=time.time(), **kw)
            for _ in range(2)]


def test_session_table_shows_main_loop_share(tmp_path):
    recs = _metered(main_spend_usd=1.0)
    recs[1]["main_spend_usd"] = 1.8
    out = run_stats(write_metrics(tmp_path, recs))
    assert any("| $1.80 | 10% |" in l for l in out.splitlines()
               if l.startswith("| sessionA"))
    out = run_stats(write_metrics(tmp_path, _metered()))
    assert any(l.endswith("| - | - |") for l in out.splitlines()
               if l.startswith("| sessionA"))


def test_session_total_ignores_unmetered_sessions_for_share(tmp_path):
    recs = _metered(main_spend_usd=1.0)
    recs[1]["main_spend_usd"] = 1.8
    recs.append(_rec("claude-haiku-5-5", session_id="sessionB", ts=time.time()))
    out = run_stats(write_metrics(tmp_path, recs))
    total = next(l for l in out.splitlines() if "**Total**" in l and "$1.80" in l)
    assert "**$1.80**" in total and "**10%**" in total
