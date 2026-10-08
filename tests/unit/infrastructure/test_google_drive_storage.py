from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pytest

from litman_analysis.domain.jobs import JobRequest, JobType, StorageKind
from litman_analysis.infrastructure.storage.google_drive import GoogleDriveArtifactPublisher, GoogleDriveDocumentSource
from litman_analysis.infrastructure.storage.common import detailed_analysis_delivery_catalog

class Request:
    def __init__(self, value): self.value = value
    def execute(self):
        if isinstance(self.value, Exception): raise self.value
        return self.value

class Files:
    def __init__(self, folder=None, pages=None):
        self.folder = folder or {"id":"source-folder", "name":"source", "mimeType":"application/vnd.google-apps.folder", "trashed":False}
        self.pages = pages or {None:{"files":[]}}; self.calls=[]; self.created=[]; self.deleted=[]; self.updated=[]
    def get(self, **kwargs): self.calls.append(("get",kwargs)); return Request(self.folder)
    def get_media(self, **kwargs): self.calls.append(("media",kwargs)); return kwargs
    def list(self, **kwargs): self.calls.append(("list",kwargs)); return Request(self.pages.get(kwargs.get("pageToken"), {"files":[]}))
    def create(self, **kwargs): self.created.append(kwargs); return Request({"id":f"id-{len(self.created)}", "webViewLink":"https://drive/example"})
    def update(self, **kwargs): self.updated.append(kwargs); return Request({"id":kwargs["fileId"]})
    def delete(self, **kwargs): self.deleted.append(kwargs); return Request({})
class Service:
    def __init__(self, folder=None, pages=None): self.files_api=Files(folder,pages)
    def files(self): return self.files_api

def job(output=StorageKind.LOCAL, job_type=JobType.ASSESSMENT):
    return JobRequest("job", job_type, StorageKind.GOOGLE_DRIVE, output, "source-folder", "destination-folder")
def downloader(payload=b"data"):
    def write(_request, stream): stream.write(payload)
    return write
def file(id, name, mime="application/pdf", size="4"): return {"id":id,"name":name,"mimeType":mime,"size":size,"parents":["source-folder"]}

def test_list_downloads_pages_deterministically_and_uses_drive_options(tmp_path):
    service=Service({"id":"source-folder","mimeType":"application/vnd.google-apps.folder","trashed":False,"driveId":"shared"}, {None:{"files":[file("b","B.pdf")],"nextPageToken":"next"}, "next":{"files":[file("a","a.pdf")]}})
    result=GoogleDriveDocumentSource(service, downloader=downloader()).materialize(job(), tmp_path)
    assert {p.name for p in result.directory.iterdir()} == {"a.pdf", "B.pdf"}
    lists=[c[1] for c in service.files_api.calls if c[0]=="list"]
    assert lists[0]["q"] == "'source-folder' in parents and trashed = false"
    assert lists[0]["pageToken"] is None and lists[1]["pageToken"] == "next"
    assert lists[0]["corpora"] == "drive" and lists[0]["driveId"] == "shared"
    assert all(c["supportsAllDrives"] and c["includeItemsFromAllDrives"] for c in lists)
    assert [c[1]["fileId"] for c in service.files_api.calls if c[0]=="media"] == ["a","b"]

def test_my_drive_uses_user_corpus(tmp_path):
    service=Service(pages={None:{"files":[file("a","a.pdf")]}})
    GoogleDriveDocumentSource(service, downloader=downloader()).materialize(job(), tmp_path)
    assert next(c[1] for c in service.files_api.calls if c[0]=="list")["corpora"] == "user"

