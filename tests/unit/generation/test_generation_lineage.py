import json
from pathlib import Path

from litman_core.generation.service import generate_documents
from litman_core.infrastructure.runs import dossier_lineage

from conftest import dossier


def test_generation_uses_explicit_dossier_lineage_and_propagates_it(tmp_path: Path) -> None:
    case = tmp_path / "un-caso-con-nombre-libre"
    source_run = tmp_path / "any-storage" / "run-a2"
    dossier_path = source_run / "payload" / "source.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")
    (source_run / "lineage.json").write_text(json.dumps(dossier_lineage(
        stage="detailed-analysis", run_dir=source_run, dossier_path=dossier_path, case_dir=case,
        origin="explicit")), encoding="utf-8")

    run_dir = tmp_path / "generated"
    manifest = generate_documents(dossier_path, output_dir=run_dir, artifacts=["summary"])

    assert manifest["lineage"]["dossier"]["stage"] == "detailed-analysis"
    assert manifest["lineage"]["dossier"]["run"]["path"] == str(source_run)
    assert manifest["lineage"]["input_snapshot_sha256"] == manifest["lineage"]["dossier"]["sha256"]
    assert json.loads((run_dir / "lineage.json").read_text()) == manifest["lineage"]



def test_generation_accepts_external_dossier(tmp_path: Path) -> None:
    dossier_path = tmp_path / "imported" / "dossier.json"
    dossier_path.parent.mkdir()
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")

    manifest = generate_documents(dossier_path, output_dir=tmp_path / "generated", artifacts=["summary"])

    assert manifest["lineage"]["dossier"]["stage"] == "external"
    assert manifest["lineage"]["dossier"]["origin"] == "external"
    assert manifest["source_run"] is None


def test_generation_rejects_incorrect_declared_dossier_hash(tmp_path: Path) -> None:
    case = tmp_path / "case"
    source_run = tmp_path / "source-run"
    dossier_path = source_run / "dossier.json"
    source_run.mkdir()
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")
    lineage = dossier_lineage(stage="detailed-analysis", run_dir=source_run, dossier_path=dossier_path,
                              case_dir=case, origin="explicit")
    lineage["dossier"]["sha256"] = "0" * 64
    (source_run / "lineage.json").write_text(json.dumps(lineage), encoding="utf-8")

    try:
        generate_documents(dossier_path, output_dir=tmp_path / "generated", artifacts=["summary"])
    except ValueError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("Debe rechazar un hash de dossier discrepante")


def test_generation_ignores_lineage_from_unrelated_ancestor(tmp_path: Path) -> None:
    dossier_path = tmp_path / "foreign" / "payload" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier()), encoding="utf-8")
    (tmp_path / "lineage.json").write_text(json.dumps({"dossier": {
        "file": str(tmp_path / "other.json"), "sha256": "0" * 64,
    }}), encoding="utf-8")

    manifest = generate_documents(dossier_path, output_dir=tmp_path / "generated", artifacts=["summary"])

    assert manifest["lineage"]["dossier"]["origin"] == "external"
