from __future__ import annotations

import io
import hashlib
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from litman_analysis.domain.jobs import JobRequest, JobType, MaterializedCase, PublishedArtifact
from .common import catalog_digest, detailed_analysis_delivery_catalog, safe_filename, sha256

_DRIVE_OPTIONS = {"supportsAllDrives": True}
_FOLDER_MIME = "application/vnd.google-apps.folder"
_NATIVE_PREFIX = "application/vnd.google-apps."
_LOGGER = logging.getLogger(__name__)
_DELIVERY_CONTRACT_VERSION = "detailed-analysis-drive-v2"
_ASSESSMENT_CONTRACT_VERSION = "assessment-drive-v1"


def build_drive_service(credentials_file: Path):
    if not credentials_file.is_file():
        raise ValueError("GOOGLE_APPLICATION_CREDENTIALS debe referirse a un archivo legible")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("La instalación no incluye dependencias de Google Drive") from exc
    credentials = service_account.Credentials.from_service_account_file(str(credentials_file), scopes=["https://www.googleapis.com/auth/drive"])
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _download(request: Any, output: Any) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(output, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()


def _upload(path: Path) -> Any:
    from googleapiclient.http import MediaFileUpload
    return MediaFileUpload(str(path), resumable=True)


class GoogleDriveDocumentSource:
    def __init__(self, service: Any, max_file_mb: int = 25, downloader: Callable[[Any, Any], None] = _download) -> None:
        self.service, self.max_bytes, self.downloader = service, max_file_mb * 1024 * 1024, downloader

    def materialize(self, job: JobRequest, workspace: Path) -> MaterializedCase:
        folder = self._folder_metadata(job.input_location)
        documents = self._validated_documents(self._children(job.input_location, folder.get("driveId")))
        target = workspace / "case"
        if target.exists():
            raise ValueError("El expediente temporal ya existe")
        target.mkdir(parents=True)
        try:
            for document, name in documents:
                self._download_document(document, target / name)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        metadata = {
            name: {
                "document_id": document["id"],
                "filename": document["name"],
                "mime_type": document.get("mimeType") or "application/octet-stream",
                "drive_md5": document.get("md5Checksum"),
            }
            for document, name in documents
        }
        return MaterializedCase(job.job_id, target, metadata)

    def _folder_metadata(self, folder_id: str) -> dict[str, Any]:
        try:
            metadata = self.service.files().get(fileId=folder_id, fields="id,name,mimeType,trashed,driveId", **_DRIVE_OPTIONS).execute()
        except Exception as exc:
            raise ValueError("No se puede acceder a la carpeta de entrada de Google Drive") from exc
        if not isinstance(metadata, dict) or metadata.get("mimeType") != _FOLDER_MIME:
            raise ValueError("La ubicación de entrada de Google Drive debe ser una carpeta")
        if metadata.get("trashed"):
            raise ValueError("La carpeta de entrada de Google Drive está en la papelera")
        return metadata

    def _children(self, folder_id: str, drive_id: object) -> list[dict[str, Any]]:
        common: dict[str, Any] = {
            "q": f"'{folder_id}' in parents and trashed = false", "spaces": "drive",
            "fields": "nextPageToken,incompleteSearch,files(id,name,mimeType,parents,size,md5Checksum)",
            "pageSize": 1000, "supportsAllDrives": True, "includeItemsFromAllDrives": True,
        }
        if isinstance(drive_id, str) and drive_id:
            common.update(corpora="drive", driveId=drive_id)
        else:
            common["corpora"] = "user"
        result: list[dict[str, Any]] = []
        token: str | None = None
        seen: set[str] = set()
        while True:
            response = self.service.files().list(**common, pageToken=token).execute()
            if response.get("incompleteSearch"):
                raise ValueError("La búsqueda de la carpeta de entrada de Google Drive está incompleta")
            result.extend(response.get("files", []))
            next_token = response.get("nextPageToken")
            if not next_token:
                return result
            if not isinstance(next_token, str) or next_token in seen:
                raise ValueError("Google Drive devolvió un token de página repetido")
            seen.add(next_token)
            token = next_token

    def _validated_documents(self, files: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
        documents: list[tuple[dict[str, Any], str]] = []
        names: set[str] = set()
        for item in files:
            name = item.get("name")
            if item.get("mimeType") == _FOLDER_MIME:
                _LOGGER.info("Se ignora la subcarpeta de entrada de Google Drive: %s", name)
                continue
            if item.get("mimeType") == "application/vnd.google-apps.shortcut":
                raise ValueError(f"La carpeta de entrada contiene un acceso directo: {name}")
            if str(item.get("mimeType", "")).startswith(_NATIVE_PREFIX):
                raise ValueError(f"Documento nativo de Google Workspace no soportado: {name}")
            if not isinstance(name, str):
                raise ValueError("Nombre de documento inválido")
            safe_name = safe_filename(name)
            if safe_name in names:
                raise ValueError("Nombres de Drive colisionan tras sanearse")
            names.add(safe_name)
            try:
                if item.get("size") is not None and int(item["size"]) > self.max_bytes:
                    raise ValueError(f"Documento supera el tamaño máximo: {name}")
            except (TypeError, ValueError) as exc:
                if isinstance(exc, ValueError) and "supera" in str(exc):
                    raise
                raise ValueError(f"Tamaño de documento inválido: {name}") from exc
            if not isinstance(item.get("id"), str) or not item["id"]:
                raise ValueError(f"Documento de Drive sin ID válido: {name}")
            documents.append((item, safe_name))
        if not documents:
            raise ValueError("La carpeta de entrada de Google Drive no contiene archivos")
        return sorted(documents, key=lambda value: (value[1].casefold(), value[0]["id"]))

    def _download_document(self, document: dict[str, Any], destination: Path) -> None:
        try:
            with destination.open("wb") as output:
                self.downloader(self.service.files().get_media(fileId=document["id"], **_DRIVE_OPTIONS), output)
            if destination.stat().st_size > self.max_bytes:
                raise ValueError(f"Documento supera el tamaño máximo: {document['name']}")
            sha256(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise

class GoogleDriveArtifactPublisher:
    def __init__(
        self,
        service: Any,
        temporary_suffix: Callable[[], str] | None = None,
        uploader: Callable[[Path], Any] = _upload,
        downloader: Callable[[Any, Any], None] = _download,
    ) -> None:
        self.service = service
        self._temporary_suffix = temporary_suffix or (lambda: uuid.uuid4().hex)
        self.uploader = uploader
        self.downloader = downloader

    def _folders(self, name: str, parent: str) -> list[dict]:
        escaped = name.replace("'", "\\'")
        query = f"name = '{escaped}' and '{parent}' in parents and mimeType = '{_FOLDER_MIME}' and trashed = false"
        return self.service.files().list(q=query, spaces="drive", fields="files(id,name,appProperties)", includeItemsFromAllDrives=True, supportsAllDrives=True).execute().get("files", [])

    def _create_folder(self, name: str, parent: str, app_properties: dict[str, str] | None = None) -> str:
        body: dict[str, Any] = {"name": safe_filename(name), "mimeType": _FOLDER_MIME, "parents": [parent]}
        if app_properties is not None:
            body["appProperties"] = app_properties
        return self.service.files().create(body=body, fields="id", **_DRIVE_OPTIONS).execute()["id"]

    def _existing(self, final: list[dict], job: JobRequest, catalog: tuple) -> tuple[PublishedArtifact, ...]:
        if len(final) > 1:
            raise FileExistsError(f"Hay más de una carpeta final para el job {job.job_id}")
        metadata = final[0].get("appProperties")
        expected_metadata = self._folder_properties(job, catalog)
        if not isinstance(metadata, dict) or any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise FileExistsError("La salida Drive existente no coincide con el job o el catálogo")
        children = self.service.files().list(
            q=f"'{final[0]['id']}' in parents and trashed = false", spaces="drive",
            fields="files(id,name,mimeType,webViewLink,appProperties)",
            includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute().get("files", [])
        expected = {item.name: item for item in catalog}
        if len(children) != len(expected) or {item.get("name") for item in children} != set(expected):
            raise FileExistsError("La salida Drive existente no contiene el catálogo esperado de documentos")
        result: list[PublishedArtifact] = []
        for child in children:
            name = child.get("name")
            if not isinstance(name, str) or child.get("mimeType") == _FOLDER_MIME:
                raise FileExistsError("La salida Drive existente contiene un artefacto inválido")
            stream = io.BytesIO()
            self.downloader(self.service.files().get_media(fileId=child["id"], **_DRIVE_OPTIONS), stream)
            checksum = hashlib.sha256(stream.getvalue()).hexdigest()
            if checksum != expected[name].checksum:
                raise FileExistsError("La salida Drive existente no coincide con el catálogo")
            result.append(PublishedArtifact(name, child.get("webViewLink") or f"drive://{child['id']}", checksum))
        return tuple(sorted(result, key=lambda item: item.name))

    @staticmethod
    def _folder_properties(job: JobRequest, catalog: tuple) -> dict[str, str]:
        return {"job_id": job.job_id, "job_type": str(job.job_type),
                "publication_contract": _DELIVERY_CONTRACT_VERSION,
                "catalog_sha256": catalog_digest(catalog)}

    def publish(self, job: JobRequest, run_dir: Path) -> tuple[PublishedArtifact, ...]:
        if job.job_type is JobType.ASSESSMENT:
            return self._publish_assessment(job, run_dir)
        catalog = detailed_analysis_delivery_catalog(run_dir)
        final = self._folders(job.job_id, job.output_location)
        if final:
            return self._existing(final, job, catalog)
        temporary_name = f".{job.job_id}.tmp-{self._temporary_suffix()}"
        temporary = self._create_folder(temporary_name, job.output_location, self._folder_properties(job, catalog))
        try:
            published: list[tuple[str, str, str]] = []
            for item in catalog:
                result = self.service.files().create(body={"name": item.name, "parents": [temporary], "appProperties": {"sha256": item.checksum}}, media_body=self.uploader(item.source), fields="id,webViewLink", **_DRIVE_OPTIONS).execute()
                if not result.get("id"):
                    raise RuntimeError(f"La subida de {item.name} a Drive no devolvió un ID")
                published.append((item.name, item.checksum, result.get("webViewLink") or f"drive://{result['id']}"))
            if len(published) != len(catalog):
                raise RuntimeError("Publicación Drive incompleta")
            concurrent_final = self._folders(job.job_id, job.output_location)
            if concurrent_final:
                existing = self._existing(concurrent_final, job, catalog)
                self._delete_temporary(temporary)
                return existing
            self.service.files().update(fileId=temporary, body={"name": job.job_id}, fields="id", **_DRIVE_OPTIONS).execute()
            post_promotion = self._folders(job.job_id, job.output_location)
            competing = [folder for folder in post_promotion if folder.get("id") != temporary]
            if competing:
                existing = self._existing(competing, job, catalog)
                self._delete_temporary(temporary)
                return existing
            return tuple(PublishedArtifact(name, uri, checksum) for name, checksum, uri in published)
        except Exception:
            try:
                self._delete_temporary(temporary)
            except Exception as cleanup_error:
                _LOGGER.warning(
                    "No se pudo limpiar la carpeta Drive temporal del job %s (temporary_id=%s): %s",
                    job.job_id, temporary, type(cleanup_error).__name__,
                )
            raise

    def _publish_assessment(self, job: JobRequest, run_dir: Path) -> tuple[PublishedArtifact, ...]:
        """Publish one PDF inside an atomic job folder in the requested destination."""
        pdf = run_dir / "output" / "ficha_oportunidad.pdf"
        if not pdf.is_file():
            raise ValueError(f"No existe el PDF de assessment requerido: {pdf}")
        checksum = sha256(pdf)
        final = self._folders(job.job_id, job.output_location)
        if final:
            return self._existing_assessment(final, checksum)
        temporary = self._create_folder(
            f".{job.job_id}.tmp-{self._temporary_suffix()}", job.output_location,
            {"job_id": job.job_id, "job_type": str(job.job_type),
             "publication_contract": _ASSESSMENT_CONTRACT_VERSION, "pdf_sha256": checksum},
        )
        try:
            result = self.service.files().create(
                body={"name": "ficha_oportunidad.pdf", "parents": [temporary],
                      "appProperties": {"sha256": checksum}},
                media_body=self.uploader(pdf), fields="id,webViewLink", **_DRIVE_OPTIONS,
            ).execute()
            if not result.get("id"):
                raise RuntimeError("La subida de ficha_oportunidad.pdf a Drive no devolvió un ID")
            concurrent = self._folders(job.job_id, job.output_location)
            if concurrent:
                existing = self._existing_assessment(concurrent, checksum)
                self._delete_temporary(temporary)
                return existing
            self.service.files().update(
                fileId=temporary, body={"name": job.job_id}, fields="id", **_DRIVE_OPTIONS
            ).execute()
            post_promotion = self._folders(job.job_id, job.output_location)
            competing = [folder for folder in post_promotion if folder.get("id") != temporary]
            if competing:
                existing = self._existing_assessment(competing, checksum)
                self._delete_temporary(temporary)
                return existing
            uri = result.get("webViewLink") or f"drive://{result['id']}"
            return (PublishedArtifact("ficha_oportunidad.pdf", uri, checksum),)
        except Exception:
            try:
                self._delete_temporary(temporary)
            except Exception as cleanup_error:
                _LOGGER.warning(
                    "No se pudo limpiar la carpeta temporal de assessment %s (temporary_id=%s): %s",
                    job.job_id, temporary, type(cleanup_error).__name__,
                )
            raise

    def _existing_assessment(self, folders: list[dict], checksum: str) -> tuple[PublishedArtifact, ...]:
        if len(folders) > 1:
            raise FileExistsError("Hay más de una carpeta final para el assessment")
        children = self.service.files().list(
            q=f"'{folders[0]['id']}' in parents and trashed = false", spaces="drive",
            fields="files(id,name,mimeType,webViewLink,appProperties)",
            includeItemsFromAllDrives=True, supportsAllDrives=True,
        ).execute().get("files", [])
        if len(children) != 1 or children[0].get("name") != "ficha_oportunidad.pdf" or children[0].get("mimeType") == _FOLDER_MIME:
            raise FileExistsError(
                "La carpeta Drive existente de assessment no contiene únicamente ficha_oportunidad.pdf"
            )
        child = children[0]
        stream = io.BytesIO()
        self.downloader(self.service.files().get_media(fileId=child["id"], **_DRIVE_OPTIONS), stream)
        remote_checksum = hashlib.sha256(stream.getvalue()).hexdigest()
        if remote_checksum != checksum:
            raise FileExistsError(
                "La carpeta Drive existente contiene ficha_oportunidad.pdf con contenido diferente; no se sobrescribe"
            )
        return (PublishedArtifact(
            "ficha_oportunidad.pdf", child.get("webViewLink") or f"drive://{child['id']}", checksum
        ),)

    def _delete_temporary(self, temporary: str) -> None:
        self.service.files().delete(fileId=temporary, **_DRIVE_OPTIONS).execute()
