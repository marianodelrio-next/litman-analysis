from __future__ import annotations

import json, os, platform, shutil, subprocess, time
from pathlib import Path
from litman_core.application.ports.llm import LLMResult
from litman_core.errors import CoreError
from .codex_cli import _prepare_output_paths


def _strict_compatible(node):
    """Return an equivalent schema that Ajv strict mode accepts without ``allowUnionTypes``.

    ``{"type": [a, b, "null"]}`` becomes ``{"anyOf": [{"type": a}, {"type": b}, {"type": "null"}]}``
    (a single type plus ``null`` is allowed as is), and each ``required`` name missing from the
    same object's ``properties`` is declared with the empty schema, which constrains nothing.
    """
    if isinstance(node, list):
        return [_strict_compatible(item) for item in node]
    if not isinstance(node, dict):
        return node
    node = {key: value if key in ("const", "enum", "default", "examples") else _strict_compatible(value)
            for key, value in node.items()}
    types = node.get("type")
    if isinstance(types, list) and len(types) > 1 and not (len(types) == 2 and "null" in types) and "anyOf" not in node:
        del node["type"]
        node["anyOf"] = [{"type": kind} for kind in types]
    required = node.get("required")
    if isinstance(required, list) and "additionalProperties" not in node:
        properties = node.get("properties", {})
        missing = [name for name in required if isinstance(name, str) and name not in properties]
        if missing and isinstance(properties, dict):
            node["properties"] = {**properties, **{name: {} for name in missing}}
    return node


