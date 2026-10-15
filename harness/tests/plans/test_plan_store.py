from __future__ import annotations

from pathlib import Path

import pytest

from litman_harness.errors import HarnessError
from litman_harness.plans import PlanStore
from litman_harness.plans.models import Plan, PlanAction


@pytest.mark.parametrize("account_id", (".", "..", "../other", "person/name", "person\\name", "person.name", ""))
def test_plan_store_rejects_unsafe_account_path_components(tmp_path: Path, account_id: str):
    with pytest.raises(HarnessError) as raised:
        PlanStore(tmp_path / "plans").load(account_id, "a" * 64)
    assert raised.value.code == "invalid_account"


def test_plan_round_trips_privately_and_is_bound_to_account(tmp_path: Path):
    store = PlanStore(tmp_path / "plans")
    plan = Plan("incorporation", "root", "person", (PlanAction("create_folder", None, "Oferta", "root"),),
                {"root": "1"})
    store.save(plan)
    assert store.load("person", plan.id) == plan
    assert (tmp_path / "plans").stat().st_mode & 0o777 == 0o700
    with pytest.raises(HarnessError) as raised:
        store.load("other", plan.id)
    assert raised.value.code == "unknown_plan"
