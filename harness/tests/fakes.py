"""Deterministic Drive, shared-state and Core doubles shared by the harness tests."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib

from litman_harness.dossier.models import ACTION_MARKER, FOLDER_MIME, GOOGLE_DOC_MIME, OPERATION_MARKER, Resource
from litman_harness.errors import HarnessError

PDF = "application/pdf"


class FakeDrive:
    """In-memory Drive: records every access and fails on IDs of other dossiers."""

    def __init__(self, *, user: str = "person-1"):
        self.user = user
        self.resources: dict[str, Resource] = {}
        self.contents: dict[str, bytes] = {}
        self.gets: list[str] = []
        self.listed: list[str] = []
        self.created: list[str] = []
        self.forbidden: set[str] = set()
        self.crash_on_create: set[int] = set()
        self._counter = 0

    def add(self, resource: Resource, content: bytes | None = None) -> Resource:
        if content is not None:
            self.contents[resource.id] = content
            if resource.md5_checksum is None and not resource.mime_type.startswith("application/vnd.google-apps."):
                resource = replace(resource, md5_checksum=hashlib.md5(content).hexdigest())
        self.resources[resource.id] = resource
        return resource

    def about(self):
        return {"user": {"permissionId": self.user, "emailAddress": f"{self.user}@example.test"}}

    def get(self, file_id):
        assert file_id not in self.forbidden, f"acceso fuera del expediente: {file_id}"
        self.gets.append(file_id)
        try:
            return self.resources[file_id]
        except KeyError as exc:
            raise HarnessError("not_found", "No existe el recurso") from exc

    def children(self, folder_id, drive_id):
        assert folder_id not in self.forbidden, f"listado fuera del expediente: {folder_id}"
        self.listed.append(folder_id)
        return [item for item in self.resources.values() if folder_id in item.parents and not item.trashed]

    def find_by_markers(self, parent_id, operation_id, action_id):
        return [item for item in self.children(parent_id, None) if item.has_markers(operation_id, action_id)]

    def download(self, file_id, destination: Path):
        destination.write_bytes(self.contents[file_id])

    def create_folder(self, name, parent_id, operation_id, action_id):
        return self._create(name, FOLDER_MIME, parent_id, operation_id, action_id, None)

    def upload(self, name, parent_id, source, mime_type, operation_id, action_id):
        return self._create(name, mime_type, parent_id, operation_id, action_id, Path(source).read_bytes())

    def upload_converted(self, name, parent_id, source, source_mime_type, operation_id, action_id):
        return self._create(name, GOOGLE_DOC_MIME, parent_id, operation_id, action_id, Path(source).read_bytes())

    def _create(self, name, mime, parent_id, operation_id, action_id, content):
        parent = self.get(parent_id)
        self._counter += 1
        identifier = f"new-{self._counter}"
        self.add(Resource(identifier, name, mime, "1", drive_id=parent.drive_id, parents=(parent_id,),
                          app_properties={OPERATION_MARKER: operation_id, ACTION_MARKER: action_id}), content)
        self.created.append(identifier)
        if len(self.created) in self.crash_on_create:
            raise RuntimeError("timeout simulado tras crear el recurso")
        return self.resources[identifier]

    def write_text(self, file_id: str, content: str) -> None:
        """Simulate an edit made outside LitMan."""
        self.contents[file_id] = content.encode()
        item = self.resources[file_id]
        self.resources[file_id] = replace(item, version=str(int(item.version) + 1),
                                          md5_checksum=hashlib.md5(content.encode()).hexdigest())


class AtomicSharedState:
    """Double of the future atomic Drive capability (create-if-absent and compare-and-swap)."""
    available = True

    def __init__(self, drive: FakeDrive):
        self.drive = drive
        self.writes: list[tuple[str, str]] = []
        self.crash_after_update: set[str] = set()  # file names whose next update "times out" afterwards
        self.race_before_update: set[str] = set()  # file names changed by someone else just before our update

    def create_if_absent(self, name, parent_id, content, operation_id, action_id):
        existing = self.drive.find_by_markers(parent_id, operation_id, action_id)
        if existing:
            return existing[0]
        created = self.drive._create(name, "text/plain", parent_id, operation_id, action_id, content.encode())
        self.writes.append(("create", name))
        return created

    def read(self, file_id):
        return self.drive.contents[file_id].decode(), self.drive.resources[file_id].version

    def update_if_version(self, file_id, content, expected_version, operation_id):
        name = self.drive.resources[file_id].name
        if name in self.race_before_update:
            self.race_before_update.discard(name)
            self.drive.write_text(file_id, self.drive.contents[file_id].decode())
        if self.drive.resources[file_id].version != expected_version:
            raise HarnessError("concurrent_change", "La versión cambió", details={"file_id": file_id})
        self.drive.write_text(file_id, content)
        self.writes.append(("update", name))
        if name in self.crash_after_update:
            self.crash_after_update.discard(name)
            raise RuntimeError("timeout simulado tras actualizar")
        return self.drive.resources[file_id]


def dossier_drive(*, user: str = "person-1") -> FakeDrive:
    """A connected dossier plus a sibling dossier that must never be touched."""
    drive = FakeDrive(user=user)
    drive.add(Resource("root", "Licitación Puerto", FOLDER_MIME, "1", drive_id="shared",
                       capabilities={"canListChildren": True}))
    drive.add(Resource("source", "pliego.pdf", PDF, "4", 123, "shared", ("root",),
                       capabilities={"canDownload": True}), b"pliego")
    drive.add(Resource("offer-doc", "Oferta", GOOGLE_DOC_MIME, "1", drive_id="shared", parents=("root",),
                       capabilities={"canEdit": True}))
    drive.add(Resource("other-root", "Otra licitación", FOLDER_MIME, "1", drive_id="shared"))
    drive.add(Resource("other-file", "pliego.pdf", PDF, "1", drive_id="shared", parents=("other-root",)))
    drive.forbidden = {"other-root", "other-file"}
    return drive


def core_run(job_type: str = "assessment", *, technical: str = "memoria_tecnica.docx", local_path=None,
             tamper=None):
    """Fake ``litman-core`` honouring the public CLI contract with ``include_run_files = false``.

    The run directory holds only the public artifacts, flat, and stdout declares
    them with their SHA-256.  No internal Core file is created, so the harness
    cannot depend on one.  ``tamper(run_dir, payload)`` lets a test break the contract.
    """
    def run(command, **kwargs):
        if command[-1] == "--version":
            return subprocess.CompletedProcess(command, 0, "litman-core 0.1.0\n", "")
        config = tomllib.loads(Path(command[-1]).read_text())
        assert config["publication"]["include_run_files"] is False
        run_dir = Path(config["output"]["directory"]) / "core-run"
        run_dir.mkdir(parents=True)
        names = (["ficha_oportunidad.pdf"] if job_type == "assessment" else
                 ["resumen_tecnico.docx", "guia_preparacion_oferta.docx", "simulador_economico.xlsx", technical])
        artifacts = []
        for name in names:
            (run_dir / name).write_bytes(f"{name} {config['job']['id']}".encode())
            artifacts.append({"name": name, "uri": (run_dir / name).as_uri(),
                              "checksum": hashlib.sha256((run_dir / name).read_bytes()).hexdigest()})
        payload = {"job_id": config["job"]["id"], "publication_id": "pub-1", "status": "succeeded",
                   "local_path": str(local_path or run_dir), "artifacts": artifacts}
        if tamper:
            tamper(run_dir, payload)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
    return run


class HttpResponse:
    def __init__(self, status_code=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status_code, payload or {}, content

    def json(self):
        return self._payload


class FakeDriveHttp:
    """Fake Drive HTTP: v2 ETag metadata, v3 media, v2 If-Match upload and v3 multipart create."""

    def __init__(self, drive: FakeDrive):
        self.drive, self.requests, self.etags = drive, [], {}
        self.on_media = None
        self.status = {}

    def request(self, method, url, params=None, headers=None, data=None):
        self.requests.append((method, url, dict(params or {}), dict(headers or {}), data))
        assert params and params.get("supportsAllDrives") == "true"
        file_id = url.rstrip("/").split("/")[-1]
        if (method, file_id) in self.status:
            return HttpResponse(self.status[(method, file_id)])
        if method == "GET" and "/drive/v2/files/" in url:
            return HttpResponse(payload={"etag": self.etags.setdefault(file_id, '"e1"')})
        if method == "GET" and "/drive/v3/files/" in url:
            if self.on_media:
                self.on_media(file_id)
            return HttpResponse(content=self.drive.contents[file_id])
        if method == "PUT":
            if headers["If-Match"] != self.etags.get(file_id):
                return HttpResponse(412)
            self.drive.write_text(file_id, data.decode())
            self.etags[file_id] = self.etags[file_id] + "+"
            return HttpResponse()
        if method == "POST":
            boundary = headers["Content-Type"].split("boundary=")[1]
            parts = data.decode().split(f"--{boundary}")
            metadata = json.loads(parts[1].split("\r\n\r\n", 1)[1].strip())
            content = parts[2].split("\r\n\r\n", 1)[1][:-2]
            created = self.drive.add(Resource(f"created-{len(self.requests)}", metadata["name"], metadata["mimeType"],
                                              "1", drive_id="shared", parents=tuple(metadata["parents"]),
                                              app_properties=metadata["appProperties"]), content.encode())
            return HttpResponse(payload={"id": created.id})
        raise AssertionError((method, url))


def minimal_pdf(text: str) -> bytes:
    """A tiny valid one-page PDF whose text ``pypdf`` can extract (ASCII text only)."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    output, offsets = bytearray(b"%PDF-1.4\n"), []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(output)
    output += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    output += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    output += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return bytes(output)


def minimal_docx(paragraph: str, cells: tuple[str, str]) -> bytes:
    import io

    from docx import Document
    document = Document()
    document.add_paragraph(paragraph)
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text, table.rows[0].cells[1].text = cells
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
