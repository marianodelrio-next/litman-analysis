from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from fakes import AtomicSharedState, core_run, dossier_drive, minimal_docx, minimal_pdf

from litman_harness.analysis.service import AnalysisService
from litman_harness.dossier.context import render_context
from litman_harness.dossier.manifest import Manifest
from litman_harness.dossier.publication import PublicationService
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.summary import CONTENT_NOTE, SummaryService
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


class Setup:
    def __init__(self, tmp_path: Path, *, publish: bool = True):
        self.tmp_path = tmp_path
        self.drive = dossier_drive()
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.summary = SummaryService(self.dossier)
        plan = self.dossier.preview_incorporation("root", ["source"])
        self.dossier.apply_incorporation(plan.id)
        self.artifacts: dict[str, str] = {}
        self.publication_results: list[dict] = []
        if publish:
            self.publish("detailed-analysis")

    def publish(self, job_type: str) -> dict:
        analysis = AnalysisService(self.drive, self.store, work_root=self.tmp_path / "work", run=core_run(job_type),
                                   settings=lambda: {"provider": "codex"})
        executed = analysis.execute(analysis.preview("root", ["source"], job_type).id)
        publication = PublicationService(self.dossier, self.tmp_path / "work")
        result = publication.apply(publication.preview(executed["operation_id"]).id)
        self.artifacts.update({item["name"]: item["file_id"] for item in result["artifacts"]})
        self.publication_results.append(result)
        return result

    def items(self) -> list[dict]:
        ficha_source = self.artifacts["resumen_tecnico.docx"]
        return [{"key": "fecha_limite", "value": "2026-11-01", "source_file_id": "source"},
                {"key": "objeto", "value": " Mantenimiento portuario ", "source_file_id": ficha_source},
                {"key": "presupuesto", "value": "377.474,79 EUR sin IVA", "source_file_id": "source"},
                {"key": "organismo", "value": "Autoridad Portuaria", "source_file_id": ficha_source},
                {"key": "lotes", "value": "No consta"}]

    def manifest(self) -> Manifest:
        resource = next(item for item in self.drive.resources.values() if item.name == "manifest.json")
        return Manifest.parse(self.drive.contents[resource.id].decode())

    def context(self) -> str:
        return self.drive.contents[self.manifest().context_file_id].decode()

    def accept(self, items=None) -> dict:
        return self.summary.apply(self.summary.preview("root", items or self.items()).id)


# -- read_document ---------------------------------------------------------------------------------

