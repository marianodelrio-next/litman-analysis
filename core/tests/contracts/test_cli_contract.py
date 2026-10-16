from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import jsonschema
import pytest

from litman_core import cli
from litman_core.errors import CORE_ERROR_CODES
from litman_core.infrastructure.storage.common import (
    ROLE_BID_PREPARATION_GUIDE,
    ROLE_ECONOMIC_SIMULATOR,
    ROLE_OPPORTUNITY_REPORT,
    ROLE_RUN_FILE,
    ROLE_TECHNICAL_DOCUMENT,
    ROLE_TECHNICAL_SUMMARY,
)

CONTRACTS = Path(__file__).parents[2].parent / "docs" / "contracts"
RESULT_SCHEMA = json.loads((CONTRACTS / "core-result.schema.json").read_text(encoding="utf-8"))
INFO_SCHEMA = json.loads((CONTRACTS / "core-info.schema.json").read_text(encoding="utf-8"))
EXAMPLES = CONTRACTS / "examples"


@pytest.mark.parametrize("name", sorted(p.name for p in EXAMPLES.glob("*.json")))
def test_each_example_validates_against_the_result_schema(name):
    payload = json.loads((EXAMPLES / name).read_text(encoding="utf-8"))
    jsonschema.validate(payload, RESULT_SCHEMA)


def test_schema_error_codes_match_the_closed_set():
    codes = set(RESULT_SCHEMA["$defs"]["failure"]["properties"]["error"]["properties"]["code"]["enum"])
    assert codes == set(CORE_ERROR_CODES)


def test_schema_roles_match_common_module_roles():
    roles = set(RESULT_SCHEMA["$defs"]["artifact"]["properties"]["role"]["enum"])
    assert roles == {
        ROLE_OPPORTUNITY_REPORT,
        ROLE_TECHNICAL_SUMMARY,
        ROLE_BID_PREPARATION_GUIDE,
        ROLE_TECHNICAL_DOCUMENT,
        ROLE_ECONOMIC_SIMULATOR,
        ROLE_RUN_FILE,
    }


def _artifact(role: str, name: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, name=name, uri=f"file:///run/{name}", checksum="0" * 64)


@pytest.mark.parametrize("job_type,artifacts", [
    ("assessment", [(ROLE_OPPORTUNITY_REPORT, "ficha_oportunidad.pdf")]),
    ("detailed-analysis", [
        (ROLE_TECHNICAL_SUMMARY, "resumen_tecnico.docx"),
        (ROLE_BID_PREPARATION_GUIDE, "guia_preparacion_oferta.docx"),
        (ROLE_TECHNICAL_DOCUMENT, "memoria_tecnica.docx"),
        (ROLE_ECONOMIC_SIMULATOR, "simulador_economico.xlsx"),
    ]),
])
def test_real_cli_success_output_validates_against_schema(tmp_path, monkeypatch, capsys, job_type, artifacts):
    config = tmp_path / "config.toml"
    config.write_text(f"[job]\nid='run-id'\ntype='{job_type}'\n[input]\nlocation='case'\n[output]\ndirectory='out'\n", encoding="utf-8")
    (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    produced = [_artifact(role, name) for role, name in artifacts]
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            from pathlib import Path as _Path
            return SimpleNamespace(job_id=request.job_id, publication_id="run-id-x", status="succeeded", local_path=_Path("/run"), artifacts=produced, remote=None)
    monkeypatch.setattr(cli, "JobRunner", Runner)
    cli.main(["run"])
    payload = json.loads(capsys.readouterr().out)
    jsonschema.validate(payload, RESULT_SCHEMA)


@pytest.mark.parametrize("code", CORE_ERROR_CODES)
def test_real_cli_failure_output_validates_against_schema(tmp_path, monkeypatch, capsys, code):
    from litman_core.errors import CoreError
    config = tmp_path / "config.toml"
    config.write_text("[job]\nid='run-id'\ntype='assessment'\n[input]\nlocation='case'\n[output]\ndirectory='out'\n", encoding="utf-8")
    (tmp_path / "case").mkdir(); monkeypatch.chdir(tmp_path)
    class Runner:
        def __init__(self, settings): pass
        def run(self, request):
            from pathlib import Path as _Path
            raise CoreError(code, "mensaje", _Path("/run"))
    monkeypatch.setattr(cli, "JobRunner", Runner)
    with pytest.raises(SystemExit):
        cli.main(["run"])
    payload = json.loads(capsys.readouterr().out)
    jsonschema.validate(payload, RESULT_SCHEMA)


def test_real_cli_info_output_validates_against_schema(capsys):
    cli.main(["info"])
    payload = json.loads(capsys.readouterr().out)
    jsonschema.validate(payload, INFO_SCHEMA)
