"""Deterministic Drive, shared-state and Core doubles shared by the harness tests."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
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
        self.move_denied: set[str] = set()  # file IDs whose move Drive rejects with 403
        self.moved: list[str] = []
        self.exports: dict[tuple[str, str], bytes] = {}  # (file ID, MIME type) → exported bytes
        self.comment_threads: dict[str, list[dict]] = {}  # file ID → comments as Drive returns them
        self.docs: FakeDocs | None = None  # when set, every created Google Doc also exists there, empty
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

    def create_document(self, name, parent_id, operation_id, action_id):
        return self._create(name, GOOGLE_DOC_MIME, parent_id, operation_id, action_id, None)

    def move(self, file_id, add_parent, remove_parents):
        if file_id in self.move_denied:
            raise HarnessError("insufficient_permission", "Drive rechazó el movimiento", details={"http_status": 403})
        item = self.get(file_id)
        parents = tuple(parent for parent in item.parents if parent not in remove_parents)
        self.resources[file_id] = replace(item, parents=(*parents, add_parent))
        self.moved.append(file_id)
        return self.resources[file_id]

    def copy(self, file_id, name, parent_id, operation_id, action_id):
        source = self.get(file_id)
        return self._create(name, source.mime_type, parent_id, operation_id, action_id, self.contents[file_id])

    def upload(self, name, parent_id, source, mime_type, operation_id, action_id):
        return self._create(name, mime_type, parent_id, operation_id, action_id, Path(source).read_bytes())

    def upload_converted(self, name, parent_id, source, source_mime_type, operation_id, action_id):
        return self._create(name, GOOGLE_DOC_MIME, parent_id, operation_id, action_id, Path(source).read_bytes())

    def export(self, file_id, mime_type, destination: Path):
        destination.write_bytes(self.exports[(file_id, mime_type)])

    def comments(self, file_id):
        return list(self.comment_threads.get(file_id, []))

    def _create(self, name, mime, parent_id, operation_id, action_id, content):
        parent = self.get(parent_id)
        self._counter += 1
        identifier = f"new-{self._counter}"
        self.add(Resource(identifier, name, mime, "1", drive_id=parent.drive_id, parents=(parent_id,),
                          app_properties={OPERATION_MARKER: operation_id, ACTION_MARKER: action_id}), content)
        self.created.append(identifier)
        if mime == GOOGLE_DOC_MIME and self.docs is not None:
            self.docs.add(identifier, [""])
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


_ROLES_BY_NAME = {"ficha_oportunidad.pdf": "opportunity_report", "resumen_tecnico.docx": "technical_summary",
                  "guia_preparacion_oferta.docx": "bid_preparation_guide",
                  "simulador_economico.xlsx": "economic_simulator"}


def core_run(job_type: str = "assessment", *, technical: str = "memoria_tecnica.docx", local_path=None,
             tamper=None):
    """Fake ``litman-core`` honouring the public CLI contract with ``include_run_files = false``.

    The run directory holds only the public artifacts, flat, and stdout declares
    them with their SHA-256 and role.  No internal Core file is created, so the
    harness cannot depend on one.  ``tamper(run_dir, payload)`` lets a test break
    the contract.
    """
    def run(command, **kwargs):
        if command[-1] == "info":
            return subprocess.CompletedProcess(command, 0, json.dumps(
                {"contract": 1, "version": "0.1.0", "providers": ["claude-code", "codex"]}), "")
        config = tomllib.loads(Path(command[-1]).read_text())
        assert "publication" not in config
        assert "id" not in config["job"]
        assert "kind" not in config["input"]
        job_id = Path(config["input"]["location"]).name
        run_dir = Path(config["output"]["directory"]) / "core-run"
        run_dir.mkdir(parents=True)
        names = (["ficha_oportunidad.pdf"] if job_type == "assessment" else
                 ["resumen_tecnico.docx", "guia_preparacion_oferta.docx", "simulador_economico.xlsx", technical])
        artifacts = []
        for name in names:
            (run_dir / name).write_bytes(f"{name} {job_id}".encode())
            role = _ROLES_BY_NAME.get(name, "technical_document")
            artifacts.append({"role": role, "name": name, "uri": (run_dir / name).as_uri(),
                              "checksum": hashlib.sha256((run_dir / name).read_bytes()).hexdigest()})
        payload = {"contract": 1, "job_id": job_id, "publication_id": "pub-1", "status": "succeeded",
                   "local_path": str(local_path or run_dir), "artifacts": artifacts}
        if tamper:
            tamper(run_dir, payload)
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
    return run


_SHEET_RANGE = re.compile(r"^(?:'(?P<quoted>(?:[^']|'')*)'|(?P<bare>[^'!]+))"
                          r"(?:!(?P<c1>[A-Z]+)(?P<r1>[0-9]+):(?P<c2>[A-Z]+)(?P<r2>[0-9]+))?$")


def _sheet_col_index(letters: str) -> int:
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value


class FakeSheets:
    """In-memory Sheets v4: ``{title: rows}`` per spreadsheet, with the grid size of each sheet.

    ``values`` slices an explicit A1 range like the real API (and trims trailing empty rows/cells);
    with no ``!A1:B2`` suffix it returns the whole sheet.  ``update`` writes an explicit range with
    ``RAW`` semantics, growing the sheet as needed.
    """

    def __init__(self):
        self.spreadsheets: dict[str, dict[str, list[list]]] = {}
        self.grids: dict[tuple[str, str], tuple[int, int]] = {}  # (spreadsheet, title) → (rows, columns)
        self.reads: list[tuple[str, list[str], str]] = []
        self.updates: list[tuple[str, str, list[list]]] = []

    def add(self, spreadsheet_id: str, sheets: dict[str, list[list]]) -> None:
        self.spreadsheets[spreadsheet_id] = sheets

    def get(self, spreadsheet_id):
        if spreadsheet_id not in self.spreadsheets:
            raise HarnessError("not_found", "No existe la hoja de cálculo")
        sheets = []
        for number, (title, rows) in enumerate(self.spreadsheets[spreadsheet_id].items()):
            height, width = self.grids.get((spreadsheet_id, title), (max(len(rows), 1000), 26))
            sheets.append({"properties": {"sheetId": number, "title": title,
                                          "gridProperties": {"rowCount": height, "columnCount": width}}})
        return {"sheets": sheets}

    def values(self, spreadsheet_id, ranges, render="FORMATTED_VALUE"):
        self.reads.append((spreadsheet_id, list(ranges), render))
        result = []
        for name in ranges:
            match = _SHEET_RANGE.match(name)
            title = (match["quoted"] or match["bare"]).replace("''", "'")
            rows = self.spreadsheets[spreadsheet_id][title]
            if match["c1"]:
                r1, r2 = int(match["r1"]), int(match["r2"])
                c1, c2 = _sheet_col_index(match["c1"]), _sheet_col_index(match["c2"])
                sliced = [[row[c - 1] if c - 1 < len(row) else None for c in range(c1, c2 + 1)]
                          for row in rows[r1 - 1:r2]]
            else:
                sliced = [list(row) for row in rows]
            while sliced and all(cell in (None, "") for cell in sliced[-1]):
                sliced.pop()
            result.append({"range": name, "values": sliced})
        return result

    def update(self, spreadsheet_id, range_, values):
        self.updates.append((spreadsheet_id, range_, values))
        match = _SHEET_RANGE.match(range_)
        title = (match["quoted"] or match["bare"]).replace("''", "'")
        r1, c1 = int(match["r1"]), _sheet_col_index(match["c1"])
        rows = self.spreadsheets[spreadsheet_id][title]
        for row_offset, row_values in enumerate(values):
            row_index = r1 - 1 + row_offset
            while len(rows) <= row_index:
                rows.append([])
            row = rows[row_index]
            for col_offset, value in enumerate(row_values):
                col_index = c1 - 1 + col_offset
                while len(row) <= col_index:
                    row.append(None)
                row[col_index] = value
        return {"updatedCells": sum(len(row) for row in values)}


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


OBJECT = object()  # an inline object (image) inside a paragraph: one index, no text


class FakeDocs:
    """In-memory Docs v1: a flat token list per document, rendered as the real structural JSON.

    Each token takes its UTF-16 width in index space: the section break, table,
    row and cell markers and inline objects take one index; text characters take
    one or two.  Only ``insertText`` and ``deleteContentRange`` by index are
    implemented, and every write changes ``revisionId``.
    """

    def __init__(self):
        self.documents: dict[str, dict] = {}
        self.gets: list[str] = []
        self.batches: list[tuple[str, list[dict], str]] = []
        self.lose_answer: set[str] = set()  # document IDs whose next batch "times out" after being applied

    def add(self, document_id: str, blocks: list, *, tabs: int = 1, child_tabs: int = 0,
            revision: str | None = "rev-1") -> None:
        """``blocks``: a str is a paragraph; a list is a paragraph of segments (str, ``OBJECT``,
        ``("text", "insert" | "delete")``); ``{"table": [[cell, ...], ...]}`` is a table of one-paragraph cells."""
        tokens = [("section",)]
        for block in blocks:
            if isinstance(block, dict):
                tokens.append(("table_start",))
                for row in block["table"]:
                    tokens.append(("row",))
                    for cell in row:
                        tokens.append(("cell",))
                        tokens.extend(_chars(cell + "\n"))
                tokens.append(("table_end",))
            else:
                for segment in ([block] if isinstance(block, str) else block):
                    if segment is OBJECT:
                        tokens.append(("object",))
                    elif isinstance(segment, tuple):
                        tokens.extend(_chars(segment[0], segment[1]))
                    else:
                        tokens.extend(_chars(segment))
                tokens.extend(_chars("\n"))
        self.documents[document_id] = {"tokens": tokens, "revision": revision, "tabs": tabs,
                                       "child_tabs": child_tabs, "version": 1}

    def get(self, document_id):
        self.gets.append(document_id)
        if document_id not in self.documents:
            raise HarnessError("not_found", "No existe el documento")
        document = self.documents[document_id]
        tab = {"tabProperties": {"tabId": "t.0"}, "documentTab": {"body": {"content": _render(document["tokens"])}}}
        if document["child_tabs"]:
            tab["childTabs"] = [{"tabProperties": {"tabId": f"t.c{n}"}} for n in range(document["child_tabs"])]
        tabs = [tab, *({"tabProperties": {"tabId": f"t.{n}"}} for n in range(1, document["tabs"]))]
        raw = {"tabs": tabs, "suggestionsViewMode": "SUGGESTIONS_INLINE"}
        if document["revision"] is not None:
            raw["revisionId"] = document["revision"]
        return raw

    def batch_update(self, document_id, requests, required_revision_id):
        self.batches.append((document_id, requests, required_revision_id))
        document = self.documents[document_id]
        if required_revision_id != document["revision"]:
            raise HarnessError("document_changed", "El documento cambió", details={"http_status": 400})
        tokens = list(document["tokens"])
        for request in requests:
            (kind, body), = request.items()
            if kind == "insertText":
                position = _position(tokens, body["location"]["index"])
                assert tokens[position][0] in ("char", "object"), "insertText fuera de un párrafo"
                tokens[position:position] = _chars(body["text"])
            elif kind == "deleteContentRange":
                begin = _position(tokens, body["range"]["startIndex"])
                end = _position(tokens, body["range"]["endIndex"])
                assert begin < end and all(token[0] == "char" for token in tokens[begin:end])
                assert end < len(tokens), "no se puede borrar el salto final del cuerpo"
                del tokens[begin:end]
            else:
                raise AssertionError(f"petición no admitida: {kind}")
        self._write(document_id, tokens)
        if document_id in self.lose_answer:
            self.lose_answer.discard(document_id)
            raise RuntimeError("timeout simulado tras escribir el documento")
        return {"documentId": document_id, "replies": [{} for _ in requests],
                "writeControl": {"requiredRevisionId": self.documents[document_id]["revision"]}}

    def edit_outside(self, document_id: str, index: int, text: str) -> None:
        """Simulate a person typing in the document after the preview."""
        tokens = list(self.documents[document_id]["tokens"])
        position = _position(tokens, index)
        tokens[position:position] = _chars(text)
        self._write(document_id, tokens)

    def plain_text(self, document_id: str) -> str:
        """Every character not carrying a suggested insertion, in token order."""
        return "".join(token[1] for token in self.documents[document_id]["tokens"]
                       if token[0] == "char" and token[2] != "insert")

    def _write(self, document_id: str, tokens: list) -> None:
        document = self.documents[document_id]
        document["version"] += 1
        document.update(tokens=tokens, revision=f"rev-{document['version']}")


def _chars(text: str, suggestion: str | None = None) -> list:
    return [("char", char, suggestion) for char in text]


def _width(token) -> int:
    return 2 if token[0] == "char" and ord(token[1]) > 0xFFFF else 1


def _position(tokens: list, index: int) -> int:
    """Token position that starts at a Docs index; never inside a surrogate pair."""
    at = 0
    for position, token in enumerate(tokens):
        if at == index:
            return position
        assert at < index, f"el índice {index} parte un par sustituto"
        at += _width(token)
    assert at == index, f"índice fuera del documento: {index}"
    return len(tokens)


def _render(tokens: list) -> list:
    """Structural elements with ``startIndex``/``endIndex`` computed from token widths."""
    starts, at = [], 0
    for token in tokens:
        starts.append(at)
        at += _width(token)
    content, position = [], 0

    def paragraph(position: int) -> tuple[dict, int]:
        elements, first = [], position
        while True:
            token = tokens[position]
            if token[0] == "object":
                elements.append({"startIndex": starts[position], "endIndex": starts[position] + 1,
                                 "inlineObjectElement": {"inlineObjectId": "kix.obj"}})
                position += 1
                continue
            begin, suggestion = position, token[2]
            while (position < len(tokens) and tokens[position][0] == "char" and tokens[position][2] == suggestion
                   and (position == begin or tokens[position - 1][1] != "\n")):
                position += 1
            run = {"content": "".join(t[1] for t in tokens[begin:position])}
            if suggestion == "insert":
                run["suggestedInsertionIds"] = ["suggest.1"]
            elif suggestion == "delete":
                run["suggestedDeletionIds"] = ["suggest.2"]
            end = starts[position] if position < len(tokens) else at
            elements.append({"startIndex": starts[begin], "endIndex": end, "textRun": run})
            if tokens[position - 1][1] == "\n":
                end = starts[position] if position < len(tokens) else at
                return {"startIndex": starts[first], "endIndex": end, "paragraph": {"elements": elements}}, position

    while position < len(tokens):
        kind = tokens[position][0]
        if kind == "section":
            content.append({"endIndex": 1, "sectionBreak": {}})
            position += 1
        elif kind == "table_start":
            first, rows = position, []
            position += 1
            while tokens[position][0] == "row":
                row_start, cells = position, []
                position += 1
                while tokens[position][0] == "cell":
                    cell_start = position
                    item, position = paragraph(position + 1)
                    cells.append({"startIndex": starts[cell_start], "endIndex": item["endIndex"], "content": [item]})
                rows.append({"startIndex": starts[row_start], "endIndex": cells[-1]["endIndex"], "tableCells": cells})
            position += 1  # table_end
            content.append({"startIndex": starts[first], "endIndex": starts[position - 1] + 1,
                            "table": {"rows": len(rows), "tableRows": rows}})
        else:
            item, position = paragraph(position)
            content.append(item)
    return content
