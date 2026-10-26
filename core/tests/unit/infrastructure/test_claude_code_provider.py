import json
import subprocess
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from litman_core.application.ports.llm import output_paths_for_run
from litman_core.resource_paths import resource_path
from litman_core.infrastructure.llm.claude_code import ClaudeCodeProvider
import litman_core.infrastructure.llm.claude_code as claude_code


def _run(tmp_path, monkeypatch, payload, *, returncode=0, stderr=""):
    seen = {}
    class Result:
        def __init__(self):
            self.stdout, self.stderr, self.returncode = json.dumps(payload) if not isinstance(payload, str) else payload, stderr, returncode
    def fake_run(argv, **kwargs):
        seen.update(argv=argv, **kwargs)
        return Result()
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    schema = tmp_path / "schema.json"; schema.write_text('{"type":"object"}')
    paths = output_paths_for_run(tmp_path / "run", "test")
    return ClaudeCodeProvider(binary="claude", model="sonnet", timeout_seconds=2).generate(
        instructions="system", prompt="prompt", schema_path=schema, case_dir=tmp_path, output_paths=paths), seen, paths


def test_valid_response_argv_stdin_and_sanitized_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "hidden")
    result, seen, paths = _run(tmp_path, monkeypatch, {"structured_output": {"ok": True}, "session_id": "s", "usage": {"input_tokens": 1}})
    assert result.data == {"ok": True}
    assert "--tools" in seen["argv"] and seen["argv"][seen["argv"].index("--tools") + 1] == "Read"
    assert seen["input"] == "system\n\n---\n\nprompt"
    assert "SECRET_TOKEN" not in seen["env"]
    assert all(p.exists() for p in (paths.events, paths.stderr, paths.response, paths.summary))


def test_windows_environment_is_allowlisted_case_insensitively(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_code.platform, "system", lambda: "Windows")
    monkeypatch.setenv("systemroot", r"C:\\Windows")
    monkeypatch.setenv("SECRET_TOKEN", "hidden")
    _, seen, _ = _run(tmp_path, monkeypatch, {"structured_output": {"ok": True}})
    assert seen["env"]["systemroot"] == r"C:\\Windows"
    assert "SECRET_TOKEN" not in seen["env"]
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace"


def test_windows_rejects_cmd_launcher_before_schema_or_process(tmp_path, monkeypatch):
    monkeypatch.setattr(claude_code.platform, "system", lambda: "Windows")
    monkeypatch.setattr("shutil.which", lambda _: r"C:\\tools\\claude.cmd")
    schema = tmp_path / "schema.json"; schema.write_text("{}", encoding="utf-8")
    paths = output_paths_for_run(tmp_path / "run", "cmd")
    with pytest.raises(RuntimeError, match=".exe"):
        ClaudeCodeProvider().generate(instructions="", prompt="", schema_path=schema, case_dir=tmp_path, output_paths=paths)


def test_schema_argument_removes_draft_metadata_but_preserves_constraints(tmp_path, monkeypatch):
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://example.test/schema",
        "$defs": {"item": {"type": "string"}},
        "type": "object",
        "required": ["name"],
        "properties": {"name": {"$ref": "#/$defs/item"}},
    }
    seen = {}

    class Result:
        stdout, stderr, returncode = json.dumps({"structured_output": {"ok": True}}), "", 0

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        return Result()

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", fake_run)
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")
    paths = output_paths_for_run(tmp_path / "run", "schema")
    ClaudeCodeProvider().generate(instructions="", prompt="", schema_path=schema_path, case_dir=tmp_path, output_paths=paths)

    passed = json.loads(seen["argv"][seen["argv"].index("--json-schema") + 1])
    assert "$schema" not in passed
    assert passed["$id"] == schema["$id"]
    assert passed["$defs"] == schema["$defs"]
    assert passed["required"] == schema["required"]
    assert json.loads(schema_path.read_text(encoding="utf-8")) == schema


def _strict_violations(node, path="#"):
    """Union types and unlisted ``required`` names that Ajv strict mode rejects."""
    found = []
    if isinstance(node, list):
        for index, item in enumerate(node):
            found += _strict_violations(item, f"{path}/{index}")
    elif isinstance(node, dict):
        types = node.get("type")
        if isinstance(types, list) and len(types) > 1 and not (len(types) == 2 and "null" in types):
            found.append(f"{path}/type")
        if isinstance(node.get("required"), list) and "additionalProperties" not in node:
            found += [f"{path}/required/{name}" for name in node["required"] if name not in node.get("properties", {})]
        for key, value in node.items():
            if key not in ("const", "enum", "default", "examples"):
                found += _strict_violations(value, f"{path}/{key}")
    return found


