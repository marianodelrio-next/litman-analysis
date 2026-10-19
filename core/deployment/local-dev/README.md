# Local development from the checkout

Use this workflow to contribute to Core. It requires Python 3.11 and `uv`, plus
an authenticated Codex or Claude Code installation for real analysis runs.
Tests do not require provider or Drive credentials.

From the repository's `core/` directory:

```sh
uv sync
UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q
cp deployment/config_example.toml deployment/config.toml
cd deployment
uv run litman-core run
```

The local CLI executes `JobRunner` directly from the checkout. Configure the
job and provider as described in the [common deployment guide](../README.md).
On Windows, use the equivalent PowerShell or `cmd` commands. Core creates its
private workspace under the system temporary directory, and Claude Code must
resolve to a native `.exe`, not a `.cmd` or `.bat` launcher.

To consume an installed distribution instead of checkout source, use the
[local wheel installation guide](../local-install/README.md).
