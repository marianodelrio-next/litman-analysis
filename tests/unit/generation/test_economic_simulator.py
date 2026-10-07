import json
import zipfile
from pathlib import Path

from openpyxl import load_workbook

from litman_analysis.generation.service import generate_documents
from litman_analysis.generation.economic_simulator.calculator import calculate_scenario
from litman_analysis.generation.economic_simulator.planner import build_economic_plan
from litman_analysis.generation.economic_simulator.generator import render_existing_economic_run
from litman_analysis.resource_paths import RESOURCE_ROOT

from conftest import dossier
RESOURCES = RESOURCE_ROOT


def test_economic_simulator_is_traceable_and_rerenderable(tmp_path: Path) -> None:
    dossier_path = tmp_path / "case" / "detailed-analysis" / "run-1" / "output" / "dossier.json"
    dossier_path.parent.mkdir(parents=True)
    dossier_path.write_text(json.dumps(dossier(), ensure_ascii=False), encoding="utf-8")
    run_dir = tmp_path / "generation-run"
    manifest = generate_documents(
        dossier_path, output_dir=run_dir, artifacts=["economic-simulator"], provider=None,
    )
    output = run_dir / "output" / "simulador_economico.xlsx"
    assert output.exists()
    assert manifest["economic_generation"]["template_version"] == "1.0.0"
    assert (run_dir / "input" / "economic_plan.json").exists()
    assert (run_dir / "output" / "economic_inputs.json").exists()
    assert (run_dir / "output" / "economic_pending.json").exists()
    assert (run_dir / "output" / "economic_validation.json").exists()
    workbook = load_workbook(output, data_only=False)
    assert workbook.sheetnames == ["Simulador", "Criterios y ayuda", "Comprobaciones", "Pendientes"]
    assert "Servicio de analítica" in "\n".join(
        str(cell.value) for row in workbook["Simulador"].iter_rows() for cell in row
        if cell.value is not None
    )
    inputs_path = run_dir / "output" / "economic_inputs.json"
    inputs = json.loads(inputs_path.read_text(encoding="utf-8"))
    inputs["scenarios"][0]["bidders"][0]["price"] = 150000
    inputs["scenarios"][0]["bidders"][0]["criterion_scores"] = {"criterion-001": 90}
    inputs_path.write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
    result = render_existing_economic_run(run_dir)
    assert result["validation"]["valid"]
    assert result["validation"]["calculations"]["scenario-01"][0]["total_points"] == 100


def test_economic_template_is_neutral() -> None:
    template = RESOURCES / "templates" / "economic-simulator" / "standard-v1" / "template.xlsx"
    with zipfile.ZipFile(template) as archive:
        xml = "\n".join(
            archive.read(name).decode("utf-8", errors="ignore")
            for name in archive.namelist() if name.endswith(".xml")
        )
    for term in ("UIB", "21/26", "NEXT", "DAMA", "206611"):
        assert term not in xml


def test_economic_calculator_detects_possible_abnormal_offer() -> None:
    plan = build_economic_plan(dossier())
    scenario = {
        "bidders": [
            {"name": "NEXT", "price": 150000, "criterion_scores": {"criterion-001": 90}},
            {"name": "A", "price": 180000, "criterion_scores": {"criterion-001": 90}},
            {"name": "B", "price": 190000, "criterion_scores": {"criterion-001": 90}},
            {"name": "C", "price": 200000, "criterion_scores": {"criterion-001": 90}},
        ]
    }
    result = calculate_scenario(plan, scenario)
    assert result[0]["price_points"] == 10
    assert result[0]["possible_abnormal"] is True


def test_economic_plan_normalizes_percentage_bases() -> None:
    value = dossier()
    value["simulador_economico"]["baja_anormal"]["reglas"][0]["base"] = 85
    value["simulador_economico"]["baja_anormal"]["maximo_cualitativo"] = 93
    plan = build_economic_plan(value)
    assert plan["abnormally_low"]["reglas"][0]["base"] == 0.85
    assert any("normalizada" in warning for warning in plan["warnings"])
    assert any("suman 90" in warning and "usa 93" in warning for warning in plan["warnings"])
