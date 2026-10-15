from __future__ import annotations

from pathlib import Path

from fakes import PDF, AtomicSharedState, dossier_drive

from litman_harness.dossier.models import FOLDER_MIME, GOOGLE_DOC_MIME, Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.tree import walk_tree
from litman_harness.plans import PlanStore


def nested_drive():
    drive = dossier_drive()
    drive.resources.pop("source")
    drive.add(Resource("orig", "originales", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    drive.add(Resource("pliego", "pliego.pdf", PDF, "1", drive_id="shared", parents=("orig",)), b"pliego")
    drive.add(Resource("sub", "Anexos", FOLDER_MIME, "1", drive_id="shared", parents=("orig",)))
    drive.add(Resource("anexo", "anexo.pdf", PDF, "1", drive_id="shared", parents=("sub",)), b"anexo")
    drive.add(Resource("oferta-dir", "Oferta", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    drive.add(Resource("borrador", "Borrador", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("oferta-dir",)))
    drive.add(Resource("lit", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
    drive.add(Resource("hidden", "interno.pdf", PDF, "1", drive_id="shared", parents=("lit",)), b"x")
    return drive


def test_tree_walks_subfolders_with_paths_but_not_into_litman():
    drive = nested_drive()
    items, truncated = walk_tree(drive, drive.resources["root"])
    paths = {item.resource.id: item.path for item in items}
    assert truncated is False
    assert paths["anexo"] == "originales/Anexos/anexo.pdf" and paths["borrador"] == "Oferta/Borrador"
    assert "hidden" not in paths and "lit" not in drive.listed
    assert not {"other-root", "other-file"} & set(drive.gets + drive.listed)


def test_tree_is_truncated_at_the_limit():
    drive = nested_drive()
    items, truncated = walk_tree(drive, drive.resources["root"], limit=3)
    assert len(items) == 3 and truncated is True


def test_inspect_lists_nested_originals_and_suggests_existing_folders_without_applying(tmp_path: Path):
    drive = nested_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"))
    result = service.inspect("root")
    candidates = result["candidates"]
    assert candidates["originals"] == ["pliego", "anexo"] and candidates["offer"] == ["offer-doc", "borrador"]
    assert {"id": "sub", "path": "originales/Anexos"} in candidates["folders"]
    assert candidates["suggested_folder_ids"] == {"originals": "orig", "offer": "oferta-dir", "litman": "lit"}
    assert result["tree_truncated"] is False and drive.created == []


def test_suggestions_are_used_only_when_passed_as_folder_ids(tmp_path: Path):
    drive = nested_drive()
    drive.resources.pop("lit")
    drive.resources.pop("hidden")
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"), AtomicSharedState(drive))
    suggested = service.status("root")["candidates"]["suggested_folder_ids"]
    plain = service.preview_incorporation("root", ["pliego"])
    assert not any(a.kind == "register_folder" for a in plain.actions)
    plan = service.preview_incorporation("root", ["pliego", "anexo"], folder_ids=suggested)
    assert sorted(a.resource_id for a in plan.actions if a.kind == "register_folder") == ["oferta-dir", "orig"]
    service.apply_incorporation(plan.id)
    status = service.status("root")
    assert status["state"] == "adopted" and status["candidates"]["suggested_folder_ids"] == {}


def test_files_in_registered_result_folders_are_not_original_candidates(tmp_path: Path):
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / "plans"), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation("root", ["source"]).id)
    initial = next(item for item in drive.resources.values() if item.name == "Analisis inicial")
    drive.add(Resource("ficha", "ficha.pdf", PDF, "1", drive_id="shared", parents=(initial.id,)), b"ficha")
    originals_dir = next(item for item in drive.resources.values() if item.name == "Originales")
    drive.add(Resource("nuevo", "nuevo.pdf", PDF, "1", drive_id="shared", parents=(originals_dir.id,)), b"nuevo")
    assert service.status("root")["candidates"]["originals"] == ["nuevo"]


def test_previous_core_output_folders_are_listed_apart_and_not_used_as_originals(tmp_path: Path):
    drive = dossier_drive()
    marker = {"publication_contract": "detailed-analysis-drive-v1", "job_type": "detailed-analysis",
              "catalog_sha256": "abc"}
    drive.add(Resource("core-dir", "analisis-detallado", FOLDER_MIME, "1", drive_id="shared", parents=("root",),
                       app_properties=marker))
    for identifier, name in (("propuesta", "propuesta_tecnica_base.docx"), ("resumen", "resumen.docx")):
        drive.add(Resource(identifier, name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                           "1", drive_id="shared", parents=("core-dir",)), name.encode())
    drive.add(Resource("ficha", "ficha_oportunidad.pdf", PDF, "1", drive_id="shared", parents=("root",)), b"ficha")
    result = ExpedienteService(drive, PlanStore(tmp_path / "plans")).inspect("root")
    candidates = result["candidates"]
    assert candidates["originals"] == ["ficha", "source"]  # an unmarked loose file is still for the person to decide
    assert candidates["previous_core_outputs"] == [{
        "folder_id": "core-dir", "path": "analisis-detallado", "job_type": "detailed-analysis",
        "files": [{"id": "propuesta", "path": "analisis-detallado/propuesta_tecnica_base.docx"},
                  {"id": "resumen", "path": "analisis-detallado/resumen.docx"}]}]
    reason = "Hay resultados de un análisis anterior de Core; no se usan como pliegos."
    assert {"kind": "review_existing_analysis", "reason": reason} in result["next_actions"]
    assert drive.created == []


def test_litman_folder_is_not_a_folder_candidate(tmp_path: Path):
    drive = nested_drive()
    folders = ExpedienteService(drive, PlanStore(tmp_path / "plans")).inspect("root")["candidates"]["folders"]
    assert "lit" not in [item["id"] for item in folders] and {"id": "orig", "path": "originales"} in folders
