from __future__ import annotations

from dataclasses import replace
import io
from pathlib import Path

import pytest
from fakes import AtomicSharedState, FakeDocs, FakeSheets, dossier_drive, minimal_docx, minimal_pdf

from litman_harness.adapters.documents import DOCX_MIME
from litman_harness.dossier import files as files_module
from litman_harness.dossier.documents import CONTENT_NOTE, DocumentService
from litman_harness.dossier.files import FileService, file_kind
from litman_harness.dossier.models import (FOLDER_MIME, GOOGLE_DOC_MIME, GOOGLE_SHEET_MIME, GOOGLE_SLIDES_MIME,
                                           XLSX_MIME, Resource)
from litman_harness.dossier.service import ExpedienteService
from litman_harness.dossier.summary import PAGE_SIZE
from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore


def workbook(sheets: dict[str, list[list]]) -> bytes:
    from openpyxl import Workbook
    book = Workbook()
    book.remove(book.active)
    for title, rows in sheets.items():
        sheet = book.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


class Setup:
    def __init__(self, tmp_path: Path, *, adopt: bool = False):
        self.drive = dossier_drive()
        add = self.drive.add
        add(Resource("sub", "Oferta económica", FOLDER_MIME, "1", drive_id="shared", parents=("root",),
                     capabilities={"canListChildren": True}))
        add(Resource("deep", "Anexos", FOLDER_MIME, "1", drive_id="shared", parents=("sub",)))
        add(Resource("deep-pdf", "Memoria Técnica.pdf", "application/pdf", "1", 40, "shared", ("deep",),
                     capabilities={"canDownload": True, "canEdit": False, "canRename": True, "canTrash": True,
                                   "canComment": True, "canCopy": True, "canMoveItemWithinDrive": True},
                     web_view_link="https://drive.example/deep-pdf", modified_time="2026-10-01T10:00:00.000Z"),
            minimal_pdf("Memoria tecnica"))
        add(Resource("notes", "notas.md", "application/octet-stream", "1", 9, "shared", ("sub",)),
            "# Notas\ncafé".encode())
        add(Resource("data-csv", "precios.csv", "text/csv", "1", 7, "shared", ("sub",)), b"a,b\n1,2\n")
        add(Resource("costs", "Costes.xlsx", XLSX_MIME, "1", 100, "shared", ("sub",)),
            workbook({"Costes": [["Concepto", "Importe"], [None, None], ["Grúas", 1200.0]], "Notas": [["ok"]]}))
        add(Resource("memo-docx", "memoria.docx", DOCX_MIME, "1", 50, "shared", ("sub",)),
            minimal_docx("Memoria técnica", ("Lote 1", "Grúas")))
        add(Resource("sheet", "Presupuesto", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("sub",),
                     capabilities={"canEdit": True}))
        add(Resource("slides", "Presentación", GOOGLE_SLIDES_MIME, "1", drive_id="shared", parents=("sub",)))
        add(Resource("zip", "datos.zip", "application/zip", "1", 5, "shared", ("sub",)), b"zip")
        add(Resource("doc", "Memoria", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("sub",),
                     capabilities={"canEdit": True}))
        add(Resource("elsewhere", "Otra carpeta", FOLDER_MIME, "1", drive_id="shared"))
        add(Resource("loose", "suelto.pdf", "application/pdf", "1", 5, "shared", ("elsewhere",)), b"x")
        self.docs = FakeDocs()
        self.docs.add("doc", ["Primera línea", "Segunda línea"])
        self.sheets = FakeSheets()
        self.sheets.add("sheet", {"Hoja 1": [["Concepto", "Importe"], [], ["Grúas", "1.200,00 €"]],
                                  "O'Brien": [["x"]]})
        self.drive.exports[("slides", "text/plain")] = "Diapositiva 1\nObjetivos".encode()
        self.store = PlanStore(tmp_path / "plans")
        self.state = AtomicSharedState(self.drive)
        self.dossier = ExpedienteService(self.drive, self.store, self.state)
        self.files = FileService(self.dossier, DocumentService(self.dossier, self.docs), self.sheets)
        if adopt:
            self.dossier.apply_incorporation(self.dossier.preview_incorporation("root", ["source"]).id)
        else:
            add(Resource("litman", "_LitMan", FOLDER_MIME, "1", drive_id="shared", parents=("root",)))
            add(Resource("litman-sheet", "Interno", GOOGLE_SHEET_MIME, "1", drive_id="shared", parents=("litman",)))
            add(Resource("litman-sub", "Borradores", FOLDER_MIME, "1", drive_id="shared", parents=("litman",)))