@pytest.mark.parametrize("folder,pages,message", [
 ({"mimeType":"application/pdf","trashed":False},{None:{"files":[]}},"debe ser una carpeta"),
 ({"mimeType":"application/vnd.google-apps.folder","trashed":True},{None:{"files":[]}},"papelera"),
 ({"mimeType":"application/vnd.google-apps.folder","trashed":False},{None:{"files":[]}},"no contiene archivos"),
])
def test_folder_validation(tmp_path, folder, pages, message):
    with pytest.raises(ValueError, match=message): GoogleDriveDocumentSource(Service(folder,pages),downloader=downloader()).materialize(job(),tmp_path)

@pytest.mark.parametrize("item,message", [
 (file("x","sub","application/vnd.google-apps.folder"),"subcarpeta"),
 (file("x","link","application/vnd.google-apps.shortcut"),"acceso directo"),
 (file("x","doc","application/vnd.google-apps.document"),"nativo"),
 (file("x","../bad.pdf"),"inválido"),
])
def test_rejects_unsupported_children(tmp_path,item,message):
    with pytest.raises(ValueError,match=message): GoogleDriveDocumentSource(Service(pages={None:{"files":[item]}}),downloader=downloader()).materialize(job(),tmp_path)

def test_rejects_repeated_token_collisions_declared_and_actual_size(tmp_path):
    repeated=Service(pages={None:{"files":[file("a","a.pdf")],"nextPageToken":"x"},"x":{"files":[],"nextPageToken":"x"}})
    with pytest.raises(ValueError,match="token"): GoogleDriveDocumentSource(repeated,downloader=downloader()).materialize(job(),tmp_path)
    collision=Service(pages={None:{"files":[file("a","same.pdf"),file("b","same.pdf")]}})
    with pytest.raises(ValueError,match="colisionan"): GoogleDriveDocumentSource(collision,downloader=downloader()).materialize(job(),tmp_path)
    actual=Service(pages={None:{"files":[file("a","a.pdf",size=None)]}})
    with pytest.raises(ValueError,match="tamaño"): GoogleDriveDocumentSource(actual,max_file_mb=0,downloader=downloader(b"data")).materialize(job(),tmp_path)
    assert not (tmp_path/"case").exists()

def test_incomplete_search_and_download_failure_clean_case(tmp_path):
    with pytest.raises(ValueError,match="incompleta"): GoogleDriveDocumentSource(Service(pages={None:{"files":[],"incompleteSearch":True}}),downloader=downloader()).materialize(job(),tmp_path)
    def broken(_request, stream): stream.write(b"partial"); raise RuntimeError("boom")
    with pytest.raises(RuntimeError): GoogleDriveDocumentSource(Service(pages={None:{"files":[file("a","a.pdf")]}}),downloader=broken).materialize(job(),tmp_path)
    assert not (tmp_path/"case").exists()

DELIVERABLES = ("resumen_tecnico.docx", "guia_preparacion_oferta.docx", "propuesta_tecnica_base.docx", "simulador_economico.xlsx")

class DeliveryFiles(Files):
    def __init__(self):
        super().__init__(); self.items={}; self.next_id=0; self.fail_name=None; self.race=None; self.final_lookups=0
    def _add(self, name, parent, data=b"", mime="application/octet-stream", props=None, item_id=None):
        item_id=item_id or f"item-{len(self.items)+1}"; self.items[item_id]={"id":item_id,"name":name,"parents":[parent],"mimeType":mime,"appProperties":props or {},"data":data,"webViewLink":f"drive://{item_id}"}; return item_id
    def list(self, **kwargs):
        self.calls.append(("list",kwargs)); q=kwargs["q"]
        if "name = 'job'" in q: self.final_lookups += 1
        values=[v for v in self.items.values() if ("name = 'job'" not in q or v["name"] == "job")]
        quoted=q.split("'")
        parent=(quoted[3] if q.startswith("name =") else quoted[1]) if " in parents" in q else None
        if parent: values=[v for v in values if parent in v["parents"]]
        if self.race and self.final_lookups == 2: self.race()
        return Request({"files":[{k:v for k,v in item.items() if k != "data"} for item in values]})
    def get_media(self, **kwargs): return kwargs
    def create(self, **kwargs):
        self.created.append(kwargs); body=kwargs["body"]
        if body["name"] == self.fail_name: return FailingRequest()
        self.next_id += 1; item_id=f"id-{self.next_id}"; data=Path(kwargs["media_body"]).read_bytes() if kwargs.get("media_body") else b""
        self._add(body["name"], body["parents"][0], data, body.get("mimeType", "application/octet-stream"), body.get("appProperties"), item_id)
        return Request({"id":item_id,"webViewLink":f"drive://{item_id}"})
    def update(self, **kwargs):
        self.updated.append(kwargs); self.items[kwargs["fileId"]]["name"]=kwargs["body"]["name"]; return Request({"id":kwargs["fileId"]})
    def delete(self, **kwargs):
        self.deleted.append(kwargs); target=kwargs["fileId"]
        self.items.pop(target, None)
        for item_id in [key for key, item in self.items.items() if target in item["parents"]]: self.items.pop(item_id)
        return Request({})

