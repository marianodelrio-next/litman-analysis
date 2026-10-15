from __future__ import annotations

from pathlib import Path

import pytest
from fakes import minimal_docx, minimal_pdf

from litman_harness.adapters.documents import DOCX_MIME, PDF_MIME, extract_text
from litman_harness.errors import HarnessError


def test_pdf_text_is_extracted(tmp_path: Path):
    path = tmp_path / "ficha.pdf"
    path.write_bytes(minimal_pdf("Presupuesto base 120000 EUR"))
    assert "Presupuesto base 120000 EUR" in extract_text(path, PDF_MIME)


def test_docx_paragraphs_and_table_cells_are_extracted(tmp_path: Path):
    path = tmp_path / "resumen.docx"
    path.write_bytes(minimal_docx("Objeto: mantenimiento portuario", ("Plazo", "12 meses")))
    assert extract_text(path, DOCX_MIME) == "Objeto: mantenimiento portuario\nPlazo | 12 meses"


def test_other_formats_and_broken_files_are_rejected(tmp_path: Path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a pdf")
    with pytest.raises(HarnessError) as raised:
        extract_text(path, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert raised.value.code == "unsupported_artifact"
    with pytest.raises(HarnessError) as raised:
        extract_text(path, PDF_MIME)
    assert raised.value.code == "unreadable_artifact"