def error(call) -> HarnessError:
    with pytest.raises(HarnessError) as raised:
        call()
    return raised.value


def by_id(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items}


# -- list_folder -----------------------------------------------------------------------------------

def test_list_folder_lists_the_root_with_kinds_and_never_litman(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.files.list_folder("root")
    assert result["writes"] is False and result["parent_folder_id"] == "root"
    items = by_id(result["items"])
    assert set(items) == {"source", "offer-doc", "sub"}
    assert items["source"] == {"id": "source", "name": "pliego.pdf", "mime_type": "application/pdf", "kind": "pdf",
                               "size": 123, "modified_time": None, "web_view_link": None, "role": None}
    assert items["sub"]["kind"] == "folder" and items["offer-doc"]["kind"] == "google_doc"
    assert items["offer-doc"]["size"] is None
    assert "litman" not in items and "_LitMan" not in {item["name"] for item in result["items"]}


def test_list_folder_describes_each_kind_in_a_subfolder_with_modified_time(tmp_path: Path):
    setup = Setup(tmp_path)
    kinds = {item["id"]: item["kind"] for item in setup.files.list_folder("root", "sub")["items"]}
    assert kinds == {"deep": "folder", "notes": "text", "data-csv": "text", "costs": "xlsx", "memo-docx": "docx",
                     "sheet": "google_sheet", "slides": "google_slides", "zip": "other", "doc": "google_doc"}
    deep = by_id(setup.files.list_folder("root", "deep")["items"])["deep-pdf"]
    assert deep["modified_time"] == "2026-10-01T10:00:00.000Z" and deep["web_view_link"].endswith("deep-pdf")
    assert deep["size"] == 40


def test_list_folder_gives_the_role_of_each_item_of_an_adopted_dossier(tmp_path: Path):
    setup = Setup(tmp_path, adopt=True)
    roles = {item["name"]: item["role"] for item in setup.files.list_folder("root")["items"]}
    assert roles["pliego.pdf"] == "original" and roles["contexto.md"] == "context"
    assert roles["Originales"] == "folder:originals" and roles["Oferta"] in ("folder:offer", None)
    assert roles["Oferta económica"] is None
    assert "_LitMan" not in roles


def test_list_folder_roles_cover_live_offer_analysis_folders_and_artifacts(tmp_path: Path):
    setup = Setup(tmp_path, adopt=True)
    manifest = next(item for item in setup.drive.resources.values() if item.name == "manifest.json")
    from litman_harness.dossier.manifest import Manifest
    data = Manifest.parse(setup.drive.contents[manifest.id].decode())
    data.live_offer = {"document_id": "offer-doc", "origin_kind": "existing_external"}
    data.analyses = [{"operation_id": "op-1", "status": "published", "folder_id": "sub",
                      "artifacts": [{"file_id": "memo-docx", "role": "technical_summary"}]}]
    setup.drive.write_text(manifest.id, data.serialize())
    roles = {item["id"]: item["role"] for item in setup.files.list_folder("root")["items"]}
    assert roles["offer-doc"] == "live_offer" and roles["sub"] == "analysis_folder"
    assert by_id(setup.files.list_folder("root", "sub")["items"])["memo-docx"]["role"] == "artifact"


def test_list_folder_rejects_litman_below_it_outside_and_files_as_invalid_parent(tmp_path: Path):
    setup = Setup(tmp_path)
    for folder in ("litman", "litman-sub", "elsewhere", "source"):
        raised = error(lambda folder=folder: setup.files.list_folder("root", folder))
        assert raised.code == "invalid_parent", folder
    assert "litman-sub" not in setup.drive.listed and "litman" not in setup.drive.listed


# -- search_in_dossier -----------------------------------------------------------------------------

def test_search_matches_names_ignoring_case_and_accents_and_reports_the_path(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.files.search_in_dossier("root", "MEMORIA tecnica")
    assert [(item["id"], item["path"]) for item in result["items"]] == [
        ("deep-pdf", "Oferta económica/Anexos/Memoria Técnica.pdf")]
    assert result["truncated"] is False and result["writes"] is False
    assert {item["id"] for item in setup.files.search_in_dossier("root", "oferta")["items"]} == {
        "sub", "offer-doc"}
    assert [item["id"] for item in setup.files.search_in_dossier("root", "Memoria", kind="docx")["items"]] == [
        "memo-docx"]


def test_search_never_returns_or_enters_litman(tmp_path: Path):
    setup = Setup(tmp_path)
    for query in ("interno", "borradores", "litman"):
        assert setup.files.search_in_dossier("root", query)["items"] == []
    assert "litman-sub" not in setup.drive.listed


def test_search_is_capped_at_fifty_items_and_validates_arguments(tmp_path: Path):
    setup = Setup(tmp_path)
    for number in range(60):
        setup.drive.add(Resource(f"bulk-{number}", f"anexo {number:02}.pdf", "application/pdf", "1", 1, "shared",
                                 ("deep",)), b"x")
    result = setup.files.search_in_dossier("root", "anexo", kind="pdf")
    assert len(result["items"]) == 50 and result["truncated"] is True
    assert error(lambda: setup.files.search_in_dossier("root", "   ")).code == "invalid_request"
    assert error(lambda: setup.files.search_in_dossier("root", "x", kind="video")).code == "invalid_request"


def test_search_reports_truncation_when_the_tree_walk_is_truncated(tmp_path: Path, monkeypatch):
    setup = Setup(tmp_path)
    monkeypatch.setattr(files_module, "walk_tree", lambda drive, root: ([], True))
    assert setup.files.search_in_dossier("root", "x") == {"folder_id": "root", "query": "x", "items": [],
                                                           "truncated": True, "writes": False}


# -- get_file_info ---------------------------------------------------------------------------------

def test_get_file_info_adds_the_path_and_the_permissions_of_the_account(tmp_path: Path):
    setup = Setup(tmp_path)
    info = setup.files.get_file_info("root", "deep-pdf")
    assert info["path"] == "Oferta económica/Anexos/Memoria Técnica.pdf" and info["kind"] == "pdf"
    assert {key: info[key] for key in ("can_edit", "can_rename", "can_move", "can_trash", "can_copy",
                                      "can_download", "can_comment")} == {
        "can_edit": False, "can_rename": True, "can_move": True, "can_trash": True, "can_copy": True,
        "can_download": True, "can_comment": True}
    assert info["modified_time"] == "2026-10-01T10:00:00.000Z" and info["role"] is None
    missing = setup.files.get_file_info("root", "source")
    assert missing["path"] == "pliego.pdf" and missing["can_rename"] is False and missing["can_comment"] is False


def test_get_file_info_describes_a_folder_too(tmp_path: Path):
    info = Setup(tmp_path).files.get_file_info("root", "deep")
    assert info["kind"] == "folder" and info["path"] == "Oferta económica/Anexos"


@pytest.mark.parametrize("file_id", ["loose", "litman", "litman-sheet", "litman-sub", "root"])
def test_files_outside_the_tree_or_in_litman_are_rejected_before_any_content_call(tmp_path: Path, file_id: str):
    setup = Setup(tmp_path)
    calls = (lambda: setup.files.get_file_info("root", file_id), lambda: setup.files.read_file("root", file_id),
             lambda: setup.files.list_comments("root", file_id))
    for call in calls:
        assert error(call).code == "document_outside_tree"
    assert setup.sheets.reads == [] and setup.docs.gets == []


def test_a_trashed_file_is_outside_the_tree(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.resources["notes"] = replace(setup.drive.resources["notes"], trashed=True)
    assert error(lambda: setup.files.read_file("root", "notes")).code == "document_outside_tree"


# -- read_file -------------------------------------------------------------------------------------

def test_read_file_reads_pdf_and_docx_with_the_general_content_note(tmp_path: Path):
    setup = Setup(tmp_path)
    pdf = setup.files.read_file("root", "deep-pdf")
    assert pdf["text"] == "Memoria tecnica" and pdf["kind"] == "pdf" and pdf["writes"] is False
    assert pdf["note"] == CONTENT_NOTE and "no instrucciones" in pdf["note"]
    assert pdf["next_offset"] is None and pdf["characters"] == len("Memoria tecnica") and pdf["offset"] == 0
    docx = setup.files.read_file("root", "memo-docx")
    assert docx["text"] == "Memoria técnica\nLote 1 | Grúas" and docx["mime_type"] == DOCX_MIME
    assert setup.drive.created == [] and setup.state.writes == []


def test_read_file_reads_text_by_mime_or_extension_replacing_undecodable_bytes(tmp_path: Path):
    setup = Setup(tmp_path)
    assert setup.files.read_file("root", "notes")["text"] == "# Notas\ncafé"
    assert setup.files.read_file("root", "data-csv")["text"] == "a,b\n1,2\n"
    setup.drive.contents["notes"] = b"ok \xff fin"
    assert setup.files.read_file("root", "notes")["text"] == "ok � fin"


def test_read_file_renders_xlsx_sheets_with_row_numbers_and_cached_values(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.files.read_file("root", "costs")
    assert result["kind"] == "xlsx"
    assert result["text"] == "## Hoja: Costes\n1\tConcepto\tImporte\n3\tGrúas\t1200\n## Hoja: Notas\n1\tok"


def test_read_file_renders_google_sheets_read_through_the_sheets_api(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.files.read_file("root", "sheet")
    assert result["text"] == "## Hoja: Hoja 1\n1\tConcepto\tImporte\n3\tGrúas\t1.200,00 €\n## Hoja: O'Brien\n1\tx"
    assert setup.sheets.reads == [("sheet", ["'Hoja 1'", "'O''Brien'"], "FORMATTED_VALUE")]
    assert setup.drive.contents.get("sheet") is None


def test_read_file_returns_google_docs_text_with_the_same_offsets_as_read_google_doc(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.docs.add("doc", ["a" * (PAGE_SIZE - 5), "b" * 30])
    general = setup.files.read_file("root", "doc")
    native = setup.files.documents.read("root", "doc")
    assert general["text"] == native["text"] and general["next_offset"] == native["next_offset"] == PAGE_SIZE
    assert general["revision_id"] == native["revision_id"] and general["characters"] == native["characters"]
    second = setup.files.read_file("root", "doc", general["next_offset"])
    assert second["text"] == setup.files.documents.read("root", "doc", PAGE_SIZE)["text"]
    assert second["kind"] == "google_doc" and second["note"] == CONTENT_NOTE and second["next_offset"] is None


def test_read_file_reads_google_slides_through_a_text_export(tmp_path: Path):
    setup = Setup(tmp_path)
    result = setup.files.read_file("root", "slides")
    assert result["text"] == "Diapositiva 1\nObjetivos" and result["kind"] == "google_slides"


def test_read_file_pages_20000_characters_and_validates_the_offset(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.contents["notes"] = ("x" * 25_000).encode()
    first = setup.files.read_file("root", "notes")
    assert len(first["text"]) == PAGE_SIZE == 20_000 and first["next_offset"] == 20_000
    second = setup.files.read_file("root", "notes", first["next_offset"])
    assert len(second["text"]) == 5_000 and second["next_offset"] is None and second["characters"] == 25_000
    for offset in (-1, True, "1"):
        assert error(lambda offset=offset: setup.files.read_file("root", "notes", offset)).code == "invalid_request"


@pytest.mark.parametrize("file_id", ["deep", "zip"])
def test_read_file_rejects_folders_and_unsupported_types(tmp_path: Path, file_id: str):
    setup = Setup(tmp_path)
    raised = error(lambda: setup.files.read_file("root", file_id))
    assert raised.code == "unsupported_document"


def test_read_file_rejects_files_over_30_mb_before_downloading(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.resources["memo-docx"] = replace(setup.drive.resources["memo-docx"], size=30 * 1024 * 1024 + 1)
    setup.drive.contents.pop("memo-docx")  # a download would raise KeyError
    assert error(lambda: setup.files.read_file("root", "memo-docx")).code == "file_too_large"
    setup.drive.resources["memo-docx"] = replace(setup.drive.resources["memo-docx"], size=30 * 1024 * 1024)
    setup.drive.contents["memo-docx"] = minimal_docx("ok", ("a", "b"))
    assert setup.files.read_file("root", "memo-docx")["text"].startswith("ok")


def test_read_file_rejects_google_sheets_over_200000_cells_before_reading_values(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.sheets.grids[("sheet", "Hoja 1")] = (1000, 150)
    setup.sheets.grids[("sheet", "O'Brien")] = (1000, 51)
    assert error(lambda: setup.files.read_file("root", "sheet")).code == "file_too_large"
    assert setup.sheets.reads == []
    setup.sheets.grids[("sheet", "O'Brien")] = (1000, 50)
    assert setup.files.read_file("root", "sheet")["text"].startswith("## Hoja: Hoja 1")


def test_read_file_counts_xlsx_cells_while_iterating(tmp_path: Path, monkeypatch):
    setup = Setup(tmp_path)
    monkeypatch.setattr(files_module, "MAX_CELLS", 5)
    assert error(lambda: setup.files.read_file("root", "costs")).code == "file_too_large"
    monkeypatch.setattr(files_module, "MAX_CELLS", 100)
    assert setup.files.read_file("root", "costs")["characters"] > 0


def test_read_file_reports_a_corrupt_xlsx_as_unreadable(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.contents["costs"] = b"not a workbook"
    assert error(lambda: setup.files.read_file("root", "costs")).code == "unreadable_document"


def test_read_file_does_not_change_read_document(tmp_path: Path):
    setup = Setup(tmp_path, adopt=True)
    from litman_harness.dossier.summary import SummaryService
    setup.drive.contents["source"] = minimal_pdf("Pliego")
    assert error(lambda: SummaryService(setup.dossier).read_document("root", "notes")).code == "document_not_registered"
    assert SummaryService(setup.dossier).read_document("root", "source")["text"] == "Pliego"


# -- list_comments ---------------------------------------------------------------------------------

def thread(identifier: str, content: str, *, resolved: bool = False, replies=(), quoted: str | None = None) -> dict:
    raw = {"id": identifier, "content": content, "author": {"displayName": "Ana", "me": False},
           "createdTime": "2026-10-02T09:00:00.000Z", "resolved": resolved, "replies": list(replies)}
    if quoted:
        raw["quotedFileContent"] = {"value": quoted}
    return raw


def test_list_comments_returns_open_comments_with_replies_and_the_content_note(tmp_path: Path):
    setup = Setup(tmp_path)
    reply = {"id": "r1", "content": "Hecho", "author": {"displayName": "Luis", "me": True},
             "createdTime": "2026-10-03T09:00:00.000Z", "action": "resolve"}
    gone = {"id": "r2", "content": "borrado", "createdTime": "2026-10-03T10:00:00.000Z", "deleted": True}
    setup.drive.comment_threads["doc"] = [thread("c1", "Revisar plazo", replies=(reply, gone), quoted="12 meses"),
                                          thread("c2", "Cerrado", resolved=True)]
    result = setup.files.list_comments("root", "doc")
    assert result["comments"] == [{
        "id": "c1", "content": "Revisar plazo", "author": "Ana", "created_time": "2026-10-02T09:00:00.000Z",
        "resolved": False, "quoted_text": "12 meses",
        "replies": [{"id": "r1", "content": "Hecho", "author": "Luis", "created_time": "2026-10-03T09:00:00.000Z",
                     "action": "resolve"}]}]
    assert result["note"] == CONTENT_NOTE and result["writes"] is False and result["include_resolved"] is False


def test_list_comments_includes_resolved_comments_only_when_asked(tmp_path: Path):
    setup = Setup(tmp_path)
    setup.drive.comment_threads["doc"] = [thread("c1", "Abierto"), thread("c2", "Cerrado", resolved=True)]
    ids = [item["id"] for item in setup.files.list_comments("root", "doc", include_resolved=True)["comments"]]
    assert ids == ["c1", "c2"]
    assert [item["id"] for item in setup.files.list_comments("root", "doc", False)["comments"]] == ["c1"]
    assert setup.files.list_comments("root", "notes")["comments"] == []


def test_list_comments_rejects_folders(tmp_path: Path):
    assert error(lambda: Setup(tmp_path).files.list_comments("root", "sub")).code == "unsupported_document"


# -- helpers ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("name, mime, kind", [
    ("a.pdf", "application/pdf", "pdf"), ("a", GOOGLE_DOC_MIME, "google_doc"), ("a", GOOGLE_SHEET_MIME, "google_sheet"),
    ("a", GOOGLE_SLIDES_MIME, "google_slides"), ("a", FOLDER_MIME, "folder"), ("a.xlsx", XLSX_MIME, "xlsx"),
    ("a", "text/markdown", "text"), ("a", "text/x-markdown", "text"), ("a", "text/plain", "text"),
    ("A.TXT", "application/octet-stream", "text"), ("a.csv", "application/vnd.ms-excel", "text"),
    ("a.bin", "application/octet-stream", "other"), ("a.html", "text/html", "other")])
def test_file_kind(name: str, mime: str, kind: str):
    assert file_kind(Resource("x", name, mime)) == kind
