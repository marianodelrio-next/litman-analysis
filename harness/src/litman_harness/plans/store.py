from __future__ import annotations

import json
import os
from pathlib import Path
import re

from ..errors import HarnessError
from .models import OperationRecord, Plan


class PlanStore:
    """Small private store; Drive plans are never accepted from transport input."""

    def __init__(self, root: Path):
        self.root = root

    def save(self, plan: Plan) -> str:
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(self.root, 0o700)
        except OSError:
            pass
        path = self._path(plan.account_id, plan.id)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        payload = json.dumps(plan.storage_json(), sort_keys=True, ensure_ascii=False)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(payload, encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)
        return plan.id

    def load(self, account_id: str, plan_id: str) -> Plan:
        if not isinstance(plan_id, str) or len(plan_id) != 64:
            raise HarnessError("unknown_plan", "El identificador de plan no es válido")
        path = self._path(account_id, plan_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HarnessError("unknown_plan", "No existe un plan pendiente para la cuenta activa") from exc
        plan = Plan.load(data)
        if plan.id != plan_id or plan.account_id != account_id:
            raise HarnessError("invalid_plan", "El plan almacenado no coincide con la aceptación")
        return plan

    def save_operation(self, account_id: str, operation_id: str, state: dict | OperationRecord) -> None:
        """Persist retry state locally; it is never mistaken for shared Drive state."""
        path = self._operation_path(account_id, operation_id)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        payload = state.json() if isinstance(state, OperationRecord) else state
        temporary.write_text(json.dumps(payload, sort_keys=True, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(path)

    def load_operation(self, account_id: str, operation_id: str) -> dict:
        try:
            return json.loads(self._operation_path(account_id, operation_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise HarnessError("unknown_operation", "No existe estado local para la operación") from exc

    def record(self, account_id: str, operation_id: str) -> OperationRecord | None:
        """The typed local record of an operation, or ``None`` if it was never registered."""
        path = self._operation_path(account_id, operation_id)
        if not path.is_file():
            return None
        return OperationRecord.load(self.load_operation(account_id, operation_id))

    def records(self, account_id: str) -> list[OperationRecord]:
        """Every readable local operation record of the account."""
        directory = self._path(account_id, "a" * 64).parent / "operations"
        records = []
        for path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
            try:
                records.append(OperationRecord.load(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError, HarnessError):
                continue
        return records

    def _path(self, account_id: str, plan_id: str) -> Path:
        # permission IDs and plan IDs are identifiers, not filenames supplied verbatim.
        if not isinstance(account_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", account_id):
            raise HarnessError("invalid_account", "La identidad activa no es apta para almacenar planes")
        return self.root / account_id / f"{plan_id}.json"

    def _operation_path(self, account_id: str, operation_id: str) -> Path:
        if not isinstance(operation_id, str) or not re.fullmatch(r"[A-Za-z0-9-]{8,128}", operation_id):
            raise HarnessError("invalid_operation", "El identificador de operación no es válido")
        self._path(account_id, "a" * 64)  # validate account consistently
        return self.root / account_id / "operations" / f"{operation_id}.json"
