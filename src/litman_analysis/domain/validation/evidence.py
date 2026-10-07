from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from litman_analysis.domain.documents import Document, NormalizedDocument

from .models import ValidationError


def iter_evidences(value: object, path: str = ""):
    """Recorre cualquier cita, también las anidadas en estructuras específicas."""
    if isinstance(value, dict):
        if "documento_id" in value and ("texto_citado" in value or "pagina" in value):
            yield path or "root", value
            return
        for key, child in value.items():
            yield from iter_evidences(child, f"{path}.{key}".strip("."))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_evidences(child, f"{path}.{index}".strip("."))


def validate_document_references(data: dict, document_ids: set[str]) -> list[ValidationError]:
    """Comprueba que toda cita apunte a un documento del inventario."""
    return [{"path": path, "documento_id": evidence.get("documento_id"),
             "message": "Documento de evidencia inexistente en el inventario"}
            for path, evidence in iter_evidences(data)
            if evidence.get("documento_id") not in document_ids]


def build_evidence_index(data: dict, documents: list[Document], normalized: list[NormalizedDocument]) -> dict:
    """Enriquece las citas y comprueba documento, página y literal contra Markdown."""
    docs = {item.document_id: item for item in documents}
    normalized_by_id = {item.document_id: item for item in normalized}
    entries = []
    for path, evidence in iter_evidences(data):
        document_id = evidence.get("documento_id")
        document = docs.get(document_id)
        item = normalized_by_id.get(document_id)
        page = evidence.get("pagina")
        quote = evidence.get("texto_citado") or ""
        status = _status(document, item, page, quote)
        verification_method = None
        if status == "verified":
            verification_method = _quote_match_method(item, page, quote)
            if verification_method is None:
                status = "quote_not_found"
        field = evidence.get("campo") or path
        digest = hashlib.sha256(f"{document_id}|{page}|{field}|{_compact(quote)}".encode("utf-8")).hexdigest()[:12]
        entries.append({"evidence_id": f"ev_{digest}", "field": field,
                        "document_id": document_id, "document_name": document.filename if document else None,
                        "document_path": str(document.path) if document else None,
                        "page": page, "section": evidence.get("seccion"), "quote": quote,
                        "verification": status, "verification_method": verification_method})
    unique = {item["evidence_id"]: item for item in entries}
    values = sorted(unique.values(), key=lambda item: (str(item["field"]), str(item["document_name"]), str(item["page"])))
    by_field: dict[str, list[str]] = {}
    for item in values:
        by_field.setdefault(str(item["field"] or ""), []).append(item["evidence_id"])
    return {"version": "evidence-index-v1", "evidences": values, "by_field": by_field}


def verification_errors(index: dict) -> list[ValidationError]:
    return [{"path": item.get("field"), "message": item["verification"], "evidence_id": item["evidence_id"]}
            for item in index["evidences"] if item["verification"] != "verified"]


def evidence_ids_for(index: dict, *fields: str) -> list[str]:
    found: list[str] = []
    for requested in fields:
        for field, identifiers in index.get("by_field", {}).items():
            if field == requested or field.startswith(requested + ".") or requested.startswith(field + "."):
                found.extend(identifiers)
    return list(dict.fromkeys(found))


def _status(document: Document | None, item: NormalizedDocument | None, page: object, quote: str) -> str:
    if document is None:
        return "missing_document"
    if not quote.strip():
        return "empty_quote"
    if item is None or item.status != "ready" or not item.normalized_path:
        return "unverifiable"
    if item.page_count is not None and (not isinstance(page, int) or page < 1 or page > item.page_count):
        return "invalid_page"
    return "verified"


def _quote_match_method(item: NormalizedDocument | None, page: object,
                        quote: str) -> str | None:
    if item is None or not item.normalized_path:
        return None
    text = Path(item.normalized_path).read_text(encoding="utf-8", errors="replace")
    if isinstance(page, int):
        marker = f"<!-- pagina: {page} -->"
        start = text.find(marker)
        if start >= 0:
            end = text.find("<!-- pagina:", start + len(marker))
            text = text[start:end if end >= 0 else None]
    if _ordered_match(_compact(text), quote, _compact, minimum=12):
        return "exact"
    if _ordered_match(_layout_key(text), quote, _layout_key, minimum=20):
        return "layout_whitespace"
    return None


def _ordered_match(haystack: str, quote: str, normalizer, *, minimum: int) -> bool:
    expected = normalizer(quote)
    if expected in haystack:
        return True
    fragments = [normalizer(part) for part in re.split(r"(?:\.\.\.|…)", quote)]
    fragments = [part for part in fragments if len(part) >= minimum]
    position = 0
    for fragment in fragments:
        position = haystack.find(fragment, position)
        if position < 0:
            return False
        position += len(fragment)
    return bool(fragments)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _layout_key(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).replace("\u00ad", "").casefold()
    return "".join(character for character in value if not character.isspace())
