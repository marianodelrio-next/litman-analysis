from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from .calculator import calculate_scenario
from .planner import build_economic_plan, skeleton_economic_inputs
from .renderer import render_economic_workbook
from litman_core.resource_paths import resource_path
from litman_core.generation.models import ArtifactContext

def generate_economic_artifact(dossier: dict, run_dir: Path,
                               template_id: str = "standard-v1") -> dict:
    template_dir = resource_path("templates", "economic-simulator", template_id)
    manifest_path = template_dir / "template.yaml"
    template_path = template_dir / "template.xlsx"
    if not template_path.exists():
        raise ValueError(f"No existe la plantilla económica {template_path}")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    shutil.copy2(manifest_path, run_dir / "input" / "economic_template.yaml")
    plan = build_economic_plan(dossier, template_id)
    inputs = skeleton_economic_inputs(
        plan, manifest.get("scenario_names", ["Escenario"]),
        int(manifest.get("competitor_slots", 3)),
    )
    _write_json(run_dir / "input" / "economic_plan.json", plan)
    _write_json(run_dir / "output" / "economic_inputs.json", inputs)
    return _render(run_dir, template_path, plan, inputs, manifest)


def _render(run_dir: Path, template_path: Path, plan: dict, inputs: dict, manifest: dict) -> dict:
    output = run_dir / "output" / "simulador_economico.xlsx"
    validation = render_economic_workbook(template_path, plan, inputs, output)
    calculations = {scenario["id"]: calculate_scenario(plan, scenario)
                    for scenario in inputs.get("scenarios", [])}
    pending = _pending(plan, inputs)
    validation["calculations"] = calculations
    _write_json(run_dir / "output" / "economic_pending.json", pending)
    _write_json(run_dir / "output" / "economic_validation.json", validation)
    return {
        "document": str(output), "validation": validation,
        "pending_count": len(pending), "template_id": manifest["id"],
        "template_version": manifest["version"],
    }


def _pending(plan: dict, inputs: dict) -> list[dict]:
    items = [{"type": "warning", "description": item} for item in plan.get("warnings", [])]
    if not plan.get("price_formula", {}).get("supported"):
        items.append({"type": "unsupported_formula",
                      "description": "Implementar o revisar manualmente la fórmula económica."})
    for scenario in inputs.get("scenarios", []):
        next_bidder = next((item for item in scenario.get("bidders", []) if item.get("name") == "NEXT"), None)
        if next_bidder and next_bidder.get("price") is None:
            items.append({"type": "company_input", "scenario_id": scenario["id"],
                          "description": "Definir el precio ofertado por NEXT."})
        if next_bidder:
            if "technical_score" in next_bidder:
                if next_bidder.get("technical_score") is None:
                    items.append({"type": "company_input", "scenario_id": scenario["id"],
                                  "description": "Definir la puntuación técnica esperada de NEXT."})
            else:  # v1 compatibility: retain the old criterion-specific pending information.
                missing = [item["id"] for item in plan.get("criteria", [])
                           if next_bidder.get("criterion_scores", {}).get(item["id"]) is None]
                if missing:
                    items.append({"type": "company_input", "scenario_id": scenario["id"],
                                  "description": "Definir las puntuaciones esperadas de NEXT.",
                                  "criterion_ids": missing})
    return items


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

class EconomicSimulatorGenerator:
    id = "economic-simulator"
    version = "economic-simulator-generator-v2"

    def generate(self, context: ArtifactContext) -> dict:
        return self._result(generate_economic_artifact(context.dossier, context.run_dir, context.economic_template_id), context.run_dir)

    def _result(self, result: dict, run_dir: Path) -> dict:
        pending_path = run_dir / "output" / "economic_pending.json"
        pending = json.loads(pending_path.read_text(encoding="utf-8")) if pending_path.exists() else []
        return {"id": self.id, "generator_version": self.version, "documents": [result["document"]],
                "validation": result["validation"], "pending": pending, "metadata": {
                    "format": "xlsx", "template_id": result["template_id"],
                    "template_version": result["template_version"], "generation": result,
                    "manifest_fields": {"economic_generation": result}}}