class ClaudeCodeProvider:
    def __init__(self, *, binary="claude", model=None, timeout_seconds=1800, config_dir=None, **_):
        self.binary, self.model, self.timeout_seconds, self.config_dir = binary, model, timeout_seconds, config_dir

    @staticmethod
    def _prepare_schema(schema_path: Path) -> str:
        """Prepare Core's schema for Claude Code's JSON-schema validator.

        Claude Code currently rejects schemas declaring the Draft 2020-12
        meta-schema.  The declaration is metadata and is not needed for the
        CLI, so remove it only from the in-memory copy sent to Claude while
        preserving the canonical schema on disk and all its constraints.
        Some Claude Code builds also compile the schema in Ajv strict mode,
        so equivalent strict-clean forms replace union types and required
        names without a local property declaration.
        """
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        if not isinstance(schema, dict):
            raise ValueError("El schema de Claude Code debe ser un objeto JSON")
        schema.pop("$schema", None)
        return json.dumps(_strict_compatible(schema), ensure_ascii=False, separators=(",", ":"))

    def generate(self, *, instructions, prompt, schema_path, case_dir, output_paths):
        _prepare_output_paths(output_paths)
        output_paths.events.touch()
        output_paths.stderr.touch()
        executable = shutil.which(self.binary)
        if executable is None:
            output_paths.response.write_text("", encoding="utf-8")
            output_paths.summary.write_text(json.dumps({"provider":"claude-code","model":self.model or "claude_default","status":"binary_missing","duration_seconds":0,"output":str(output_paths.response),"usage":{},"error":"binary_missing"}, indent=2), encoding="utf-8")
            raise CoreError("llm_unavailable", f"No se encuentra Claude Code CLI ({self.binary!r}); revisa {output_paths.summary.name}")
        if platform.system() == "Windows" and Path(executable).suffix.lower() in {".cmd", ".bat"}:
            raise CoreError("llm_unavailable", "Claude Code debe usar el binario nativo .exe en Windows; configura LITMAN_CORE_CLAUDE_BINARY con esa ruta.")
        try:
            prepared_schema = self._prepare_schema(schema_path)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            message = f"No se pudo preparar el schema para Claude Code: {exc}"
            output_paths.stderr.write_text(message, encoding="utf-8")
            output_paths.response.write_text("", encoding="utf-8")
            output_paths.summary.write_text(json.dumps({
                "provider": "claude-code",
                "model": self.model or "claude_default",
                "status": "schema",
                "duration_seconds": 0,
                "output": str(output_paths.response),
                "usage": {},
                "error": "schema",
            }, indent=2), encoding="utf-8")
            raise RuntimeError(f"No se pudo preparar el schema de Claude Code; revisa {output_paths.stderr.name}") from exc
        command = [executable, "-p", "--output-format", "json", "--json-schema", prepared_schema, "--safe-mode", "--restricted", "--permission-mode", "dontAsk", "--permission-prompts", "none", "--tools", "Read"]
        if self.model: command += ["--model", self.model]
        allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "HOME"}
        if platform.system() == "Windows":
            allowed.update({"SystemRoot", "WINDIR", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "PATHEXT", "COMSPEC"})
            allowed = {name.upper() for name in allowed}
            env = {name: value for name, value in os.environ.items() if name.upper() in allowed}
        else:
            env = {name: value for name, value in os.environ.items() if name in allowed}
        if self.config_dir: env["CLAUDE_CONFIG_DIR"] = str(self.config_dir)
        started = time.monotonic()
        try:
            result = subprocess.run(command, input=f"{instructions}\n\n---\n\n{prompt}", text=True, encoding="utf-8", errors="replace", cwd=case_dir, capture_output=True, timeout=self.timeout_seconds, env=env)
        except subprocess.TimeoutExpired as exc:
            stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            output_paths.stderr.write_text(stderr, encoding="utf-8")
            output_paths.response.write_text("", encoding="utf-8")
            output_paths.summary.write_text(json.dumps({"provider":"claude-code","model":self.model or "claude_default","status":"timeout","error":"timeout","duration_seconds":round(time.monotonic()-started,3),"output":str(output_paths.response),"usage":{}}, indent=2), encoding="utf-8")
            raise RuntimeError(f"Claude Code superó el tiempo máximo de {self.timeout_seconds} segundos") from exc
        output_paths.events.write_text(result.stdout, encoding="utf-8")
        output_paths.stderr.write_text(result.stderr, encoding="utf-8")
        if result.returncode != 0:
            reason = "authentication" if any(x in result.stderr.lower() for x in ("auth", "login", "unauthorized")) else ("schema" if "schema" in result.stderr.lower() else "process_failed")
            output_paths.response.write_text("", encoding="utf-8")
            output_paths.summary.write_text(json.dumps({"provider":"claude-code","model":self.model or "claude_default","status":reason,"exit_code":result.returncode,"duration_seconds":round(time.monotonic()-started,3),"output":str(output_paths.response),"usage":{},"error":reason}, indent=2), encoding="utf-8")
            message = f"Claude Code terminó con error ({reason}); revisa {output_paths.stderr.name}"
            if reason == "authentication":
                raise CoreError("llm_unavailable", message)
            raise RuntimeError(message)
        try: payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            output_paths.response.write_text(result.stdout, encoding="utf-8")
            output_paths.summary.write_text(json.dumps({
                "provider": "claude-code",
                "model": self.model or "claude_default",
                "status": "invalid_json",
                "exit_code": result.returncode,
                "duration_seconds": round(time.monotonic()-started, 3),
                "output": str(output_paths.response),
                "usage": {},
                "error": "invalid_json",
            }, indent=2), encoding="utf-8")
            raise RuntimeError(f"La respuesta de Claude Code no es JSON válido; revisa {output_paths.events.name}") from exc
        output_paths.response.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        summary = {"provider": "claude-code", "model": self.model or payload.get("model", "claude_default"), "status": "completed" if result.returncode == 0 else "failed", "exit_code": result.returncode, "duration_seconds": round(time.monotonic()-started, 3), "output": str(output_paths.response), "usage": payload.get("usage", {}), "error": None if result.returncode == 0 else "process_failed"}
        output_paths.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        data = payload.get("structured_output")
        if not isinstance(data, dict):
            summary["status"] = "missing_structured_output"
            summary["error"] = "missing_structured_output"
            output_paths.summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
            raise RuntimeError(f"Claude Code no devolvió structured_output; revisa {output_paths.response.name} y autentícate si procede")
        return LLMResult(data=data, provider="claude-code", model=summary["model"], response_id=payload.get("session_id"), usage=payload.get("usage", {}), execution={"duration_seconds": summary["duration_seconds"], "exit_code": result.returncode, "summary_path": str(output_paths.summary)})
