from __future__ import annotations

import importlib.util
from pathlib import Path

import litman_harness
from litman_harness.errors import HarnessError
from litman_harness.interfaces.tools import invoke, registry, tool_descriptors

OPERATIONS = {"identity", "diagnose", "inspect", "status", "preview_incorporation", "apply_incorporation",
              "preview_analysis", "execute_analysis", "discard_analysis", "preview_publication", "apply_publication",
              "read_document", "preview_summary", "apply_summary", "recover", "setup", "read_google_doc",
              "preview_document_edit", "apply_document_edit", "preview_document_creation", "apply_document_creation",
              "list_folder", "search_in_dossier", "get_file_info", "read_file", "list_comments"}


def test_registry_exposes_operations_with_schema_and_kind():
    assert set(registry()) == OPERATIONS and "login" not in registry()
    for descriptor in tool_descriptors():
        assert descriptor["inputSchema"]["type"] == "object"
        assert descriptor["description"].startswith(("Consulta", "Mutación"))
    incorporation = registry()["preview_incorporation"].input_schema["properties"]
    assert incorporation["overwrite_context"]["type"] == "boolean"
    preview_analysis = registry()["preview_analysis"].input_schema
    assert "provider" not in preview_analysis["properties"]
    setup_schema = registry()["setup"].input_schema
    assert setup_schema["required"] == ["provider"]
    assert "codex" in setup_schema["properties"]["provider"]["enum"]
    assert {tool.name for tool in registry().values() if tool.mutates} == {"apply_incorporation", "execute_analysis",
                                                                              "discard_analysis", "apply_publication",
                                                                              "apply_summary", "setup",
                                                                              "apply_document_edit",
                                                                              "apply_document_creation"}


DESTRUCTIVE = {"apply_document_edit", "apply_file_changes", "apply_sheet_edit", "apply_summary",
               "apply_incorporation", "discard_analysis"}


def test_tools_declare_mcp_annotations_derived_from_their_kind():
    for descriptor in tool_descriptors():
        tool = registry()[descriptor["name"]]
        annotations = descriptor["annotations"]
        assert annotations["readOnlyHint"] is (not tool.mutates)
        assert annotations["destructiveHint"] is (tool.name in DESTRUCTIVE)
        assert annotations["openWorldHint"] is False
        if tool.mutates:
            assert annotations["idempotentHint"] is True
    for name in ("preview_document_edit", "preview_analysis", "preview_incorporation"):
        assert registry()[name].descriptor()["annotations"]["readOnlyHint"] is True
    assert DESTRUCTIVE & set(registry()) <= {tool.name for tool in registry().values() if tool.mutates}



def test_invalid_arguments_are_invalid_request_before_building_services():
    def factory():
        raise AssertionError("services must not be built for invalid arguments")

    for args in ({}, {"folder_id": 3}, {"folder_id": "root", "extra": True}, []):
        envelope = invoke("inspect", args, factory)
        assert envelope["ok"] is False and envelope["error"]["code"] == "invalid_request"
    envelope = invoke("preview_analysis", {"folder_id": "r", "original_ids": ["a", 1], "job_type": "assessment",
                                           "provider": "codex"}, factory)
    assert envelope["error"]["code"] == "invalid_request"
    envelope = invoke("preview_analysis", {"folder_id": "r", "original_ids": ["a"], "job_type": "assessment",
                                           "provider": "other"}, factory)
    assert envelope["error"]["code"] == "invalid_request"


def test_document_tools_declare_closed_operations_and_reject_bad_arguments_before_services():
    def factory():
        raise AssertionError("services must not be built for invalid arguments")

    operations = registry()["preview_document_edit"].input_schema["properties"]["operations"]
    assert operations["maxItems"] == 20 and operations["items"]["additionalProperties"] is False
    assert operations["items"]["properties"]["op"]["enum"] == ["replace_text", "insert_after", "append"]
    assert registry()["read_google_doc"].input_schema["required"] == ["folder_id", "document_id"]
    creation = registry()["preview_document_creation"].input_schema
    assert creation["required"] == ["folder_id", "parent_folder_id", "name"]
    assert {"text", "source_file_id"} <= set(creation["properties"])
    for name, args in (("read_google_doc", {"folder_id": "root", "document_id": 1}),
                       ("preview_document_edit", {"folder_id": "root", "document_id": "d", "operations": {}}),
                       ("preview_document_edit", {"folder_id": "root", "document_id": "d", "operations": ["x"]}),
                       ("apply_document_edit", {"plan_id": "p", "operations": []}),
                       ("preview_document_creation", {"folder_id": "root", "parent_folder_id": "root"}),
                       ("preview_document_creation", {"folder_id": "root", "parent_folder_id": "root", "name": "n",
                                                      "text": 1}),
                       ("apply_document_creation", {})):
        assert invoke(name, args, factory)["error"]["code"] == "invalid_request"


def test_file_tools_are_read_only_queries_with_validated_arguments():
    from litman_harness.dossier.files import KINDS

    def factory():
        raise AssertionError("services must not be built for invalid arguments")

    for name in ("list_folder", "search_in_dossier", "get_file_info", "read_file", "list_comments"):
        tool = registry()[name]
        assert tool.mutates is False and tool.descriptor()["annotations"]["readOnlyHint"] is True
        assert tool.description.startswith("Consulta (no escribe)")
        assert invoke(name, {}, factory)["error"]["code"] == "invalid_request"
    assert registry()["search_in_dossier"].input_schema["properties"]["kind"]["enum"] == list(KINDS)
    for name, args in (("read_file", {"folder_id": "r", "file_id": "f", "offset": "0"}),
                       ("list_comments", {"folder_id": "r", "file_id": "f", "include_resolved": "yes"}),
                       ("search_in_dossier", {"folder_id": "r", "query": "x", "kind": "video"}),
                       ("list_folder", {"folder_id": "r", "parent_folder_id": 3})):
        assert invoke(name, args, factory)["error"]["code"] == "invalid_request", args


