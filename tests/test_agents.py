import re
from pathlib import Path

AGENTS = Path(__file__).resolve().parent.parent / "agents"
EXPECTED = {
    "scout": "haiku",
    "extractor": "haiku",
    "mechanic": "sonnet",
    "builder": "sonnet",
    "sage": "fable",
}
FOOTER_KEYS = ["RESULT:", "CHECKS-RUN:", "UNCERTAINTIES:", "ESCALATE:"]


def frontmatter(name):
    text = (AGENTS / f"{name}.md").read_text()
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    assert match, f"{name}.md missing frontmatter"
    fields = dict(
        line.split(":", 1)
        for line in match.group(1).splitlines()
        if ":" in line
    )
    return {k.strip(): v.strip() for k, v in fields.items()}, match.group(2)


def test_all_agents_exist_with_correct_model():
    for name, model in EXPECTED.items():
        fields, _ = frontmatter(name)
        assert fields["name"] == name
        assert fields["model"] == model
        assert len(fields["description"]) > 40


def test_all_agents_carry_footer_contract():
    for name in EXPECTED:
        _, body = frontmatter(name)
        for key in FOOTER_KEYS:
            assert key in body, f"{name}.md body missing {key}"


def test_readonly_agents_cannot_edit():
    for name in ("scout", "extractor"):
        fields, _ = frontmatter(name)
        tools = fields.get("tools", "")
        assert "Edit" not in tools and "Write" not in tools
