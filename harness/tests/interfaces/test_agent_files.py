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


def test_prepare_team_skill_references_real_operations_and_installation_commands():
    from litman_harness.interfaces.tools import registry
    prepare_skill = (AGENT / "skills" / "preparar-equipo" / "SKILL.md").read_text(encoding="utf-8")
    assert _frontmatter(AGENT / "skills" / "preparar-equipo" / "SKILL.md")["name"] == "preparar-equipo"
    for operation in ("diagnose", "setup"):
        assert operation in registry() and f"`{operation}`" in prepare_skill
    assert "litman login" in prepare_skill
    assert "litman install --oauth-client" in prepare_skill
    assert "--delete-original" in prepare_skill
    assert "conectar-licitacion" in prepare_skill


def test_workspace_template_mentions_the_litman_binary_placeholder():
    template = (AGENT / "workspace" / "AGENTS.md").read_text(encoding="utf-8")
    assert "{{LITMAN_BIN}}" in template


DOCUMENT_TOOLS = ("read_google_doc", "preview_document_edit", "apply_document_edit", "preview_document_creation",
                  "apply_document_creation")


def test_connect_skill_and_workspace_route_drive_documents_through_litman_tools():
    from litman_harness.interfaces.tools import registry
    connect_skill = (AGENT / "skills" / "conectar-licitacion" / "SKILL.md").read_text(encoding="utf-8")
    workspace = (AGENT / "workspace" / "AGENTS.md").read_text(encoding="utf-8")
    for text in (connect_skill, workspace):
        for operation in DOCUMENT_TOOLS:
            assert operation in registry() and f"`{operation}`" in text
        lowered = text.lower()
        assert "computer use" in lowered and "navegador" in lowered
    assert "vista previa" in connect_skill and "acepte" in connect_skill


def test_prepare_team_skill_covers_the_docs_api_check():
    prepare_skill = (AGENT / "skills" / "preparar-equipo" / "SKILL.md").read_text(encoding="utf-8")
    assert "`docs_api`" in prepare_skill and "Google Docs API" in prepare_skill
    assert "disabled" in prepare_skill and "unknown" in prepare_skill