def test_union_types_and_unlisted_required_names_become_equivalent_strict_forms(tmp_path):
    schema = {
        "type": "object", "additionalProperties": False, "required": ["page", "kind"],
        "properties": {"page": {"type": ["integer", "string", "null"]},
                       "note": {"type": ["string", "null"]},
                       "kind": {"enum": [{"type": ["a", "b", "c"]}]}},
        "allOf": [{"if": {"properties": {"page": {"const": 0}}}, "then": {"required": ["note"]}}],
    }
    schema_path = tmp_path / "schema.json"
    schema_path.write_text(json.dumps(schema), encoding="utf-8")

    passed = json.loads(ClaudeCodeProvider._prepare_schema(schema_path))

    assert passed["properties"]["page"] == {"anyOf": [{"type": "integer"}, {"type": "string"}, {"type": "null"}]}
    assert passed["properties"]["note"] == {"type": ["string", "null"]}
    assert passed["properties"]["kind"] == schema["properties"]["kind"]
    assert passed["allOf"][0]["then"] == {"required": ["note"], "properties": {"note": {}}}
    assert _strict_violations(passed) == []
    kind = {"type": ["a", "b", "c"]}
    for instance in ({"page": 3, "kind": kind}, {"page": "iv", "kind": kind}, {"page": None, "kind": kind},
                     {"page": 1.5, "kind": kind}, {"page": 0, "kind": kind}, {"page": 0, "note": "x", "kind": kind},
                     {"page": 1, "kind": kind, "extra": 1}):
        assert Draft202012Validator(passed).is_valid(instance) == Draft202012Validator(schema).is_valid(instance)


@pytest.mark.parametrize("name", ["assessment.schema.json", "detailed-analysis.schema.json",
                                  "technical-content.schema.json"])
def test_packaged_schemas_sent_to_claude_have_no_strict_mode_violations(name):
    path = resource_path("schemas", name)
    assert _strict_violations(json.loads(ClaudeCodeProvider._prepare_schema(path))) == []


def test_invalid_schema_creates_diagnostic_and_does_not_run_cli(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("CLI should not run"))
    schema_path = tmp_path / "schema.json"
    schema_path.write_text("not-json", encoding="utf-8")
    paths = output_paths_for_run(tmp_path / "run", "invalid-schema")

    with pytest.raises(RuntimeError, match="preparar el schema"):
        ClaudeCodeProvider().generate(instructions="", prompt="", schema_path=schema_path, case_dir=tmp_path, output_paths=paths)

    assert all(p.exists() for p in (paths.events, paths.stderr, paths.response, paths.summary))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["status"] == "schema"
    assert summary["error"] == "schema"


@pytest.mark.parametrize("payload", [{}, {"structured_output": "x"}, {"structured_output": None}])
def test_missing_or_non_object_structured_output_is_diagnostic(tmp_path, monkeypatch, payload):
    with pytest.raises(RuntimeError): _run(tmp_path, monkeypatch, payload)
    paths = output_paths_for_run(tmp_path / "run", "test")
    assert all(p.exists() for p in (paths.events, paths.stderr, paths.response, paths.summary))
    summary = json.loads(paths.summary.read_text(encoding="utf-8"))
    assert summary["error"] == "missing_structured_output"
    assert summary["provider"] == "claude-code"
    assert summary["model"] == "sonnet"
    assert "duration_seconds" in summary and "output" in summary and "usage" in summary


def test_invalid_json_and_process_failures_are_classified(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError): _run(tmp_path, monkeypatch, "not-json")
    summary = json.loads((tmp_path / "run" / "output" / "llm-summary-test.json").read_text(encoding="utf-8"))
    assert summary["provider"] == "claude-code"
    assert summary["model"] == "sonnet"
    assert isinstance(summary["duration_seconds"], float)
    assert summary["output"].endswith("llm-response-test.json")
    assert summary["usage"] == {}
    assert summary["error"] == "invalid_json"
    with pytest.raises(RuntimeError) as auth_exc: _run(tmp_path, monkeypatch, {"error": "auth"}, returncode=1, stderr="Please login")
    assert auth_exc.value.code == "llm_unavailable"


def test_binary_missing_creates_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    schema = tmp_path / "schema.json"; schema.write_text("{}")
    paths = output_paths_for_run(tmp_path / "run", "missing")
    with pytest.raises(RuntimeError) as exc_info: ClaudeCodeProvider().generate(instructions="", prompt="", schema_path=schema, case_dir=tmp_path, output_paths=paths)
    assert exc_info.value.code == "llm_unavailable"
    assert all(p.exists() for p in (paths.events, paths.stderr, paths.response, paths.summary))


def test_timeout_creates_diagnostics(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired(kwargs.get("args", args[0]), 1, stderr="timeout")
    monkeypatch.setattr(subprocess, "run", timeout)
    schema = tmp_path / "schema.json"; schema.write_text("{}")
    paths = output_paths_for_run(tmp_path / "run", "timeout")
    with pytest.raises(RuntimeError): ClaudeCodeProvider(timeout_seconds=1).generate(instructions="", prompt="", schema_path=schema, case_dir=tmp_path, output_paths=paths)
    assert all(p.exists() for p in (paths.events, paths.stderr, paths.response, paths.summary))
