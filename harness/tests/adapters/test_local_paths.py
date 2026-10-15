from __future__ import annotations

from pathlib import Path

import pytest

from litman_harness.errors import HarnessError, safe_exception_message
from litman_harness.local_paths import checkout_root, plan_store_root, work_root


def test_default_private_locations_follow_xdg_state(tmp_path: Path):
    env = {"XDG_STATE_HOME": str(tmp_path)}
    assert work_root(env) == (tmp_path / "litman-harness" / "work").resolve()
    assert plan_store_root(env) == (tmp_path / "litman-harness" / "plans").resolve()


@pytest.mark.parametrize("resolver,variable", ((work_root, "LITMAN_HARNESS_WORK_DIR"),
                                                (plan_store_root, "LITMAN_HARNESS_PLAN_STORE")))
def test_configured_locations_inside_checkout_are_rejected(resolver, variable):
    with pytest.raises(HarnessError) as raised:
        resolver({variable: str(checkout_root() / "harness" / "tmp")})
    assert raised.value.code == "unsafe_local_path"


def test_safe_exception_message_redacts_environment_values_and_token_paths(monkeypatch):
    monkeypatch.setenv("LITMAN_HARNESS_OAUTH_TOKEN", "/home/x/private/credentials.json")
    message = safe_exception_message(RuntimeError(
        "fallo en /home/x/private/credentials.json con ya29.abcDEF y /tmp/a/token.json " + "x" * 500))
    assert "/home/x/private" not in message and "ya29" not in message and "token.json" not in message
    assert message.startswith("RuntimeError: ") and len(message) <= 300