class DeliveryService:
    def __init__(self, files): self.files_api=files
    def files(self): return self.files_api

ExistingService = DeliveryService

class FailingRequest:
    def execute(self): raise RuntimeError("simulated")

def delivery_run(tmp_path):
    run=tmp_path/"run"; output=run/"output"; output.mkdir(parents=True)
    for name in DELIVERABLES: (output/name).write_bytes(name.encode())
    (output/"generation_manifest.json").write_text(json.dumps({"artifacts":[{"id":"technical-summary","documents":[str(output/"resumen_tecnico.docx")]},{"id":"summary","documents":[str(output/"guia_preparacion_oferta.docx")]},{"id":"technical-document","documents":[str(output/"propuesta_tecnica_base.docx")]}]}))
    (run/"lineage.json").write_text("{}")
    (run/"logs").mkdir(); (run/"logs/x.log").write_text("x")
    return run


def test_delivery_catalog_rejects_malformed_generation_manifest(tmp_path):
    run = delivery_run(tmp_path)
    (run / "output/generation_manifest.json").write_text('{"artifacts":["invalid"]}')
    with pytest.raises(ValueError, match="artefactos inválidos"):
        detailed_analysis_delivery_catalog(run)

def delivery_downloader(files):
    def write(request, stream): stream.write(files.items[request["fileId"]]["data"])
    return write

def test_detailed_analysis_publishes_expected_flat_catalog(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path)
    result=GoogleDriveArtifactPublisher(DeliveryService(files),temporary_suffix=lambda:"fixed",uploader=lambda p:str(p)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)
    assert [item.name for item in result] == list(DELIVERABLES)
    uploads=[call["body"] for call in files.created if call["body"].get("mimeType") != "application/vnd.google-apps.folder"]
    assert {item["name"] for item in uploads} == set(DELIVERABLES)
    assert all("output/" not in item["name"] for item in uploads)
    assert all(not item["name"].endswith(".json") for item in uploads)
    assert all(item.name in DELIVERABLES and item.checksum == hashlib.sha256(item.name.encode()).hexdigest() for item in result)

def test_detailed_analysis_requires_all_documents_before_temporary_folder(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path); (run/"output"/DELIVERABLES[0]).unlink()
    with pytest.raises(ValueError, match="artefacto de entrega requerido"):
        GoogleDriveArtifactPublisher(DeliveryService(files)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)
    assert files.created == []

def test_existing_compatible_delivery_is_reused(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path)
    catalog=__import__("litman_analysis.infrastructure.storage.common",fromlist=["detailed_analysis_delivery_catalog"]).detailed_analysis_delivery_catalog(run)
    props=GoogleDriveArtifactPublisher._folder_properties(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),catalog)
    final=files._add("job","destination-folder",mime="application/vnd.google-apps.folder",props=props)
    for item in catalog: files._add(item.name,final,item.source.read_bytes())
    result=GoogleDriveArtifactPublisher(DeliveryService(files),downloader=delivery_downloader(files)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)
    assert len(result) == 4 and files.created == []

