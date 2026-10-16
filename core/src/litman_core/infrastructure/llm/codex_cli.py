from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TextIO

from litman_core.application.ports.llm import LLMOutputPaths, LLMResult
from litman_core.errors import CoreError
from .codex_events import CodexEventSummary
from .codex_auth import CodexAuthentication


class CodexExecutionError(RuntimeError):
    pass


class CodexTimeoutError(CodexExecutionError):
    pass


class CodexOutputError(CodexExecutionError):
    pass


class CodexToolExecutionError(CodexExecutionError):
    pass


class CodexUnexpectedToolUseError(CodexExecutionError):
    pass


ToolFailurePolicy = Literal["warn", "strict"]


class CodexProvider:
    """Ejecuta Codex CLI y conserva su stream JSONL estructurado."""

    def __init__(self, *, binary: str = "codex", model: str | None = None,
                 timeout_seconds: int = 1800, authentication: CodexAuthentication | None = None,
                 home: Path | None = None, codex_home: Path | None = None, no_tools: bool = False,
                 tool_failure_policy: ToolFailurePolicy = "warn") -> None:
        if tool_failure_policy not in {"warn", "strict"}:
            raise ValueError("tool_failure_policy debe ser 'warn' o 'strict'")
        self.binary = binary
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.authentication = authentication
        self.home = home
        self.codex_home = codex_home
        self.no_tools = no_tools
        self.tool_failure_policy = tool_failure_policy

    def generate(self, *, instructions: str, prompt: str, schema_path: Path,
                 case_dir: Path, output_paths: LLMOutputPaths) -> LLMResult:
        executable = shutil.which(self.binary)
        if executable is None:
            raise CoreError(
                "llm_unavailable",
                f"No se encuentra Codex CLI ({self.binary!r}). "
                "Instálalo o configura LITMAN_CORE_CODEX_BINARY.",
            )

        _prepare_output_paths(output_paths)
        command = [
            executable,
            "exec",
            "--ephemeral",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--json",
            "--output-schema",
            str(schema_path.resolve()),
            "--output-last-message",
            str(output_paths.response.resolve()),
        ]
        command.extend(["--ignore-user-config", "--ignore-rules", "-c", "shell_environment_policy.inherit=\"core\""])
        if self.no_tools:
            for feature in ("shell_tool", "unified_exec", "apps", "plugins", "browser_use", "computer_use", "image_generation"):
                command.extend(["--disable", feature])
        authentication = self.authentication or CodexAuthentication.from_environment(
            codex_home=self.codex_home
        )
        command.extend(["-c", f'forced_login_method="{authentication.cli_login_method}"'])
        if self.model:
            command.extend(["--model", self.model])
        command.append("-")

        print(f"[codex] modelo: {self.model or 'por defecto'}", file=sys.stderr, flush=True)
        print("[codex] esperando respuesta...", file=sys.stderr, flush=True)
        full_prompt = (
            f"{instructions}\n\n---\n\n{prompt}\n\n"
            "El directorio de trabajo es la raíz del expediente. Puedes leer sus "
            "documentos, pero no debes modificar ningún archivo ni ejecutar acciones "
            "ajenas al análisis."
        )

        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        event_summary = CodexEventSummary()
        process = subprocess.Popen(
            command,
            cwd=case_dir,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=_child_environment(authentication, home=self.home, codex_home=self.codex_home),
        )
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None

        stdout_thread = threading.Thread(
            target=_consume_events,
            args=(process.stdout, output_paths.events, event_summary),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_consume_stderr,
            args=(process.stderr, output_paths.stderr),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        status = "completed"
        timed_out = False
        try:
            process.stdin.write(full_prompt)
            process.stdin.close()
            process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            status = "timeout"
            timed_out = True
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        finally:
            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)

        duration = time.monotonic() - started
        finished_at = datetime.now(timezone.utc)
        if not timed_out and process.returncode != 0:
            status = "failed"

        summary = _build_summary(
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            duration=duration,
            exit_code=process.returncode,
            requested_model=self.model,
            events=event_summary,
            response_path=output_paths.response,
        )
        _write_json(output_paths.summary, summary)

        if timed_out:
            raise CodexTimeoutError(
                f"Codex superó el tiempo máximo de {self.timeout_seconds} segundos; "
                f"se conservaron {event_summary.total} eventos"
            )
        if process.returncode != 0:
            raise CodexExecutionError(
                f"Codex terminó con código {process.returncode}. "
                f"Revisa {output_paths.stderr.name} y {output_paths.events.name}."
            )

        if self.no_tools and event_summary.tool_calls:
            summary["status"] = "unexpected_tool_use"
            summary["failure_reason"] = "no_tools_policy"
            _write_json(output_paths.summary, summary)
            raise CodexUnexpectedToolUseError("Codex emitió una herramienta pese a la política no-tools.")

        try:
            data = _read_response(output_paths.response)
        except CodexOutputError:
            summary["status"] = "output_error"
            summary["response"]["present"] = output_paths.response.exists()
            _write_json(output_paths.summary, summary)
            raise
        summary["response"]["valid_json"] = True
        if event_summary.failed_tool_calls:
            summary["tool_failure_policy"] = self.tool_failure_policy
            failures = ", ".join(
                f"programa={item.get('program') or 'desconocido'} exit_code={item.get('exit_code')}"
                for item in event_summary.command_failures[:3]
            )
            if self.tool_failure_policy == "strict":
                summary["status"] = "tool_execution_error"
                summary["failure_reason"] = "required_tool_failed"
                _write_json(output_paths.summary, summary)
                detail = f" ({failures})" if failures else ""
                raise CodexToolExecutionError(
                    "Falló una herramienta requerida para el análisis"
                    f"{detail}; se conservaron los diagnósticos en {output_paths.summary.name}.")
            summary["status"] = "completed_with_tool_errors"
            summary["failure_reason"] = "tool_errors_recovered"
            summary["tool_failures"] = event_summary.command_failures
            detail = f" ({failures})" if failures else ""
            print(
                "[codex] se recuperó de errores de herramientas"
                f"{detail}; el resultado pasará las validaciones del pipeline",
                file=sys.stderr,
                flush=True,
            )
        _write_json(output_paths.summary, summary)
        print(
            f"[codex] completado en {duration:.1f}s · "
            f"{event_summary.total} eventos · {event_summary.tool_calls} herramientas",
            file=sys.stderr,
            flush=True,
        )
        return LLMResult(
            data=data,
            provider="codex",
            model=self.model or "codex_default",
            response_id=event_summary.thread_id,
            usage=event_summary.usage,
            execution={
                "duration_seconds": round(duration, 3),
                "exit_code": process.returncode,
                "event_count": event_summary.total,
                "malformed_event_count": event_summary.malformed,
                "tool_call_count": event_summary.tool_calls,
                "failed_tool_call_count": event_summary.failed_tool_calls,
                "empty_search_count": event_summary.empty_searches,
                "tool_failure_policy": self.tool_failure_policy,
                "summary_path": str(output_paths.summary),
            },
        )


