import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "hooks" / "guard_sensitive.py"
ENV = {"PATH": "/usr/bin:/bin:/usr/local/bin"}

IBAN_RULE = [{"name": "pii", "patterns": [r"\bNL\d{2}[A-Z]{4}\d{10}\b"],
              "allow_agents": []}]


def run_guard(payload, env=None):
    return subprocess.run(
        ["python3", str(SCRIPT)],
        input=json.dumps(payload),
        text=True, capture_output=True,
        env={**ENV, **(env or {})},
    )


def spawn(prompt, agent="frugal:extractor"):
    return {"tool_name": "Agent",
            "tool_input": {"subagent_type": agent, "prompt": prompt}}


def write_config(tmp_path, data):
    cfg = tmp_path / "sensitivity.json"
    cfg.write_text(data if isinstance(data, str) else json.dumps(data))
    return {"FRUGAL_SENSITIVITY_CONFIG": str(cfg)}


def test_no_config_allows(tmp_path):
    env = {"FRUGAL_SENSITIVITY_CONFIG": str(tmp_path / "missing.json")}
    proc = run_guard(spawn("NL12ABCD3456789012"), env=env)
    assert proc.returncode == 0


def test_matching_pattern_blocks(tmp_path):
    env = write_config(tmp_path, IBAN_RULE)
    proc = run_guard(spawn("pay out to NL12ABCD3456789012 please"), env=env)
    assert proc.returncode == 2
    assert "pii" in proc.stderr


def test_allow_agents_bypasses(tmp_path):
    rule = [{"name": "pii", "patterns": [r"\bNL\d{2}[A-Z]{4}\d{10}\b"],
             "allow_agents": ["frugal:extractor"]}]
    env = write_config(tmp_path, rule)
    proc = run_guard(spawn("NL12ABCD3456789012", agent="frugal:extractor"), env=env)
    assert proc.returncode == 0


def test_non_matching_allows(tmp_path):
    env = write_config(tmp_path, IBAN_RULE)
    proc = run_guard(spawn("summarise the changelog for me"), env=env)
    assert proc.returncode == 0


def test_path_glob_blocks(tmp_path):
    rule = [{"name": "keys", "paths": ["*.pem"], "allow_agents": []}]
    env = write_config(tmp_path, rule)
    proc = run_guard(spawn("read config/tls/server.pem and summarise"), env=env)
    assert proc.returncode == 2
    assert "keys" in proc.stderr


def test_unparseable_config_blocks(tmp_path):
    env = write_config(tmp_path, "{ this is not json")
    proc = run_guard(spawn("anything"), env=env)
    assert proc.returncode == 2
    assert "fail closed" in proc.stderr


def test_invalid_regex_blocks(tmp_path):
    rule = [{"name": "bad", "patterns": ["("], "allow_agents": []}]
    env = write_config(tmp_path, rule)
    proc = run_guard(spawn("anything"), env=env)
    assert proc.returncode == 2
    assert "invalid regex" in proc.stderr


def test_non_agent_tool_ignored(tmp_path):
    env = write_config(tmp_path, IBAN_RULE)
    proc = run_guard({"tool_name": "Bash",
                      "tool_input": {"command": "echo NL12ABCD3456789012"}},
                     env=env)
    assert proc.returncode == 0


def test_garbage_input_allows():
    proc = subprocess.run(["python3", str(SCRIPT)], input="not json",
                          text=True, capture_output=True, env=ENV)
    assert proc.returncode == 0


def test_rules_dict_form(tmp_path):
    env = write_config(tmp_path, {"rules": IBAN_RULE})
    proc = run_guard(spawn("NL12ABCD3456789012"), env=env)
    assert proc.returncode == 2
