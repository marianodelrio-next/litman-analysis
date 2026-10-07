from litman_analysis.infrastructure.documents.normalize import _clean_pdf_text


def test_pdf_cleanup_only_repairs_unambiguous_encoding_and_line_hyphens():
    value = "ISO\u00a027001 vi\u00adgente\nApoyo técnico-\nadministrativo\nim plantará"
    assert _clean_pdf_text(value) == "ISO 27001 vigente\nApoyo técnico-administrativo\nim plantará"