def test_existing_v1_delivery_is_not_reused_as_v2(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path)
    catalog=detailed_analysis_delivery_catalog(run)
    props=GoogleDriveArtifactPublisher._folder_properties(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),catalog)
    props["publication_contract"]="detailed-analysis-drive-v1"
    final=files._add("job","destination-folder",mime="application/vnd.google-apps.folder",props=props)
    for item in catalog: files._add(item.name,final,item.source.read_bytes())
    with pytest.raises(FileExistsError, match="no coincide"):
        GoogleDriveArtifactPublisher(DeliveryService(files),downloader=delivery_downloader(files)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)

@pytest.mark.parametrize("mutation", ["metadata", "missing", "duplicate", "extra"])
def test_existing_incompatible_delivery_fails_without_overwrite(tmp_path, mutation):
    files=DeliveryFiles(); run=delivery_run(tmp_path); catalog=__import__("litman_analysis.infrastructure.storage.common",fromlist=["detailed_analysis_delivery_catalog"]).detailed_analysis_delivery_catalog(run)
    props=GoogleDriveArtifactPublisher._folder_properties(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),catalog)
    if mutation == "metadata": props["job_id"]="other"
    final=files._add("job","destination-folder",mime="application/vnd.google-apps.folder",props=props)
    for item in catalog: files._add(item.name,final,item.source.read_bytes())
    if mutation == "missing": files.items.pop(next(key for key, value in files.items.items() if value["name"] == DELIVERABLES[0]))
    if mutation == "duplicate": files._add(DELIVERABLES[0],final,b"duplicate")
    if mutation == "extra": files._add("extra.txt",final,b"extra")
    with pytest.raises(FileExistsError): GoogleDriveArtifactPublisher(DeliveryService(files),downloader=delivery_downloader(files)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)
    assert files.created == [] and files.updated == []

def test_upload_failure_cleans_temporary_folder(tmp_path):
    files=DeliveryFiles(); files.fail_name=DELIVERABLES[1]
    with pytest.raises(RuntimeError): GoogleDriveArtifactPublisher(DeliveryService(files),uploader=lambda p:str(p)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),delivery_run(tmp_path))
    assert files.deleted and not files.items

def test_compatible_concurrent_delivery_is_reused_and_temporary_is_removed(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path)
    catalog=__import__("litman_analysis.infrastructure.storage.common",fromlist=["detailed_analysis_delivery_catalog"]).detailed_analysis_delivery_catalog(run)
    request=job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS)
    def winner():
        final=files._add("job","destination-folder",mime="application/vnd.google-apps.folder",props=GoogleDriveArtifactPublisher._folder_properties(request,catalog))
        for item in catalog: files._add(item.name,final,item.source.read_bytes())
    files.race=winner
    result=GoogleDriveArtifactPublisher(DeliveryService(files),temporary_suffix=lambda:"x",uploader=lambda p:str(p),downloader=delivery_downloader(files)).publish(request,run)
    assert len(result) == 4 and files.deleted
    assert len([item for item in files.items.values() if item["name"] == "job"]) == 1

def test_incompatible_concurrent_delivery_fails_and_temporary_is_removed(tmp_path):
    files=DeliveryFiles(); run=delivery_run(tmp_path)
    def winner(): files._add("job","destination-folder",mime="application/vnd.google-apps.folder",props={"job_id":"other"})
    files.race=winner
    with pytest.raises(FileExistsError):
        GoogleDriveArtifactPublisher(DeliveryService(files),temporary_suffix=lambda:"x",uploader=lambda p:str(p),downloader=delivery_downloader(files)).publish(job(StorageKind.GOOGLE_DRIVE, JobType.DETAILED_ANALYSIS),run)
    assert files.deleted


