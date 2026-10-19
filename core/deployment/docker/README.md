# Optional Docker deployment

Docker installs the Core wheel into an isolated image and invokes the same
`litman-core` CLI as a local installation. It does not run source directly
from the checkout.

## Prepare and run

Copy `core/deployment/config_example.toml` to
`core/deployment/config.toml`. If the run uses Codex or Drive, place the
required local state under `core/deployment/local-secrets/`; these paths are
ignored by Git.

From the repository root:

```sh
docker compose -f core/deployment/docker/compose.yaml config --quiet
docker compose -f core/deployment/docker/compose.yaml build
docker compose -f core/deployment/docker/compose.yaml run --rm litman-core run
```

Compose provides these runtime paths:

| Host path | Container path | Access |
| --- | --- | --- |
| `core/deployment/config.toml` | `/app/config.toml` | read-only |
| `core/deployment/input/` | `/app/input` | read-only |
| `core/deployment/runs/` | `/app/runs` | read/write |
| `core/deployment/local-secrets/` | `/run/secrets` | read-only |
| `core/deployment/local-secrets/codex/` | `/var/lib/litman-core/codex` | read/write |

Override the secrets and Codex state host directories with
`LITMAN_CORE_SECRETS_DIR` and `LITMAN_CORE_CODEX_STATE_DIR`. Paths in
`config.toml` must refer to container paths; Core performs no automatic host
path translation.

## Isolation boundary

The container runs as a non-root user with a read-only root filesystem,
dropped capabilities, `no-new-privileges`, and a temporary `/tmp`. Only the
declared mounts are available. Codex runs inside this boundary with access to
the network and mounted job resources, so never mount unrelated information
or include credentials in jobs, prompts, images, logs, or build context.

Docker supports Codex, not Claude Code. Provider selection and the common run
procedure are documented in the [deployment guide](../README.md).
