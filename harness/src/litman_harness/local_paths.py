"""Private local locations of the harness: never inside the repository checkout."""
from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .errors import HarnessError

METADATA_ENV = "LITMAN_HARNESS_METADATA"
OAUTH_TOKEN_ENV = "LITMAN_HARNESS_OAUTH_TOKEN"
OAUTH_CLIENT_ENV = "LITMAN_HARNESS_OAUTH_CLIENT"
PLAN_STORE_ENV = "LITMAN_HARNESS_PLAN_STORE"
WORK_DIR_ENV = "LITMAN_HARNESS_WORK_DIR"
CONFIGURABLE = (METADATA_ENV, OAUTH_TOKEN_ENV, OAUTH_CLIENT_ENV, PLAN_STORE_ENV, WORK_DIR_ENV)


def checkout_root(start: Path | None = None) -> Path | None:
    """Return the repository that contains this package, if it runs from a clone (not the cwd)."""
    origin = (start or Path(__file__)).resolve()
    for candidate in (origin, *origin.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def ensure_outside_checkout(path: Path, code: str, message: str) -> Path:
    resolved = path.expanduser().resolve()
    checkout = checkout_root()
    if checkout is not None and resolved.is_relative_to(checkout):
        raise HarnessError(code, message)
    return resolved


def state_dir(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base).expanduser() / "litman-harness"


def config_dir(env: Mapping[str, str]) -> Path:
    base = env.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base).expanduser() / "litman-harness"


def _configured(env: Mapping[str, str], name: str, default: Path) -> Path:
    value = env.get(name)
    return Path(value).expanduser() if value else default


def plan_store_root(env: Mapping[str, str]) -> Path:
    return ensure_outside_checkout(_configured(env, PLAN_STORE_ENV, state_dir(env) / "plans"),
                                   "unsafe_local_path", "El almacén de planes debe estar fuera del clon")


def work_root(env: Mapping[str, str]) -> Path:
    return ensure_outside_checkout(_configured(env, WORK_DIR_ENV, state_dir(env) / "work"),
                                   "unsafe_local_path", "El directorio de trabajo debe estar fuera del clon")


def token_path(env: Mapping[str, str]) -> Path:
    return _configured(env, OAUTH_TOKEN_ENV, config_dir(env) / "token.json")


def client_path(env: Mapping[str, str]) -> Path:
    return _configured(env, OAUTH_CLIENT_ENV, config_dir(env) / "client_secret.json")
