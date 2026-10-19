# Running LitMan Core

This page owns the common procedure for configuring and running Core. Use the
linked guides for environment-specific installation and deployment steps.

## Configure a run

Copy [`config_example.toml`](config_example.toml) to `config.toml`, then set
the input and output locations. The operational file is ignored by Git.

`config.toml` selects the job, source, local run root, optional Drive replica,
LLM provider, and publication mode. Relative paths are resolved from the TOML
file. The complete list of keys and defaults belongs to the
[public CLI contract](../../docs/contracts.md).

Authentication is supplied by the environment, never by the job:

- Codex uses the session created by `codex login` and reads
  `CODEX_HOME/auth.json` (`~/.codex/auth.json` by default).
- Claude Code uses an existing Claude session when `[llm] provider =
  "claude-code"`; the provider and optional model are selected only in
  `config.toml`.
- Google Drive requires explicit Google credentials for Drive input or output.

## Run

From this directory, with `litman-core` available in the active environment:

```sh
litman-core run
litman-core run --config /path/config.toml --env-file /path/.env
```

Without `--config`, Core loads `./config.toml`. Without `--env-file`, it loads
an adjacent `.env` when present. Existing environment variables take
precedence over `.env`; the file is never copied into a run.

`output.directory` receives the final `<job.id>-<UTC timestamp>` directory.
Setting `output.google_drive_folder_id` adds a Drive replica. With
`publication.include_run_files = false` (the default), a successful
publication retains only public deliverables; `true` retains and replicates
the complete run tree. A failed run keeps its local diagnostics and does not
promote a final Drive folder.

## Choose an environment

- [Develop from the checkout](local-dev/README.md)
- [Install and run a wheel](local-install/README.md)
- [Run the optional Docker deployment](docker/README.md)

Core does not translate host paths into container paths. Each environment
guide documents the paths visible to that runtime.
