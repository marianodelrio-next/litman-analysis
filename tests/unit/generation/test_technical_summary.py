import json
import copy
from pathlib import Path

from docx import Document
from docx.shared import Cm

from conftest import dossier
from litman_analysis.generation.technical_summary import TechnicalSummaryGenerator
from litman_analysis.generation.technical_summary.renderer import write_technical_summary


def _text(path: Path) -> str:
    doc = Document(path)
    return "\n".join([p.text for p in doc.paragraphs] + [cell.text for table in doc.tables for row in table.rows for cell in row.cells])


def test_technical_summary_contains_dossier_context_and_not_operational_sections(tmp_path: Path) -> None:
    output = tmp_path / "resumen_tecnico.docx"
    write_technical_summary(dossier(), output)
    text = _text(output)
    for value in ("RESUMEN TÉCNICO", "Contexto y situación de partida", "Mejorar la calidad", "Trabajos requeridos", "Plan de trabajo", "Entregables del contrato", "Jefe de proyecto", "Criterios", "CALIDAD DEL ANÁLISIS"):
        assert value in text
    assert "Pendientes para preparar la oferta" not in text
    assert "Documentos que presentar con la oferta" not in text
    assert "None" not in text


def test_technical_summary_rerenders_snapshot_with_its_stable_contract(tmp_path: Path) -> None:
    run = tmp_path / "run"; (run / "input").mkdir(parents=True); (run / "output").mkdir()
    (run / "input" / "dossier.json").write_text(json.dumps(dossier()), encoding="utf-8")
    result = TechnicalSummaryGenerator().rerender(run)
    assert Path(result["documents"][0]).name == "resumen_tecnico.docx"
    assert result["id"] == "technical-summary"
    assert result["generator_version"] == "technical-summary-generator-v2"
    assert result["pending"] == [] and result["metadata"]["format"] == "docx"


def test_technical_summary_keeps_cover_brief_and_detail_complete(tmp_path: Path) -> None:
    objectives = ["Objetivo muy extenso " + str(i) + " " + "x" * 160 for i in range(5)]
    scope = ["Alcance muy extenso " + str(i) + " " + "x" * 160 for i in range(5)]
    requirements = [{"descripcion": "Requisito extenso " + str(i) + " " + "x" * 180, "obligatorio": True} for i in range(5)]
    data = dossier(contexto="Contexto " + "x" * 500, objetivos=objectives, alcance=scope, requisitos_oferta=requirements)
    output = tmp_path / "summary.docx"; write_technical_summary(data, output)
    doc = Document(output); paragraphs = doc.paragraphs
    break_index = next(i for i, p in enumerate(paragraphs) if 'w:type="page"' in p._p.xml)
    cover = "\n".join(p.text for p in paragraphs[:break_index])
    detail = "\n".join(p.text for p in paragraphs[break_index + 1:])
    assert len(cover) < 2000 and cover.count("Objetivo muy extenso") == 3
    assert "Y 2 objetivos adicionales en el detalle." in cover
    assert all(item in detail for item in objectives + scope)


def test_technical_summary_uses_explicit_empty_states_instead_of_fake_cards(tmp_path: Path) -> None:
    output = tmp_path / "empty.docx"
    write_technical_summary(dossier(requisitos_oferta=[], criterios_adjudicacion=[], fases=[], entregables_contrato=[], equipo=[], tecnologias=[]), output)
    text = _text(output)
    assert "No constan requisitos de la oferta." in text
    assert "No constan criterios de adjudicación." in text
    assert "OBLIGATORIEDAD NO INDICADA" not in text


def test_technical_summary_callouts_are_visual_cards_with_textual_labels(tmp_path: Path) -> None:
    output = tmp_path / "card.docx"; write_technical_summary(dossier(), output)
    doc = Document(output)
    card = next(p for p in doc.paragraphs if p.text.startswith("CALIDAD DEL ANÁLISIS:"))
    assert "w:pBdr" in card._p.xml and "w:shd" in card._p.xml
    assert card.paragraph_format.keep_with_next is True
    assert "CALIDAD DEL ANÁLISIS" in card.text


def test_technical_summary_has_accessible_document_structure_and_keeps_input(tmp_path: Path) -> None:
    data = dossier(); original = copy.deepcopy(data)
    output = tmp_path / "structure.docx"; write_technical_summary(data, output)
    doc = Document(output); section = doc.sections[0]
    assert data == original
    tolerance = Cm(.01)
    assert abs(section.page_width - Cm(21)) < tolerance and abs(section.page_height - Cm(29.7)) < tolerance
    assert abs(section.left_margin - Cm(2)) < tolerance and abs(section.right_margin - Cm(2)) < tolerance
    assert doc.styles["Normal"].font.name == "Arial"
    assert sum(p.style.name == "Heading 1" for p in doc.paragraphs) == 1
    assert any(p._p.xpath('.//w:br[@w:type="page"]') for p in doc.paragraphs)
    assert section.header.paragraphs[0].text
    assert section.footer._element.xpath('.//w:fldSimple[contains(@w:instr,"PAGE")]')
    assert all(len(table.columns) <= 4 for table in doc.tables)
    for table in doc.tables:
        assert table.rows[0]._tr.xpath('./w:trPr/w:tblHeader')
        assert all(row._tr.xpath('./w:trPr/w:cantSplit') for row in table.rows)


def test_technical_summary_cover_explains_absent_conditioning_requirements(tmp_path: Path) -> None:
    output = tmp_path / "without-conditioners.docx"
    write_technical_summary(dossier(requisitos_oferta=[{
        "descripcion": "Opcional", "tipo": "técnico", "obligatorio": False,
        "donde_responder": None,
    }]), output)
    assert "No constan requisitos obligatorios o con obligatoriedad pendiente." in _text(output)
