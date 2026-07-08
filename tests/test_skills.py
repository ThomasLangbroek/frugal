from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