def _consume_events(stream: TextIO, path: Path, summary: CodexEventSummary) -> None:
    try:
        with path.open("w", encoding="utf-8") as output:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                output.write(line)
                output.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    summary.add_malformed()
                    continue
                if isinstance(event, dict):
                    summary.add(event)
                else:
                    summary.add_malformed()
    finally:
        stream.close()


def _consume_stderr(stream: TextIO, path: Path, captured: list[str] | None = None) -> None:
    try:
        with path.open("w", encoding="utf-8") as output:
            for line in iter(stream.readline, ""):
                if not line:
                    break
                output.write(line)
                if captured is not None:
                    captured.append(line)
                output.flush()
                print(line, end="", file=sys.stderr, flush=True)
    finally:
        stream.close()


def _prepare_output_paths(paths: LLMOutputPaths) -> None:
    for path in (paths.events, paths.stderr, paths.response, paths.summary):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)


def _read_response(path: Path) -> dict:
    if not path.exists():
        raise CodexOutputError(
            f"Codex terminó correctamente pero no generó {path.name}"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexOutputError(
            f"La respuesta final de Codex no es un JSON válido: {path}"
        ) from exc
    if not isinstance(value, dict):
        raise CodexOutputError("La respuesta final de Codex debe ser un objeto JSON")
    return value


def _build_summary(*, status: str, started_at: datetime, finished_at: datetime,
                   duration: float, exit_code: int | None, requested_model: str | None,
                   events: CodexEventSummary, response_path: Path) -> dict:
    return {
        "status": status,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round(duration, 3),
        "exit_code": exit_code,
        "model_requested": requested_model or "codex_default",
        "thread_id": events.thread_id,
        "events": events.as_dict(),
        "tool_calls_failed": events.failed_tool_calls,
        "usage": events.usage,
        "response": {
            "path": str(response_path),
            "present": response_path.exists(),
            "valid_json": False,
        },
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _child_environment(authentication: CodexAuthentication, *, home: Path | None, codex_home: Path | None) -> dict[str, str]:
    """A narrowly scoped environment, inherited by any agent tools as well."""
    allowed = {"PATH", "LANG", "LC_ALL", "LC_CTYPE", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy"}
    env = {name: value for name, value in os.environ.items() if name in allowed}
    env["HOME"] = str(home or os.environ.get("HOME", "/tmp/litman-core/home"))
    env["CODEX_HOME"] = str(codex_home or os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    env.update(authentication.environment())
    return env
