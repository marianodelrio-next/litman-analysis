"""The single next step of the guided path, computed deterministically from known state.

organise (structure + originals) → initial analysis (+ publication) → summary →
detailed analysis? (+ publication, live offer) → refresh summary → the person decides.
"""
from __future__ import annotations

from typing import Any

from .manifest import Manifest


def _action(kind: str, reason: str, tool: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"kind": kind, "reason": reason, "tool": tool, "arguments": arguments or {}}


def recommend(*, folder_id: str, state: str, manifest: Manifest | None, candidates: dict[str, Any] | None = None,
              pending: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """First applicable step; ``None`` when nothing is pending (ask the person)."""
    candidates = candidates or {}
    pending = pending or []
    if state in ("partial", "unsupported_manifest"):
        return _action("review_manifest", "El estado LitMan de la carpeta necesita revisión antes de continuar.",
                       "status", {"folder_id": folder_id})
    published = manifest.published_analyses() if manifest else []
    # Only a dossier without registered originals needs organising first; extra
    # unregistered candidates never block the path (they stay an option in next_actions).
    if manifest is None or not manifest.originals:
        return _action(
            "incorporate",
            "Organizar la licitación: registrar los pliegos originales y la estructura de carpetas.",
            "preview_incorporation",
            {"folder_id": folder_id, "suggested_original_ids": list(candidates.get("originals") or []),
             "suggested_folder_ids": dict(candidates.get("suggested_folder_ids") or {})})
    if pending:
        item = pending[0]
        if item.get("publication_plan_id"):
            return _action("publish_analysis", "Hay un análisis local validado cuya publicación quedó pendiente.",
                           "apply_publication", {"plan_id": item["publication_plan_id"]})
        return _action("publish_analysis", "Hay un análisis local validado sin publicar.", "preview_publication",
                       {"analysis_operation_id": item["operation_id"]})
    originals = [item["file_id"] for item in manifest.originals]
    if not published:
        return _action("run_assessment", "Analizar la oportunidad (análisis inicial) y publicar sus resultados.",
                       "preview_analysis",
                       {"folder_id": folder_id, "original_ids": originals, "job_type": "assessment"})
    summary = manifest.summary
    if not summary:
        return _action("propose_summary", "Preparar el resumen de contexto de la licitación con los resultados "
                       "publicados.", "preview_summary", {"folder_id": folder_id})
    if set(published) - set(summary.get("based_on_analyses") or []):
        return _action("refresh_summary", "Actualizar el resumen con los análisis publicados después.",
                       "preview_summary", {"folder_id": folder_id})
    if not any(item.get("type") == "detailed-analysis" and item.get("status") == "published"
               for item in manifest.analyses):
        return _action("decide_detailed_analysis", "Decidir si se prepara el análisis detallado (incluye el "
                       "borrador de la oferta); es una decisión de negocio.", "preview_analysis",
                       {"folder_id": folder_id, "original_ids": originals, "job_type": "detailed-analysis"})
    return None
