"""Approvable plans and local operation records shared by every area."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from ..errors import HarnessError


class OperationStatus(StrEnum):
    PLANNED = "planned"
    RUNNING = "running"
    RECOVERABLE = "recoverable"
    SUCCEEDED = "succeeded"
    CONFLICT = "conflict"
    PUBLISHED = "published"
    DISCARDED = "discarded"


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    plan_id: str
    kind: str
    status: OperationStatus = OperationStatus.PLANNED
    completed_actions: tuple[str, ...] = ()
    resources: tuple[dict[str, Any], ...] = ()
    outputs: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    conflict: dict[str, Any] | None = None

    def json(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = str(self.status)
        data["completed_actions"] = list(self.completed_actions)
        data["resources"] = list(self.resources)
        return data

    @classmethod
    def load(cls, data: dict[str, Any]) -> "OperationRecord":
        try:
            return cls(data["operation_id"], data["plan_id"], data["kind"], OperationStatus(data["status"]),
                       tuple(data.get("completed_actions", ())), tuple(data.get("resources", ())),
                       dict(data.get("outputs") or {}), data.get("result"), data.get("conflict"))
        except (KeyError, TypeError, ValueError) as exc:
            raise HarnessError("invalid_operation", "El estado local de la operación no es válido") from exc


@dataclass(frozen=True)
class PlanAction:
    kind: str
    resource_id: str | None
    name: str
    parent_id: str | None
    expected_version: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Plan:
    kind: str
    root_folder_id: str
    account_id: str
    actions: tuple[PlanAction, ...]
    snapshot: dict[str, str | None]
    operation_id: str = field(default_factory=lambda: str(uuid4()))

    @property
    def id(self) -> str:
        data = {"kind": self.kind, "root": self.root_folder_id, "account": self.account_id,
                "actions": [action.json() for action in self.actions], "snapshot": self.snapshot,
                "operation": self.operation_id}
        encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return sha256(encoded.encode()).hexdigest()

    def json(self) -> dict[str, Any]:
        return {"plan_id": self.id, "operation_id": self.operation_id, "kind": self.kind,
                "root_folder_id": self.root_folder_id, "actions": [item.json() for item in self.actions],
                "snapshot": self.snapshot}

    @classmethod
    def load(cls, data: dict[str, Any]) -> "Plan":
        """Restore a locally stored plan, rejecting malformed substitutes."""
        try:
            actions = tuple(PlanAction(**action) for action in data["actions"])
            plan = cls(
                kind=data["kind"], root_folder_id=data["root_folder_id"],
                account_id=data["account_id"], actions=actions,
                snapshot=data["snapshot"], operation_id=data["operation_id"],
            )
        except (KeyError, TypeError) as exc:
            raise HarnessError("invalid_plan", "El plan local no cumple el contrato") from exc
        if not all(isinstance(key, str) and (value is None or isinstance(value, str))
                   for key, value in plan.snapshot.items()):
            raise HarnessError("invalid_plan", "El snapshot del plan no es válido")
        return plan

    def storage_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "root_folder_id": self.root_folder_id,
                "account_id": self.account_id,
                "actions": [item.json() for item in self.actions],
                "snapshot": self.snapshot, "operation_id": self.operation_id,
                "plan_id": self.id}
