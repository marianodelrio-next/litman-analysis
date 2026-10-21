# Local wheel installation

Use this workflow to run a built `litman-core` distribution without executing
source from a checkout. It requires Python 3.11 and `uv`.

Build or obtain a wheel as a packaging step:

```sh
uv build --wheel --out-dir ./dist
```

In the directory that will hold the installation, create an environment and
install the exact wheel:

```sh
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python /path/litman_core-0.2.0-py3-none-any.whl
```

Run the installed CLI:

```sh
.venv/bin/litman-core run
.venv/bin/litman-core run --config /path/config.toml
```

On Windows, the equivalent paths are `.venv\\Scripts\\python.exe` and
`.venv\\Scripts\\litman-core.exe`.

Configure jobs, environment loading, and authentication through the
[common deployment guide](../README.md). The exact configuration surface is
the [public CLI contract](../../../docs/contracts.md); generation templates
are not publicly configurable.

Core uses `/tmp/litman-core` as its temporary workspace on POSIX and the
system temporary directory plus `litman-core` on Windows. Override it with
`LITMAN_CORE_WORKSPACE_DIR`; Core removes the workspace after execution.

For Claude Code on Ubuntu or Windows, authenticate with `claude`, select
`[llm] provider = "claude-code"`, and optionally set
`LITMAN_CORE_CLAUDE_CONFIG_DIR`. Core forwards that directory internally as
`CLAUDE_CONFIG_DIR`. The default model is `claude-sonnet-5`; select another
with `[llm] model` in `config.toml`. On Windows,
`LITMAN_CORE_CLAUDE_BINARY` must identify the native `.exe`, not a `.cmd` or
`.bat` launcher. Core does not copy or inspect provider tokens.
