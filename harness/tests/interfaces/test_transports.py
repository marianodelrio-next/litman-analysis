from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import litman_harness
from litman_harness.interfaces import cli, mcp


def run_cli(capsys, operation: str, args: dict | None = None) -> tuple[int, dict]:
    argv = [operation] if args is None else [operation, "--json", json.dumps(args)]
    code = 0
    try:
        cli.main(argv)
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    stream = captured.err if code else captured.out
    assert (captured.out if code else captured.err) == ""
    return code, json.loads(stream)


def call_mcp(name: str, arguments: dict) -> tuple[bool, dict]:
    response = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                      "params": {"name": name, "arguments": arguments}}))
    result = response["result"]
    return result["isError"], json.loads(result["content"][0]["text"])


def without_ids(envelope: dict) -> dict:
    result = dict(envelope["result"])
    result.pop("plan_id"), result.pop("operation_id")
    return {**envelope, "result": result}


def test_cli_and_mcp_return_the_same_envelope_for_queries_and_errors(harness_env, capsys):
    cases = [("identity", {}), ("inspect", {"folder_id": "root"}), ("status", {"folder_id": "root"}),
             ("inspect", {"folder_id": "missing"}), ("inspect", {}),
             ("apply_incorporation", {"plan_id": "a" * 64}), ("recover", {"operation_id": "unknown-operation"}),
             ("read_document", {"folder_id": "root", "file_id": "source", "offset": 0}),
             ("read_document", {"folder_id": "root", "file_id": "source", "offset": "0"}),
             ("preview_summary", {"folder_id": "root",
                                  "items": [{"key": "objeto", "value": "x", "source_file_id": "source"}]}),
             ("apply_summary", {"plan_id": "a" * 64}),
             ("read_google_doc", {"folder_id": "root", "document_id": "source"}),
             ("preview_document_edit", {"folder_id": "root", "document_id": "source",
                                        "operations": [{"op": "append", "text": "x"}]}),
             ("apply_document_edit", {"plan_id": "a" * 64}),
             ("preview_document_creation", {"folder_id": "root", "parent_folder_id": "root", "name": "Notas",
                                            "source_file_id": "source"}),
             ("apply_document_creation", {"plan_id": "a" * 64})]
    for name, arguments in cases:
        code, cli_envelope = run_cli(capsys, name.replace("_", "-"), arguments)
        is_error, mcp_envelope = call_mcp(name, arguments)
        assert cli_envelope == mcp_envelope
        assert is_error is (not cli_envelope["ok"]) and (code == 2) is is_error
    assert run_cli(capsys, "inspect", {})[1]["error"]["code"] == "invalid_request"
    assert run_cli(capsys, "status", {"folder_id": "root"})[1]["result"]["state"] == "unadopted"


def test_cli_and_mcp_share_plans_and_their_application(harness_env, capsys):
    request = {"folder_id": "root", "original_ids": ["source"]}
    _, cli_plan = run_cli(capsys, "preview-incorporation", request)
    _, mcp_plan = call_mcp("preview_incorporation", request)
    assert without_ids(cli_plan) == without_ids(mcp_plan)
    plan_id = cli_plan["result"]["plan_id"]
    _, cli_apply = run_cli(capsys, "apply-incorporation", {"plan_id": plan_id})
    _, mcp_apply = call_mcp("apply_incorporation", {"plan_id": plan_id})
    assert cli_apply == mcp_apply
    assert cli_apply["result"]["status"] == "pending_concurrency_gate"
    assert cli_apply["result"]["writes"] is False


def test_cli_json_is_optional_and_invalid_json_is_invalid_request(harness_env, capsys):
    assert run_cli(capsys, "identity")[1]["result"]["permission_id"] == "person-1"
    with pytest.raises(SystemExit) as raised:
        cli.main(["identity", "--json", "{"])
    assert raised.value.code == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "invalid_request"


def test_mcp_protocol_methods():
    init = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                             "clientInfo": {"name": "t", "version": "0"}}}))
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert init["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert init["result"]["serverInfo"] == {"name": "litman-harness", "version": litman_harness.__version__}
    future = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 2, "method": "initialize",
                                    "params": {"protocolVersion": "2099-01-01"}}))
    assert future["result"]["protocolVersion"] == "2025-06-18"
    assert mcp.handle(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})) is None
    assert mcp.handle(json.dumps({"jsonrpc": "2.0", "method": "tools/call", "params": {"name": "identity"}})) is None
    assert mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"}))["result"] == {}
    assert mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 4, "method": "nope"}))["error"]["code"] == -32601
    assert mcp.handle("{not json")["error"]["code"] == -32700
    assert mcp.handle("[]")["error"]["code"] == -32600
    unknown = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 5, "method": "tools/call",
                                     "params": {"name": "publish", "arguments": {}}}))
    assert unknown["error"]["code"] == -32602
    bad_arguments = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                           "params": {"name": "identity", "arguments": []}}))
    assert bad_arguments["error"]["code"] == -32602