def test_read_document_reads_originals_and_artifacts_without_writing(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.contents["source"] = minimal_pdf("Pliego de condiciones")
    docx_id = setup.artifacts["resumen_tecnico.docx"]
    setup.drive.contents[docx_id] = minimal_docx("Objeto: mantenimiento", ("Plazo", "12 meses"))
    created, writes = list(setup.drive.created), list(setup.state.writes)
    original = setup.summary.read_document("root", "source")
    assert original["kind"] == "original" and "Pliego de condiciones" in original["text"]
    artifact = setup.summary.read_document("root", docx_id)
    assert artifact["kind"] == "artifact" and artifact["role"] == "technical_summary"
    assert artifact["text"] == "Objeto: mantenimiento\nPlazo | 12 meses" and artifact["next_offset"] is None
    assert artifact["note"] == CONTENT_NOTE and "no instrucciones" in CONTENT_NOTE and artifact["writes"] is False
    assert setup.drive.created == created and setup.state.writes == writes


def test_copied_original_keeps_the_source_id_citable_and_readable(tmp_path: Path):
    setup = Setup(tmp_path)
    resource = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    manifest = setup.manifest()
    manifest.originals[0].pop("placement")  # registered before placement existed
    setup.drive.write_text(resource.id, manifest.serialize())
    setup.drive.add(replace(setup.drive.resources["source"], capabilities={"canDownload": True, "canCopy": True}))
    setup.dossier.apply_incorporation(setup.dossier.preview_incorporation("root").id)
    copy_id = setup.manifest().originals[0]["file_id"]
    assert copy_id != "source"
    for file_id in ("source", copy_id):
        setup.drive.contents[file_id] = minimal_pdf("Pliego de condiciones")
        document = setup.summary.read_document("root", file_id)
        assert document["kind"] == "original" and "Pliego de condiciones" in document["text"]
    assert setup.accept()["status"] == "succeeded"
    assert {item.get("source_file_id") for item in setup.manifest().summary["items"]} >= {"source"}


def test_read_document_rejects_unregistered_outside_and_unsupported(tmp_path: Path):
    setup = Setup(tmp_path)
    for file_id, code in (("offer-doc", "document_not_registered"), ("other-file", "document_not_registered"),
                          (setup.artifacts["simulador_economico.xlsx"], "unsupported_document")):
        with pytest.raises(HarnessError) as raised:
            setup.summary.read_document("root", file_id)
        assert raised.value.code == code
    setup.drive.add(replace(setup.drive.resources["source"], parents=("elsewhere",)))
    with pytest.raises(HarnessError) as raised:
        setup.summary.read_document("root", "source")
    assert raised.value.code == "document_outside_tree"


def test_read_document_pages_with_next_offset(tmp_path: Path, monkeypatch):
    from litman_harness.dossier import summary
    setup = Setup(tmp_path)
    docx_id = setup.artifacts["resumen_tecnico.docx"]
    setup.drive.contents[docx_id] = minimal_docx("abcdefghij", ("k", "l"))  # "abcdefghij\nk | l"
    monkeypatch.setattr(summary, "PAGE_SIZE", 6)
    first = setup.summary.read_document("root", docx_id)
    assert (first["text"], first["offset"], first["next_offset"], first["characters"]) == ("abcdef", 0, 6, 16)
    pages = [first["text"]]
    offset = first["next_offset"]
    while offset is not None:
        page = setup.summary.read_document("root", docx_id, offset)
        pages.append(page["text"])
        offset = page["next_offset"]
    assert "".join(pages) == "abcdefghij\nk | l"


# -- preview_summary -------------------------------------------------------------------------------

def _without(items, key):
    return [item for item in items if item["key"] != key]


@pytest.mark.parametrize(("change", "code"), (
    (lambda items: items + [{"key": "color", "value": "x", "source_file_id": "source"}], "invalid_summary_key"),
    (lambda items: items + [dict(items[0])], "invalid_summary_key"),
    (lambda items: _without(items, "presupuesto"), "invalid_summary_key"),
    (lambda items: [{**items[0], "value": "x" * 301}] + items[1:], "invalid_summary"),
    (lambda items: [{**items[0], "value": "dos\nlíneas"}] + items[1:], "invalid_summary"),
    (lambda items: [{**items[0], "value": "  "}] + items[1:], "invalid_summary"),
    (lambda items: [{**items[0], "extra": "x"}] + items[1:], "invalid_summary"),
    (lambda items: [{"key": "fecha_limite", "value": "2026-11-01"}] + items[1:], "invalid_summary_source"),
    (lambda items: [{**items[0], "source_file_id": "other-file"}] + items[1:], "invalid_summary_source"),
    (lambda items: [{**items[0], "source_file_id": "offer-doc"}] + items[1:], "invalid_summary_source"),
    (lambda items: [], "invalid_summary"),
))
def test_preview_validates_keys_values_and_one_source_per_line(tmp_path: Path, change, code):
    setup = Setup(tmp_path)
    with pytest.raises(HarnessError) as raised:
        setup.summary.preview("root", change(setup.items()))
    assert raised.value.code == code


def test_preview_orders_keys_writes_nothing_and_requires_published_analyses(tmp_path: Path):
    with pytest.raises(HarnessError) as raised:
        Setup(tmp_path / "empty", publish=False).summary.preview("root", [])
    assert raised.value.code == "no_published_analysis"
    setup = Setup(tmp_path)
    writes = list(setup.state.writes)
    plan = setup.summary.preview("root", setup.items())
    assert [a.kind for a in plan.actions] == ["set_summary", "update_context", "update_manifest"]
    change = plan.actions[0].metadata
    assert [item["key"] for item in change["items"]] == ["objeto", "organismo", "presupuesto", "fecha_limite",
                                                          "lotes"]
    assert change["items"][0]["value"] == "Mantenimiento portuario" and "source_file_id" not in change["items"][-1]
    assert change["previous_summary"] is None and change["based_on_analyses"] == setup.manifest().published_analyses()
    assert setup.state.writes == writes


# -- apply_summary and context ---------------------------------------------------------------------

def test_apply_summary_stores_it_at_dossier_level_and_renders_it_first(tmp_path: Path):
    setup = Setup(tmp_path)
    assert setup.publication_results[0]["recommended_action"]["kind"] == "propose_summary"
    result = setup.accept()
    assert result["status"] == "succeeded" and result["context_conflict"] is None
    assert result["recommended_action"] is None  # detailed analysis published and summarised: the person decides
    summary = setup.manifest().summary
    assert summary["accepted_by"] == "person-1@example.test" and summary["origin"] == "assistant_proposal_accepted"
    assert summary["based_on_analyses"] == setup.manifest().published_analyses()
    assert setup.manifest().history[-1]["kind"] == "summary"
    context = setup.context()
    assert context.index("## Resumen") < context.index("## Carpetas") < context.index("## Resultados")
    ficha = setup.artifacts["resumen_tecnico.docx"]
    assert (f"- Objeto: Mantenimiento portuario ([fuente](https://drive.google.com/open?id={ficha}))\n"
            f"- Organismo: Autoridad Portuaria ([fuente](https://drive.google.com/open?id={ficha}))\n"
            "- Presupuesto: 377.474,79 EUR sin IVA ([fuente](https://drive.google.com/open?id=source))\n"
            "- Fecha límite de presentación: 2026-11-01 ([fuente](https://drive.google.com/open?id=source))\n"
            "- Lotes: No consta\n"
            "- Propuesto por el asistente y aceptado por person-1@example.test") in context
    assert render_context(setup.manifest(), "Licitación Puerto") == context  # another installation reproduces it


def test_context_without_summary_says_it_is_pending(tmp_path: Path):
    setup = Setup(tmp_path)
    assert "## Resumen\n- Resumen pendiente de proponer." in setup.context()


def test_summary_is_suggested_after_publication_and_refreshed_after_a_new_analysis(tmp_path: Path):
    setup = Setup(tmp_path)
    assert [a["kind"] for a in setup.publication_results[0]["next_actions"]] == ["propose_summary"]
    assert "propose_summary" in [a["kind"] for a in setup.dossier.status("root")["next_actions"]]
    setup.accept()
    kinds = [a["kind"] for a in setup.dossier.status("root")["next_actions"]]
    assert "propose_summary" not in kinds and "refresh_summary" not in kinds
    result = setup.publish("assessment")
    assert [a["kind"] for a in result["next_actions"]] == ["refresh_summary"]
    assert "refresh_summary" in [a["kind"] for a in setup.dossier.status("root")["next_actions"]]


def test_a_previous_summary_is_replaced_and_shown_in_the_preview(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.accept()
    items = [{**item, "value": "Servicio revisado"} if item["key"] == "objeto" else item for item in setup.items()]
    plan = setup.summary.preview("root", items)
    assert plan.actions[0].metadata["previous_summary"]["items"][0]["value"] == "Mantenimiento portuario"
    setup.summary.apply(plan.id)
    assert "Servicio revisado" in setup.context() and "Mantenimiento portuario" not in setup.context()


def test_manifest_changed_since_preview_is_a_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    plan = setup.summary.preview("root", setup.items())
    resource = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    manifest = setup.manifest()
    manifest.workflow_phase = "entregada"
    setup.drive.write_text(resource.id, manifest.serialize())
    assert setup.summary.apply(plan.id)["status"] == "conflict"
    assert setup.manifest().summary is None


def test_context_edited_outside_litman_reports_context_conflict(tmp_path: Path):
    setup = Setup(tmp_path)
    context_id = setup.manifest().context_file_id
    setup.drive.write_text(context_id, "# notas propias\n")
    result = setup.accept()
    assert result["status"] == "succeeded" and result["context_conflict"]["reason"] == "edited_outside_litman"
    assert setup.manifest().summary is not None and setup.drive.contents[context_id] == b"# notas propias\n"


def test_manifest_rejects_a_malformed_summary(tmp_path: Path):
    setup = Setup(tmp_path)
    manifest = setup.manifest()
    manifest.summary = {"items": [{"key": "color", "value": "x"}], "based_on_analyses": []}
    with pytest.raises(HarnessError) as raised:
        manifest.json()
    assert raised.value.code == "invalid_manifest"