def assessment_run(tmp_path, payload=b"pdf"):
    run = tmp_path / "assessment-run"
    (run / "output").mkdir(parents=True, exist_ok=True)
    (run / "output/ficha_oportunidad.pdf").write_bytes(payload)
    (run / "output/result.json").write_text("{}")
    (run / "output/ficha_oportunidad.html").write_text("technical")
    return run


def test_assessment_creates_job_folder_containing_only_pdf(tmp_path):
    files = DeliveryFiles()
    result = GoogleDriveArtifactPublisher(DeliveryService(files), temporary_suffix=lambda: "fixed",
                                          uploader=lambda path: str(path)).publish(
        job(StorageKind.GOOGLE_DRIVE), assessment_run(tmp_path)
    )
    assert [item.name for item in result] == ["ficha_oportunidad.pdf"]
    final = [item for item in files.items.values() if item["name"] == "job"]
    assert len(final) == 1
    children = [item for item in files.items.values() if final[0]["id"] in item["parents"]]
    assert [item["name"] for item in children] == ["ficha_oportunidad.pdf"]
    assert all(item["name"] != "publication-manifest.json" for item in files.items.values())
    assert files.updated


def test_assessment_reuses_one_identical_pdf(tmp_path):
    files = DeliveryFiles()
    folder = files._add("job", "destination-folder", mime="application/vnd.google-apps.folder")
    files._add("ficha_oportunidad.pdf", folder, b"same", item_id="pdf-id")
    publisher = GoogleDriveArtifactPublisher(DeliveryService(files), downloader=delivery_downloader(files))
    result = publisher.publish(job(StorageKind.GOOGLE_DRIVE), assessment_run(tmp_path, b"same"))
    assert result[0].name == "ficha_oportunidad.pdf"
    assert result[0].uri == "drive://pdf-id"
    assert files.created == []


def test_assessment_rejects_different_or_duplicate_pdf(tmp_path):
    different = DeliveryFiles()
    folder = different._add("job", "destination-folder", mime="application/vnd.google-apps.folder")
    different._add("ficha_oportunidad.pdf", folder, b"other")
    with pytest.raises(FileExistsError, match="contenido diferente"):
        GoogleDriveArtifactPublisher(DeliveryService(different), downloader=delivery_downloader(different)).publish(
            job(StorageKind.GOOGLE_DRIVE), assessment_run(tmp_path, b"local")
        )
    duplicates = DeliveryFiles()
    duplicates._add("job", "destination-folder", mime="application/vnd.google-apps.folder")
    duplicates._add("job", "destination-folder", mime="application/vnd.google-apps.folder")
    with pytest.raises(FileExistsError, match="más de una carpeta"):
        GoogleDriveArtifactPublisher(DeliveryService(duplicates)).publish(
            job(StorageKind.GOOGLE_DRIVE), assessment_run(tmp_path, b"local")
        )


def test_assessment_rejects_existing_job_folder_with_extra_files(tmp_path):
    files = DeliveryFiles()
    folder = files._add("job", "destination-folder", mime="application/vnd.google-apps.folder")
    files._add("ficha_oportunidad.pdf", folder, b"same")
    files._add("result.json", folder, b"{}")
    with pytest.raises(FileExistsError, match="únicamente ficha_oportunidad.pdf"):
        GoogleDriveArtifactPublisher(DeliveryService(files)).publish(
            job(StorageKind.GOOGLE_DRIVE), assessment_run(tmp_path, b"same")
        )


def test_assessment_requires_pdf_before_drive_publication(tmp_path):
    run = tmp_path / "run"
    (run / "output").mkdir(parents=True)
    with pytest.raises(ValueError, match="No existe el PDF"):
        GoogleDriveArtifactPublisher(Service()).publish(job(StorageKind.GOOGLE_DRIVE), run)
