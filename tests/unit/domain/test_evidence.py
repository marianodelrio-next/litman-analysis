from pathlib import Path

from litman_analysis.domain.validation.evidence import build_evidence_index
from litman_analysis.domain.documents import Document, NormalizedDocument


def test_evidence_is_verified_on_its_declared_page(tmp_path: Path) -> None:
    markdown = tmp_path / "document.md"
    markdown.write_text("<!-- pagina: 1 -->\nimporte 100 euros\n<!-- pagina: 2 -->\nimporte 200 euros", encoding="utf-8")
    document = Document("doc_1", tmp_path / "source.pdf", "source.pdf", "source.pdf", ".pdf", "application/pdf", 1, "x", "ppt", "licitacion", "ready")
    normalized = NormalizedDocument("doc_1", str(markdown), "ready", "pdf_text_by_page", 2, 80, [])
    index = build_evidence_index({"evidencias": [{"campo": "ficha.presupuesto.base_sin_iva", "documento_id": "doc_1", "pagina": 1, "seccion": None, "texto_citado": "importe 100 euros"}]}, [document], [normalized])
    assert index["evidences"][0]["verification"] == "verified"
    assert index["evidences"][0]["verification_method"] == "exact"


def test_evidence_on_wrong_page_is_not_verified(tmp_path: Path) -> None:
    markdown = tmp_path / "document.md"
    markdown.write_text("<!-- pagina: 1 -->\nimporte 100 euros\n<!-- pagina: 2 -->\nimporte 200 euros", encoding="utf-8")
    document = Document("doc_1", tmp_path / "source.pdf", "source.pdf", "source.pdf", ".pdf", "application/pdf", 1, "x", "ppt", "licitacion", "ready")
    normalized = NormalizedDocument("doc_1", str(markdown), "ready", "pdf_text_by_page", 2, 80, [])
    index = build_evidence_index({"evidencias": [{"campo": "ficha.presupuesto.base_sin_iva", "documento_id": "doc_1", "pagina": 2, "seccion": None, "texto_citado": "importe 100 euros"}]}, [document], [normalized])
    assert index["evidences"][0]["verification"] == "quote_not_found"


def test_nonexistent_document_is_not_verified(tmp_path: Path) -> None:
    index = build_evidence_index({"evidencias": [{"campo": "ficha", "documento_id": "missing", "pagina": 1,
                                                    "texto_citado": "texto"}]}, [], [])
    assert index["evidences"][0]["verification"] == "missing_document"


def test_quote_not_found_is_not_verified(tmp_path: Path) -> None:
    markdown = tmp_path / "document.md"
    markdown.write_text("<!-- pagina: 1 -->\nimporte 100 euros", encoding="utf-8")
    document = Document("doc_1", tmp_path / "source.pdf", "source.pdf", "source.pdf", ".pdf", "application/pdf", 1, "x", "ppt", "licitacion", "ready")
    normalized = NormalizedDocument("doc_1", str(markdown), "ready", "pdf_text_by_page", 1, 80, [])
    index = build_evidence_index({"evidencias": [{"campo": "ficha", "documento_id": "doc_1", "pagina": 1,
                                                    "texto_citado": "importe 200 euros"}]}, [document], [normalized])
    assert index["evidences"][0]["verification"] == "quote_not_found"


def test_pdf_layout_spaces_are_tolerated_but_paraphrases_are_not(tmp_path: Path) -> None:
    markdown = tmp_path / "document.md"
    markdown.write_text(
        "<!-- pagina: 1 -->\nLas pro posiciones se presentarán. "
        "El Adjudicatario im plantará medidas. "
        "Al menos y una vez el valor anual.", encoding="utf-8")
    document = Document("doc_1", tmp_path / "source.pdf", "source.pdf", "source.pdf", ".pdf",
                        "application/pdf", 1, "x", "ppt", "licitacion", "ready")
    normalized = NormalizedDocument("doc_1", str(markdown), "ready", "pdf_text_by_page", 1, 120, [])
    data = {"evidencias": [
        {"campo":"fecha", "documento_id":"doc_1", "pagina":1,
         "texto_citado":"Las proposiciones se presentarán."},
        {"campo":"ens", "documento_id":"doc_1", "pagina":1,
         "texto_citado":"El Adjudicatario implantará medidas."},
        {"campo":"solvencia", "documento_id":"doc_1", "pagina":1,
         "texto_citado":"Al menos de una vez el valor anual."},
    ]}
    entries = {item["field"]: item for item in build_evidence_index(data, [document], [normalized])["evidences"]}
    assert entries["fecha"]["verification_method"] == "layout_whitespace"
    assert entries["ens"]["verification_method"] == "layout_whitespace"
    assert entries["solvencia"]["verification"] == "quote_not_found"
