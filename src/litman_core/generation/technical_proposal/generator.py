from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from litman_core.application.ports.llm import output_paths_for_run

from .content import build_generation_prompt, fallback_content, skeleton_content
from .planner import build_document_plan
from .renderer import render_technical_document
from litman_core.generation.models import ArtifactContext
from litman_core.resource_paths import resource_path


class TechnicalDocumentGenerator:
    id = "technical-document"
    version = "technical-document-generator-v4"

    def generate(self, context: ArtifactContext) -> dict:
        template_path, manifest = _template(context.template_id)
        shutil.copy2(template_path.parent / "template.yaml", context.run_dir / "input" / "template.yaml")
        plan = build_document_plan(context.dossier, context.template_id)
        _write_json(context.run_dir / "input" / "document_plan.json", plan)
        content, generation = _generate_content(context, plan)
        _write_json(context.run_dir / "output" / "content.json", content)
        return self._render(context.run_dir, context.dossier, plan, content, manifest,
                            context.include_internal_pending, context.include_editorial_guidance, generation)

    def rerender(self, run_dir: Path, **options: object) -> dict:
        run_dir = run_dir.resolve()
        dossier = json.loads((run_dir / "input" / "dossier.json").read_text(encoding="utf-8"))
        plan = json.loads((run_dir / "input" / "document_plan.json").read_text(encoding="utf-8"))
        # Un refresh explícito es la única ocasión en que se migra el esqueleto
        # histórico; queda persistido y no altera rerenders ordinarios.
        if bool(options.get("refresh_skeleton", False)) and plan.get("version") != "document-plan-v2":
            plan = build_document_plan(dossier, plan.get("template_id", "next-standard-v1"))
            _write_json(run_dir / "input" / "document_plan.json", plan)
        if plan.get("language") != "es":
            raise ValueError("No se puede rerenderizar un plan histórico que no sea de salida en español.")
        content_path = run_dir / "output" / "content.json"
        refresh = bool(options.get("refresh_skeleton", False))
        content = skeleton_content(dossier, plan) if refresh else json.loads(content_path.read_text(encoding="utf-8"))
        if refresh: _write_json(content_path, content)
        _, manifest = _template(plan.get("template_id", "next-standard-v1"))
        result = self._render(run_dir, dossier, plan, content, manifest,
                              bool(options.get("include_internal_pending", True)),
                              bool(options.get("include_editorial_guidance", True)), None)
        return dict(result, status="completed", run_dir=str(run_dir), content_refreshed=refresh,
                    document=result["documents"][0])

    def _render(self, run_dir, dossier, plan, content, manifest, include_pending, include_guidance, generation):
        validation = _validate_content(content, plan)
        if not validation["valid"]:
            _write_json(run_dir / "output" / "validation.json", {"valid": False, "content": validation,
                "errors": ["El contenido generado no respeta el plan del documento"], "warnings": [],
                "page_limit_validation": "not_performed"})
            raise ValueError("El contenido generado no respeta el plan del documento")
        pending = _all_pending(content, plan)
        _write_json(run_dir / "output" / "pending.json", pending)
        _write_json(run_dir / "output" / "coverage.json", _coverage(plan, content))
        template_path, _ = _template(plan.get("template_id", "next-standard-v1"))
        output = run_dir / "output" / _document_filename(plan)
        rendered = render_technical_document(template_path, content, plan, output,
            include_internal_pending=include_pending, include_editorial_guidance=include_guidance,
            body_marker=manifest.get("body_marker", "[[DOCUMENT_BODY]]"),
            table_format=manifest.get("table_format", {}), toc_format=manifest.get("toc", {}),
            heading_format=manifest.get("headings", {}))
        rendered["content"] = validation
        _write_json(run_dir / "output" / "validation.json", rendered)
        metadata = {"format": "docx", "template_id": manifest["id"], "template_version": manifest["version"],
                    "manifest_fields": {"template_id": manifest["id"], "template_version": manifest["version"]}}
        if generation is not None:
            metadata["generation"] = generation
            metadata["manifest_fields"]["generation"] = generation
        return {"id": self.id, "generator_version": self.version, "documents": [str(output)],
                "validation": rendered, "pending": pending, "metadata": metadata}


def _template(template_id):
    directory = resource_path("templates", "technical-proposal", template_id)
    path = directory / "template.docx"
    if not path.exists():
        raise ValueError(f"No existe la plantilla runtime versionada: {path}")
    return path, yaml.safe_load((directory / "template.yaml").read_text(encoding="utf-8"))