def test_file_tools_call_the_file_service_with_their_arguments():
    calls = []

    class Files:
        def list_folder(self, *args):
            calls.append(("list_folder", args))
            return {"ok": 1}

        def search_in_dossier(self, *args):
            calls.append(("search_in_dossier", args))
            return {}

        def get_file_info(self, *args):
            calls.append(("get_file_info", args))
            return {}

        def read_file(self, *args):
            calls.append(("read_file", args))
            return {}

        def list_comments(self, *args):
            calls.append(("list_comments", args))
            return {}

    class Services:
        files = Files()

    for name, args in (("list_folder", {"folder_id": "r"}), ("list_folder", {"folder_id": "r", "parent_folder_id": "p"}),
                       ("search_in_dossier", {"folder_id": "r", "query": "x", "kind": "pdf"}),
                       ("get_file_info", {"folder_id": "r", "file_id": "f"}),
                       ("read_file", {"folder_id": "r", "file_id": "f"}),
                       ("read_file", {"folder_id": "r", "file_id": "f", "offset": 5}),
                       ("list_comments", {"folder_id": "r", "file_id": "f", "include_resolved": True})):
        assert invoke(name, args, Services)["ok"] is True
    assert calls == [("list_folder", ("r", None)), ("list_folder", ("r", "p")),
                     ("search_in_dossier", ("r", "x", "pdf")), ("get_file_info", ("r", "f")),
                     ("read_file", ("r", "f", 0)), ("read_file", ("r", "f", 5)),
                     ("list_comments", ("r", "f", True))]


def test_preview_analysis_no_longer_accepts_a_provider_argument():
    def factory():
        raise AssertionError("services must not be built for invalid arguments")

    envelope = invoke("preview_analysis", {"folder_id": "r", "original_ids": ["a"], "job_type": "assessment",
                                           "provider": "codex"}, factory)
    assert envelope["ok"] is False and envelope["error"]["code"] == "invalid_request"
    assert envelope["error"]["details"]["unknown"] == ["provider"]


def test_harness_errors_keep_their_code_and_unknown_operations_fail():
    def factory():
        raise HarnessError("adapter_not_configured", "sin configurar", details={"hint": "x"})

    assert invoke("identity", {}, factory) == {"ok": False, "error": {
        "code": "adapter_not_configured", "message": "sin configurar", "details": {"hint": "x"}}}
    assert invoke("publish", {}, factory)["error"]["code"] == "unknown_operation"


def test_diagnose_works_without_configuration(unconfigured_env):
    envelope = invoke("diagnose", {})
    assert envelope["ok"] is True
    report = envelope["result"]
    assert report["adapter"] == "oauth" and report["token_exposed"] is False
    assert report["shared_state"] == {"available": False, "mechanism": "unavailable"}
    assert report["oauth"]["token_present"] is False
    assert report["errors"][0]["code"] == "oauth_login_required"


def test_diagnose_reports_metadata_identity_without_paths(harness_env):
    report = invoke("diagnose", {})["result"]
    assert report["adapter"] == "metadata" and report["read_only"] is True
    assert report["identity"]["permission_id"] == "person-1"
    assert report["paths_configured"]["LITMAN_HARNESS_METADATA"] is True
    assert report["paths_configured"]["LITMAN_HARNESS_OAUTH_TOKEN"] is False
    assert isinstance(report["core_executable_found"], bool)
    assert report["shared_state"] == {"available": False, "mechanism": "unavailable"}
    assert harness_env["LITMAN_HARNESS_METADATA"] not in repr(report)


def test_execute_analysis_takes_only_plan_id(harness_env):
    envelope = invoke("execute_analysis", {"plan_id": "a" * 64, "provider": "codex"})
    assert envelope["error"]["code"] == "invalid_request"
    assert invoke("execute_analysis", {"plan_id": "a" * 64})["error"]["code"] == "unknown_plan"


def test_old_flat_modules_and_compatibility_reexports_are_gone():
    package = Path(litman_harness.__file__).parent
    for name in ("models", "service", "analysis", "drive", "configured", "cli", "mcp"):
        assert not (package / f"{name}.py").exists()
    for name in ("models", "service", "drive", "configured", "cli", "mcp"):
        assert importlib.util.find_spec(f"litman_harness.{name}") is None
    assert not hasattr(litman_harness, "ExpedienteService")


def test_local_paths_inside_checkout_are_configuration_errors(harness_env, monkeypatch):
    from litman_harness.local_paths import checkout_root
    monkeypatch.setenv("LITMAN_HARNESS_WORK_DIR", str(checkout_root() / "work"))
    assert invoke("identity", {})["error"]["code"] == "unsafe_local_path"


def test_unexpected_errors_use_the_safe_message(harness_env, monkeypatch):
    monkeypatch.setenv("LITMAN_HARNESS_OAUTH_CLIENT", "/home/p/secret-client.json")

    class Boom:
        @property
        def expediente(self):
            raise RuntimeError("leer /home/p/secret-client.json falló")

    envelope = invoke("identity", {}, Boom)
    assert envelope["error"]["code"] == "internal_error"
    assert "/home/p" not in envelope["error"]["details"]["error"]
