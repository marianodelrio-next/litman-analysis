import json
from pathlib import Path

from docx import Document

from conftest import dossier
from litman_analysis.generation.bid_preparation_guide import BidPreparationGuideGenerator
from litman_analysis.generation.bid_preparation_guide.renderer import write_bid_preparation_guide


def _text(path: Path) -> str:
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs] + [cell.text for table in doc.tables for row in table.rows for cell in row.cells])


def test_bid_guide_contains_operational_data_nulls_pending_and_evidence(tmp_path: Path) -> None:
    output = tmp_path / "guia.docx"; write_bid_preparation_guide(dossier(), output)
    text = _text(output)
    for value in ("Guía de preparación de la oferta", "Documentos que presentar con la oferta", "Sobre", "Memoria técnica", "Metodología", "No consta", "No incluir precio", "Documento técnico", "Información económica", "Resumen y coordinación", "Generales", "Falta información", "PPT", "Página", "Calidad y limitaciones"):
        assert value in text
    assert "None" not in text and "Entregables del contrato" not in text


def test_bid_guide_uses_suggested_structure_when_imposed_sections_are_absent(tmp_path: Path) -> None:
    data = dossier(memoria_tecnica={"secciones": [], "formato": {}}, estructura_documento_tecnico=["Propuesta sugerida"])
    output = tmp_path / "guide.docx"; write_bid_preparation_guide(data, output)
    text = _text(output)
    assert "Estructura sugerida por el análisis" in text and "Propuesta sugerida" in text


def test_bid_guide_rerenders_snapshot_with_its_stable_contract(tmp_path: Path) -> None:
    run = tmp_path / "run"; (run / "input").mkdir(parents=True); (run / "output").mkdir()
    data = dossier(); (run / "input" / "dossier.json").write_text(json.dumps(data), encoding="utf-8")
    result = BidPreparationGuideGenerator().rerender(run)
    assert Path(result["documents"][0]).name == "guia_preparacion_oferta.docx"
    assert result["id"] == "summary"
    assert result["generator_version"] == "summary-generator-v2"
    assert result["pending"] == data["pendientes"] and result["metadata"]["format"] == "docx"