def _generate_content(context, plan):
    if context.content_profile == "skeleton-v1": return skeleton_content(context.dossier, plan), {"mode": "skeleton", "profile": context.content_profile}
    if context.content_profile != "draft-v1": raise ValueError(f"Perfil de contenido no soportado: {context.content_profile}")
    if context.provider is None: return fallback_content(context.dossier, plan), {"mode": "deterministic-fallback", "profile": context.content_profile}
    prompt_dir = resource_path("pipelines", "detailed", "v1", "generation")
    instructions, task = (prompt_dir / "system.md").read_text(encoding="utf-8"), (prompt_dir / "generation.md").read_text(encoding="utf-8")
    prompt = build_generation_prompt(task, context.dossier, plan)
    (context.run_dir / "input" / "prompt.md").write_text(f"{instructions}\n\n---\n\n{prompt}", encoding="utf-8")
    response = context.provider.generate(instructions=instructions, prompt=prompt,
        schema_path=resource_path("schemas", "technical-content.schema.json"), case_dir=context.case_dir,
        output_paths=output_paths_for_run(context.run_dir, "draft-v1"))
    return response.data, {"mode": "llm", "provider": response.provider, "model": response.model,
        "response_id": response.response_id, "prompt_version": (prompt_dir / "VERSION").read_text(encoding="utf-8").strip(),
        "usage": response.usage, "execution": response.execution, "profile": context.content_profile}


def _validate_content(content, plan):
    schema = json.loads(resource_path("schemas", "technical-content.schema.json").read_text(encoding="utf-8"))
    errors = [{"path": ".".join(map(str, e.path)), "message": e.message} for e in Draft202012Validator(schema).iter_errors(content)]
    if [x.get("id") for x in content.get("sections", [])] != [x["id"] for x in plan["sections"]]: errors.append({"path": "sections", "message": "Las secciones no respetan el plan y su orden"})
    for key, label in (("document_title", "El título no respeta el plan del documento"), ("language", "El idioma no respeta el plan del documento")):
        if content.get(key) != plan.get(key): errors.append({"path": key, "message": label})
    planned = {x["id"]: x for x in plan["sections"]}
    for section in content.get("sections", []):
        expected = planned.get(section.get("id"), {})
        actual_subsections = [(b.get("id"), b.get("text"), b.get("level")) for b in section.get("blocks", []) if b.get("type") == "subheading"]
        planned_subsections = [(b.get("id"), b.get("level", 2)) for b in expected.get("subsections", [])]
        actual_subsections = [(block_id, level) for block_id, _text, level in actual_subsections]
        if actual_subsections != planned_subsections:
            errors.append({"path": f"sections.{section.get('id')}.blocks", "message": "Los subapartados no respetan el plan y su orden"})
        for key, label in (("requirements_covered", "Declara requisitos no asignados al apartado"), ("evidence_fields", "Declara evidencias no trazables al plan")):
            if set(section.get(key, [])) - set(expected.get("requirements" if key == "requirements_covered" else key, [])): errors.append({"path": f"sections.{section.get('id')}.{key}", "message": label})
    if any(x.get("section_id") is not None and x["section_id"] not in planned for x in content.get("pending", [])): errors.append({"path": "pending", "message": "Un pendiente referencia una sección inexistente"})
    return {"valid": not errors, "errors": errors}


def _document_filename(plan: dict) -> str:
    import re
    identity = plan.get("identity")
    # Rerender v1 preserves the historical public name rather than adding a
    # second generic document to an existing run.
    if not identity:
        return "propuesta_tecnica_base.docx"
    reference = identity.get("tender_reference") or ""
    title = identity.get("short_title") or ""
    pieces = ["Propuesta técnica", str(reference), str(title)]
    value = " ".join(x.strip() for x in pieces if x and x.strip())
    value = re.sub(r'[\\/:*?"<>|]+', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    # Límite portable sin cortar la última palabra.
    if len(value) > 180:
        shortened = value[:181].rsplit(" ", 1)[0].rstrip(" .")
        value = shortened or value[:180].rstrip(" .")
    return (value or "Propuesta técnica") + ".docx"


def _all_pending(content, plan):
    items = list(content.get("pending", []))
    existing = {x.get("description") for x in items}
    items += [{"section_id": None, "description": x, "reason": "Decisión o dato no localizado en el expediente"} for x in plan.get("pending_decisions", []) if x not in existing]
    items += [{"section_id": s["id"], "description": x, "reason": s.get("review", {}).get("reason")} for s in content.get("sections", []) for x in s.get("pending", [])]
    return list({(x.get("section_id"), x.get("description"), x.get("reason")): x for x in items}.values())
def _coverage(plan, content):
    sections = {x["id"]: x for x in content.get("sections", [])}; details = []
    for item in plan["sections"]:
        value = sections.get(item["id"], {}); complete = bool(value.get("blocks")) and not value.get("pending")
        details.append({"section_id": item["id"], "title": item["title"], "requirements": item["requirements"], "criteria": item["criteria"], "generated": bool(value.get("blocks")), "requirements_covered": value.get("requirements_covered", []), "response_complete": complete, "pending": value.get("pending", []), "evidence_fields": value.get("evidence_fields", []), "subsections": item.get("subsections", [])})
    return {"sections": details, "complete": all(x["response_complete"] for x in details)}
def _write_json(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
