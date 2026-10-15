from __future__ import annotations

from pathlib import Path
import tomllib

AGENT = Path(__file__).parents[2] / "agent"
READ_ONLY_TOOLS = {"mcp__litman__status", "mcp__litman__read_document"}


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    header = text.split("---\n", 2)[1]
    return dict(line.split(": ", 1) for line in header.strip().splitlines())


def test_claude_reader_subagent_uses_the_cheapest_model_and_only_read_tools():
    meta = _frontmatter(AGENT / "claude" / "agents" / "lector-licitacion.md")
    assert meta["name"] == "lector-licitacion" and meta["model"] == "haiku"
    assert {tool.strip() for tool in meta["tools"].split(",")} == READ_ONLY_TOOLS


def test_codex_reader_subagent_is_small_low_effort_and_read_only():
    config = tomllib.loads((AGENT / "codex" / "agents" / "lector-licitacion.toml").read_text(encoding="utf-8"))
    assert config["name"] == "lector-licitacion" and config["model"] == "gpt-5.6-luna"
    assert config["model_reasoning_effort"] == "low" and config["sandbox_mode"] == "read-only"
    assert "status" in config["developer_instructions"] and "read_document" in config["developer_instructions"]


def test_skills_reference_real_operations():
    from litman_harness.interfaces.tools import registry
    summary_skill = (AGENT / "skills" / "resumir-licitacion" / "SKILL.md").read_text(encoding="utf-8")
    connect_skill = (AGENT / "skills" / "conectar-licitacion" / "SKILL.md").read_text(encoding="utf-8")
    assert _frontmatter(AGENT / "skills" / "resumir-licitacion" / "SKILL.md")["name"] == "resumir-licitacion"
    for operation in ("read_document", "preview_summary", "apply_summary", "status"):
        assert operation in registry() and f"`{operation}" in summary_skill
    assert "lector-licitacion" in summary_skill and "resumir-licitacion" in connect_skill
    assert "recommended_action" in connect_skill and "recommended_action" in summary_skill
    for operation in ("identity", "status", "apply_incorporation", "execute_analysis", "apply_publication",
                      "apply_summary", "discard_analysis", "recover", "preview_incorporation"):
        assert operation in registry() and f"`{operation}`" in connect_skill
    assert "read_published_artifact" not in summary_skill + connect_skill