def test_mcp_lists_tools_and_reports_configuration_errors_as_is_error(unconfigured_env):
    tools = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]
    assert {tool["name"] for tool in tools} >= {"inspect", "status", "preview_analysis", "execute_analysis",
                                                "preview_publication", "apply_publication", "discard_analysis"}
    assert "login" not in {tool["name"] for tool in tools}
    assert all(tool["inputSchema"]["type"] == "object" for tool in tools)
    is_error, envelope = call_mcp("identity", {})
    assert is_error is True
    assert envelope["error"]["code"] == "oauth_login_required"


def test_mcp_stdio_handshake_in_real_subprocess(harness_env):
    env = {key: value for key, value in os.environ.items() if not key.startswith("LITMAN_HARNESS_")}
    env.update(harness_env)
    env["PYTHONPATH"] = str(Path(litman_harness.__file__).parents[1])
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "inspect",
                                                                     "arguments": {"folder_id": "root"}}},
    ]
    stdin = "".join(json.dumps(message) + "\n" for message in messages) + "{broken\n"
    completed = subprocess.run([sys.executable, "-m", "litman_harness.interfaces.mcp"], input=stdin,
                               capture_output=True, text=True, env=env, timeout=60, check=True)
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2, 3, None]
    assert responses[0]["result"]["protocolVersion"] == "2025-06-18"
    assert all("inputSchema" in tool for tool in responses[1]["result"]["tools"])
    call = responses[2]["result"]
    assert call["isError"] is False
    envelope = json.loads(call["content"][0]["text"])
    assert envelope["ok"] is True and envelope["result"]["candidates"]["originals"] == ["source"]
    assert responses[3]["error"]["code"] == -32700


def test_install_is_cli_only_and_not_exposed_as_an_mcp_operation(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "home" / ".codex"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = Path(litman_harness.__file__).parents[3]

    try:
        cli.main(["install", "--app", "codex", "--source", str(repo)])
        code = 0
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    payload = json.loads(captured.out if code == 0 else captured.err)
    assert code == 0 and payload["ok"] is True

    try:
        cli.main(["install", "--app", "codex"])
        assert False, "debía fallar sin --source"
    except SystemExit as exc:
        assert exc.code == 2
    capsys.readouterr()

    assert "install" not in [t["name"] for t in mcp.handle(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}))["result"]["tools"]]


def test_uninstall_without_manifest_is_ok(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    try:
        cli.main(["uninstall"])
        code = 0
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    payload = json.loads(captured.out if code == 0 else captured.err)
    assert code == 0 and payload == {"ok": True, "result": {"removed": [], "kept": [], "failed": []}}


def test_uninstall_with_failed_items_is_an_error_envelope(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    fake_result = {"removed": ["skill:resumir-licitacion"], "kept": [], "failed": ["skill:conectar-licitacion"]}
    monkeypatch.setattr(cli.installation, "uninstall", lambda **kwargs: fake_result)

    try:
        cli.main(["uninstall"])
        code = 0
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    payload = json.loads(captured.out if code == 0 else captured.err)
    assert code == 2
    assert payload["ok"] is False
    assert payload["error"]["code"] == "uninstall_incomplete"
    assert payload["error"]["details"] == fake_result


def test_oauth_client_flag_only_works_without_app(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    repo = Path(litman_harness.__file__).parents[3]
    client = tmp_path / "client_secret.json"
    client.write_text(json.dumps({"installed": {"client_id": "a", "client_secret": "b",
                                                  "auth_uri": "https://x", "token_uri": "https://y"}}))

    try:
        cli.main(["install", "--oauth-client", str(client)])
        code = 0
    except SystemExit as exc:
        code = exc.code
    captured = capsys.readouterr()
    payload = json.loads(captured.out if code == 0 else captured.err)
    assert code == 0 and payload["result"]["oauth_client"] == {"ok": True, "imported": True}


def test_login_is_cli_only_and_uses_the_configured_provider(harness_env, capsys, monkeypatch):
    from litman_harness.interfaces import assembly

    class Provider:
        def login(self):
            return {"logged_in": True, "scopes": ["drive"], "token_exposed": False}

    monkeypatch.setattr(assembly, "oauth_provider", lambda env=None: Provider())
    assert run_cli(capsys, "login")[1] == {"ok": True, "result": {"logged_in": True, "scopes": ["drive"],
                                                                   "token_exposed": False}}
    unknown = mcp.handle(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                     "params": {"name": "login", "arguments": {}}}))
    assert unknown["error"]["code"] == -32602
