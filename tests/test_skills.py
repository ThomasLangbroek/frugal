from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_setup_statusline_skill_is_command_only():
    text = (ROOT / "skills" / "setup-statusline" / "SKILL.md").read_text()
    assert "disable-model-invocation: true" in text
    assert "statusline.py" in text
    assert "consent" in text.lower()


def test_routing_skill_covers_all_agents_and_protocol():
    text = (ROOT / "skills" / "routing" / "SKILL.md").read_text()
    for agent in ("scout", "extractor", "mechanic", "builder", "sage"):
        assert agent in text
    for marker in (
        "[frugal-escalation from",
        "RESULT:",
        "ESCALATE:",
        ".claude/routing-overrides.md",
        "Never delegate",
    ):
        assert marker in text, f"routing skill missing: {marker}"
