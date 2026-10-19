# LitMan Core public CLI contract

This page is the source of truth for the interface between `litman-core` and
any process consumer. Harness runs Core as a process and never imports
`litman_core`; other integrations must use the same boundary. The contract has
an explicit `contract` version, with its change policy defined below.

Core's [internal run documentation](../core/docs/contracts.md) describes
workspace layout, lineage, and internal publication behavior. Those details
are not part of this public contract and may change without increasing the
public contract version.

## Commands

- `litman-core run --config PATH [--env-file PATH]` runs a job. If `--config`
  is omitted, it uses `./config.toml`. If `--env-file` is not provided and a
  `.env` file exists beside the configuration, Core loads it without
  overwriting variables already present in the environment.
- `litman-core info` prints version and contract information without running a
  job.
- `litman-core --version` prints `litman-core <version>`. It is not part of the
  versioned contract; use `info` for programmatic checks.

## Configuration (`config.toml`)

| Key | Required | Default |
| --- | --- | --- |
| `job.type` | yes | — (`assessment` or `detailed-analysis`) |
| `job.id` | no | input directory name sanitized to `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`; for `input.kind = "google-drive"`, the folder ID |
| `input.location` | yes | — |
| `input.kind` | no | `local` (`google-drive` is also supported) |
| `output.directory` | yes | — |
| `output.google_drive_folder_id` | no | no Drive replica |
| `llm.provider` | no | `codex` |
| `llm.model` | no | the provider's default model |
| `publication.include_run_files` | no | `false` |

Any other top-level key, or any unlisted key within these tables, is rejected.
This includes `[analysis]`: generation templates are not publicly
configurable.

- [Minimal configuration used by Harness](contracts/core-config.minimal.toml)
- [Complete example with optional keys](../core/deployment/config_example.toml)

## `run` output

Standard output always contains exactly one UTF-8 JSON object. Logs go to
standard error and are never part of the contract.

Success has exit code 0:

```json
{"contract": 1, "status": "succeeded", "job_id": "...", "publication_id": "...",
 "local_path": "...",
 "artifacts": [{"role": "technical_summary", "name": "resumen_tecnico.docx",
                "uri": "...", "checksum": "<sha256>"}],
 "remote": {"folder_id": "...", "artifacts": ["..."]}}
```

`remote` is present only when `output.google_drive_folder_id` was configured.

Failure has exit code 1:

```json
{"contract": 1, "status": "failed", "local_path": "...",
 "error": {"code": "llm_unavailable", "message": "..."}}
```

`local_path` is present only if the run was created before the failure.

Invalid CLI usage, such as an unknown subcommand, has exit code 2 and an
`argparse` message on standard error, with no JSON result.

See the [complete examples](contracts/examples/) for one successful result per
job type and one failure per error code. The machine-readable result contract
is [core-result.schema.json](contracts/core-result.schema.json).

### Artifact roles

The closed set is `opportunity_report`, `technical_summary`,
`bid_preparation_guide`, `technical_document`, and `economic_simulator`.
`run_file` is present only when `publication.include_run_files = true`; it
labels published files outside the deliverable catalog. Harness always uses
`include_run_files = false`, so it never receives this role.

### Error codes

| Code | Source |
| --- | --- |
| `invalid_config` | Invalid TOML configuration, `Settings`, or `.env`, before the job runs |
| `invalid_input` | Dossier materialization, inventory, normalization, Drive input metadata, or size |
| `llm_unavailable` | Missing provider CLI or invalid Codex or Claude Code authentication |
| `analysis_failed` | Timeout, invalid provider response, deliverable generation, or an unvalidated run |
| `publication_failed` | Local or Drive publication |
| `internal` | Any other unclassified failure |

## `info` output

```json
{"contract": 1, "version": "0.1.0", "providers": ["claude-code", "codex"],
 "environment": {
   "providers": {"codex": {"cli": true, "session": true},
                 "claude-code": {"cli": false, "session": false}},
   "pdf_browser": true
 }}
```

`environment` is optional and does not increase `contract`. Its checks are
local only: binary presence in `PATH`, a session file, and a discoverable local
PDF browser. The command never invokes a provider CLI or opens a browser.
`false` means "not detected", not necessarily "absent".

The machine-readable contract is
[core-info.schema.json](contracts/core-info.schema.json).

## Versioning

Every `run` and `info` result includes `contract: 1`.

- Increase `contract` when removing or renaming a field, changing the meaning
  of a field or existing value, or adding a new `status`.
- Do not increase it when adding an optional field, artifact role, or error
  code.
- A consumer must map an unknown error code to `internal` and treat an unknown
  artifact role as a contract error. Artifact roles are closed except for
  explicit future additions.
- A `contract` value other than the consumer's expected version is a contract
  incompatibility, not a job execution error.

## Consumer requirements

Harness pins `litman-core==0.1.0`; the `contract` check protects it from an
incompatible installation. Consumers must rely only on the exit behavior and
JSON structures documented here, not on Core's internal run files.
