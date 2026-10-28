"""Deterministic, non-instructional ``contexto.md`` rendered only from the manifest.

Another installation reproduces exactly the same text from the same manifest.
"""
from __future__ import annotations

from hashlib import sha256

from .manifest import SUMMARY_KEYS, SUMMARY_LABELS, Manifest

_ROLE_TEXT = {
    "originals": ("Originales", "pliegos y documentos de la licitación tal como se recibieron."),
    "initial": ("Análisis inicial", "resultados del análisis inicial de oportunidad."),
    "detailed": ("Análisis detallado", "resultados del análisis detallado."),
    "offer": ("Oferta", "documento vivo de la oferta y material de trabajo."),
    "internal": ("Interno", "material interno de la empresa."),
    "deliveries": ("Entregas", "versiones entregadas."),
    "litman": ("_LitMan", "estado técnico del expediente; no editar a mano."),
}
_ANALYSIS_TYPES = {"assessment": "Análisis inicial", "detailed-analysis": "Análisis detallado"}
# One fixed phrase per artifact role: the context never depends on Core's content.
# "technical-document" (hyphen) is a back-compat alias for manifests published
# before the role became "technical_document" (underscore, Core's contract).
_ARTIFACT_TEXT = {"opportunity_report": "ficha de oportunidad", "technical_summary": "resumen técnico",
                  "bid_preparation_guide": "guía de preparación de la oferta",
                  "economic_simulator": "simulador económico",
                  "technical_document": "documento técnico (borrador de oferta)",
                  "technical-document": "documento técnico (borrador de oferta)"}


def _link(identifier: str) -> str:
    return f"https://drive.google.com/open?id={identifier}"


def _one_line(value: object) -> str:
    return " ".join(str(value).split())


def context_sha256(content: str) -> str:
    return sha256(content.encode("utf-8")).hexdigest()


def render_context(manifest: Manifest, title: str) -> str:
    """Brief verifiable map: phase, links by ID, live offer and cited results."""
    lines = [f"# {_one_line(title) or 'Licitación'}", "",
             "Mapa informativo generado por LitMan a partir de `_LitMan/manifest.json`. "
             "No contiene instrucciones para el agente ni sustituye a los pliegos ni a la oferta.", "",
             f"- Fase confirmada: `{manifest.workflow_phase}`", f"- Expediente: `{manifest.dossier_id}`", "",
             "## Resumen", *_summary_lines(manifest), "", "## Carpetas"]
    folders = [(role, manifest.folders.get(role)) for role in _ROLE_TEXT if manifest.folders.get(role)]
    lines += [f"- [{_ROLE_TEXT[role][0]}]({_link(identifier)}): {_ROLE_TEXT[role][1]}" for role, identifier in folders]
    if not folders:
        lines.append("- Aún no hay carpetas registradas.")
    lines += ["", "## Documentos"]
    for item in manifest.active_originals():
        name = _one_line(item.get("observed_name") or item["file_id"])
        lines.append(f"- Original: [{name}]({_link(item['file_id'])})")
    if manifest.live_offer:
        lines.append(f"- Oferta viva: [Google Doc]({_link(manifest.live_offer['document_id'])})")
    if not manifest.active_originals() and not manifest.live_offer:
        lines.append("- Aún no hay documentos registrados.")
    lines += ["", "## Resultados"]
    published = [item for item in manifest.analyses if item.get("status") == "published"]
    if not published:
        lines.append("- Todavía no hay resultados publicados.")
    for item in published:
        kind = _ANALYSIS_TYPES.get(str(item.get("type")), str(item.get("type")))
        folder = f" ([carpeta]({_link(item['folder_id'])}))" if item.get("folder_id") else ""
        lines.append(f"- {kind}{folder}, operación `{item.get('operation_id')}`, "
                     f"publicación `{item.get('publication_id')}`:")
        for artifact in item.get("artifacts") or []:
            text = _ARTIFACT_TEXT.get(str(artifact.get("role")), "artefacto")
            lines.append(f"  - [{_one_line(artifact.get('name'))}]({_link(artifact['file_id'])}): {text}")
    return "\n".join(lines) + "\n"


def _summary_lines(manifest: Manifest) -> list[str]:
    """One line per key in fixed order with its source link, plus provenance."""
    summary = manifest.summary
    if not summary:
        return ["- Resumen pendiente de proponer."]
    by_key = {item["key"]: item for item in summary.get("items") or []}
    lines = []
    for key in SUMMARY_KEYS:
        item = by_key.get(key)
        if item is None:
            continue
        source_id = item.get("source_file_id")
        retired = set(manifest.summary_sources(historical=True)) - set(manifest.summary_sources())
        source = (" (fuente retirada; revisar)" if source_id in retired else
                  f" ([fuente]({_link(source_id)}))" if source_id else "")
        lines.append(f"- {SUMMARY_LABELS[key]}: {_one_line(item['value'])}{source}")
    lines.append(f"- Propuesto por el asistente y aceptado por {_one_line(summary.get('accepted_by'))}; "
                 "cada línea cita el documento del que procede.")
    return lines
