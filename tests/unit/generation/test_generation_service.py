import json
import zipfile
from xml.etree import ElementTree
from pathlib import Path

from docx import Document
from litman_analysis.generation import ARTIFACT_GENERATORS, resolve_artifact_generators
from litman_analysis.generation.service import generate_documents

from conftest import dossier


def test_generation_service_writes_traceable_artifacts(tmp_path: Path) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier(), ensure_ascii=False), encoding="utf-8")
    run_dir = tmp_path / "generation-run"
    manifest = generate_documents(
        dossier_path, output_dir=run_dir, artifacts=["technical-document"], provider=None,
    )
    assert Path(manifest["documents"][0]).exists()
    assert manifest["generation"]["mode"] == "skeleton"
    assert manifest["content_profile"] == "skeleton-v1"
    coverage = json.loads((run_dir / "output" / "coverage.json").read_text(encoding="utf-8"))
    assert not coverage["complete"]
    assert not coverage["sections"][0]["response_complete"]
    generated_content = json.loads((run_dir / "output" / "content.json").read_text(encoding="utf-8"))
    generated_document = Document(run_dir / "output" / "propuesta_tecnica_base.docx")
    assert any(block["type"] == "subheading" for block in generated_content["sections"][0]["blocks"])
    assert any(paragraph.text == "Ejemplo de subapartado" and paragraph.style.name == "Heading 2"
               for paragraph in generated_document.paragraphs)
    with zipfile.ZipFile(run_dir / "output" / "propuesta_tecnica_base.docx") as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    word = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    body_subheading = next(
        paragraph for paragraph in root.iter(word + "p")
        if paragraph.find(f"{word}pPr/{word}pStyle") is not None
        and paragraph.find(f"{word}pPr/{word}pStyle").get(word + "val") == "Heading2"
        and "Ejemplo de subapartado" in "".join(node.text or "" for node in paragraph.iter(word + "t"))
    )
    assert body_subheading.find(f"{word}pPr/{word}numPr/{word}ilvl").get(word + "val") == "1"
    assert body_subheading.find(f"{word}pPr/{word}numPr/{word}numId").get(word + "val") == "2"
    indentation = body_subheading.find(f"{word}pPr/{word}ind")
    assert indentation.get(word + "left") == "1440"
    assert indentation.get(word + "hanging") == "360"
    toc_subheading = next(
        paragraph for paragraph in root.iter(word + "p")
        if paragraph.find(f"{word}pPr/{word}pStyle") is None
        and "1.1. Ejemplo de subapartado" in "".join(node.text or "" for node in paragraph.iter(word + "t"))
    )
    assert any(node.get(word + "val") == "22" for node in toc_subheading.iter(word + "sz"))
    assert any(node.get(word + "val") == "0" for node in toc_subheading.iter(word + "b"))
    assert any(node.get(word + "val") == "F2A900" for node in toc_subheading.iter(word + "color"))
    toc_heading = next(
        paragraph for paragraph in root.iter(word + "p")
        if paragraph.find(f"{word}pPr/{word}pStyle") is None
        and "1. Metodología" in "".join(node.text or "" for node in paragraph.iter(word + "t"))
    )
    assert any(node.get(word + "val") == "4FA6DC" for node in toc_heading.iter(word + "color"))
    body_heading = next(
        paragraph for paragraph in root.iter(word + "p")
        if paragraph.find(f"{word}pPr/{word}pStyle") is not None
        and paragraph.find(f"{word}pPr/{word}pStyle").get(word + "val") == "Heading1"
        and paragraph.text is None
        and "Metodología" in "".join(node.text or "" for node in paragraph.iter(word + "t"))
    )
    assert body_heading.find(f"{word}pPr/{word}numPr/{word}ilvl").get(word + "val") == "0"
    # La fuente Arial del pliego de prueba prevalece sobre Roboto de la plantilla.
    assert any(node.get(word + "ascii") == "Arial" for node in body_heading.iter(word + "rFonts"))
    assert any(node.get(word + "val") == "32" for node in body_heading.iter(word + "sz"))
    assert any(node.get(word + "val") == "4FA6DC" for node in body_heading.iter(word + "color"))
    for relative in (
        "input/document_plan.json", "input/template.yaml", "output/content.json",
        "output/pending.json", "output/coverage.json", "output/validation.json",
        "output/generation_manifest.json", "lineage.json",
    ): 
        assert (run_dir / relative).exists()
def test_artifact_registry_resolves_stable_generators() -> None:
    generators = resolve_artifact_generators(["summary", "technical-document", "economic-simulator"])
    assert [generator.id for generator in generators] == ["summary", "technical-document", "economic-simulator"]
    assert all(generator.version for generator in generators)
    assert set(ARTIFACT_GENERATORS) == {"summary", "technical-document", "economic-simulator"}


def test_unknown_artifact_is_rejected_before_generation(tmp_path: Path) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")
    try:
        generate_documents(dossier_path, output_dir=tmp_path / "run", artifacts=["not-a-document"])
    except ValueError as error:
        assert "desconocido" in str(error)
        assert "not-a-document" in str(error)
    else:
        raise AssertionError("Debe rechazar un artefacto no registrado")


def test_multiple_artifacts_are_consolidated_with_versions(tmp_path: Path) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")
    manifest = generate_documents(dossier_path, output_dir=tmp_path / "run",
                                  artifacts=["summary", "economic-simulator"])
    assert len(manifest["documents"]) == 2
    assert {item["id"] for item in manifest["artifacts"]} == {"summary", "economic-simulator"}
    assert all(item["generator_version"] for item in manifest["artifacts"])
    assert manifest["artifacts"][1]["metadata"]["template_version"] == "1.0.0"


def test_artifact_failure_identifies_generator(tmp_path: Path, monkeypatch) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")

    class BrokenSummary:
        id = "summary"
        version = "test-v1"
        def generate(self, context):
            raise RuntimeError("fallo controlado")
        def rerender(self, run_dir, **options):
            raise RuntimeError("fallo controlado")

    monkeypatch.setitem(ARTIFACT_GENERATORS, "summary", BrokenSummary())
    try:
        generate_documents(dossier_path, output_dir=tmp_path / "run", artifacts=["summary"])
    except ValueError as error:
        assert "summary" in str(error)
        assert "fallo controlado" in str(error)
    else:
        raise AssertionError("Debe identificar el generador que falló")


def test_draft_profile_keeps_previous_deterministic_generation(tmp_path: Path) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier(), ensure_ascii=False), encoding="utf-8")
    manifest = generate_documents(
        dossier_path, output_dir=tmp_path / "generation-run",
        artifacts=["technical-document"], provider=None, content_profile="draft-v1",
    )
    assert manifest["generation"]["mode"] == "deterministic-fallback"
