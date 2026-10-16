from pathlib import Path

from litman_core.domain.jobs import JobType
from litman_core.infrastructure.storage.common import publication_inventory
from litman_core.infrastructure.storage.local import LocalArtifactPublisher, LocalDocumentSource
import litman_core.infrastructure.storage.local as local


def test_local_source_materializes_an_isolated_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"; source.mkdir(); (source / "PCAP.txt").write_text("original")
    job = type("Job", (), {"input_location": str(source), "job_id": "job"})()
    materialized = LocalDocumentSource().materialize(job, tmp_path / "workspace")
    (materialized.directory / "PCAP.txt").write_text("changed")
    assert (source / "PCAP.txt").read_text() == "original"


def test_local_catalog_promotion_replaces_complete_run_only_after_copy(tmp_path: Path) -> None:
    run = tmp_path / "job-20261008T153045.123456Z"; output = run / "output"; output.mkdir(parents=True)
    (output / "ficha_oportunidad.pdf").write_bytes(b"pdf"); (run / "lineage.json").write_text("{}")
    inventory = publication_inventory(run, JobType.ASSESSMENT, False)
    artifacts = LocalArtifactPublisher().publish(run, inventory, include_run_files=False)
    assert [item.name for item in artifacts] == ["ficha_oportunidad.pdf"]
    assert (run / "ficha_oportunidad.pdf").read_bytes() == b"pdf"
    assert not (run / "lineage.json").exists()


def test_full_run_inventory_preserves_relative_tree(tmp_path: Path) -> None:
    run = tmp_path / "run"; (run / "output").mkdir(parents=True); (run / "logs").mkdir()
    (run / "output/ficha_oportunidad.pdf").write_bytes(b"pdf"); (run / "logs/run.log").write_text("log")
    inventory = publication_inventory(run, JobType.ASSESSMENT, True)
    artifacts = LocalArtifactPublisher().publish(run, inventory, include_run_files=True)
    assert {item.name for item in artifacts} == {"output/ficha_oportunidad.pdf", "logs/run.log"}


def test_catalog_cleanup_failure_restores_complete_run(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "run"; output = run / "output"; output.mkdir(parents=True)
    (output / "ficha_oportunidad.pdf").write_bytes(b"pdf"); (run / "lineage.json").write_text("{}")
    inventory = publication_inventory(run, JobType.ASSESSMENT, False)
    real_rmtree = local.shutil.rmtree
    def fail_backup(path, *args, **kwargs):
        if ".complete-" in str(path): raise OSError("cleanup failed")
        return real_rmtree(path, *args, **kwargs)
    monkeypatch.setattr(local.shutil, "rmtree", fail_backup)
    import pytest
    with pytest.raises(OSError): LocalArtifactPublisher().publish(run, inventory, include_run_files=False)
    assert (run / "lineage.json").is_file()


def test_windows_cleanup_retries_readonly_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(local.platform, "system", lambda: "Windows")
    seen = {}

    def fake_rmtree(path, *, onerror):
        seen["path"] = path
        onerror(__import__("os").unlink, str(path / "readonly"), None)

    monkeypatch.setattr(local.shutil, "rmtree", fake_rmtree)
    changed = []
    monkeypatch.setattr(local.os, "chmod", lambda path, mode: changed.append((path, mode)))
    monkeypatch.setattr(local.os, "unlink", lambda path: seen.setdefault("retried", path))
    local._rmtree(tmp_path / "workspace")
    assert seen["path"] == tmp_path / "workspace"
    assert changed and seen["retried"].endswith("readonly")


def test_assessment_catalog_role_is_opportunity_report(tmp_path: Path) -> None:
    run = tmp_path / "run"; output = run / "output"; output.mkdir(parents=True)
    (output / "ficha_oportunidad.pdf").write_bytes(b"pdf")
    inventory = publication_inventory(run, JobType.ASSESSMENT, False)
    assert {item.role for item in inventory} == {"opportunity_report"}


def test_detailed_analysis_catalog_roles(tmp_path: Path) -> None:
    import json

    run = tmp_path / "run"; output = run / "output"; output.mkdir(parents=True)
    for name in ("resumen_tecnico.docx", "guia_preparacion_oferta.docx", "memoria_tecnica.docx", "simulador_economico.xlsx"):
        (output / name).write_bytes(b"x")
    manifest = {"artifacts": [
        {"id": "technical-summary", "documents": ["resumen_tecnico.docx"]},
        {"id": "bid-preparation-guide", "documents": ["guia_preparacion_oferta.docx"]},
        {"id": "technical-document", "documents": ["memoria_tecnica.docx"]},
    ]}
    (output / "generation_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    inventory = publication_inventory(run, JobType.DETAILED_ANALYSIS, False)
    roles = {item.relative_path: item.role for item in inventory}
    assert roles == {
        "resumen_tecnico.docx": "technical_summary",
        "guia_preparacion_oferta.docx": "bid_preparation_guide",
        "memoria_tecnica.docx": "technical_document",
        "simulador_economico.xlsx": "economic_simulator",
    }


def test_full_run_inventory_tags_non_catalog_files_as_run_file(tmp_path: Path) -> None:
    run = tmp_path / "run"; (run / "output").mkdir(parents=True); (run / "logs").mkdir()
    (run / "output/ficha_oportunidad.pdf").write_bytes(b"pdf"); (run / "logs/run.log").write_text("log")
    inventory = publication_inventory(run, JobType.ASSESSMENT, True)
    roles = {item.relative_path: item.role for item in inventory}
    assert roles["output/ficha_oportunidad.pdf"] == "opportunity_report"
    assert roles["logs/run.log"] == "run_file"


def test_detailed_catalog_requires_manifest_declared_technical_document(tmp_path: Path) -> None:
    run = tmp_path / "run"; (run / "output").mkdir(parents=True)
    from litman_core.infrastructure.storage.common import detailed_analysis_delivery_catalog
    import pytest
    with pytest.raises(ValueError, match="generation_manifest.json es obligatorio"):
        detailed_analysis_delivery_catalog(run)
