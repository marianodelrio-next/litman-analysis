from pathlib import Path

from litman_core.infrastructure.documents.inventory import inventory


def test_inventory_is_stable_and_ignores_case_metadata(tmp_path: Path) -> None:
    (tmp_path / "PCAP.pdf").write_bytes(b"pdf-content")
    (tmp_path / "caso.yaml").write_text("validado: false", encoding="utf-8")
    first, second = inventory(tmp_path), inventory(tmp_path)
    assert len(first) == 1
    assert first[0].document_id == second[0].document_id
    assert first[0].type_hint == "pcap"
    assert first[0].phase_hint == "licitacion"
