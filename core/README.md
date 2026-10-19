# LitMan Core

LitMan Core is the Python 3.11 distribution that analyzes procurement files.
It runs independently through the `litman-core` CLI and supports local or
Google Drive input and output. Docker is an optional deployment boundary, not
a separate runtime.

Core supports `assessment` and `detailed-analysis` jobs. Each successful run
creates a versioned publication named `<job_id>-<YYYYMMDDTHHMMSS.ffffffZ>`.
Assessment publishes `ficha_oportunidad.pdf`; detailed analysis publishes
`resumen_tecnico.docx`, `guia_preparacion_oferta.docx`, one technical DOCX
declared by the generation manifest, and `simulador_economico.xlsx`.

## Documentation

Choose the page that owns the topic you need:

| Topic | Source of truth |
| --- | --- |
| Public CLI, configuration, result JSON, errors, and versioning | [Repository public contract](../docs/contracts.md) |
| Core run layout, lineage, validation, and publication internals | [Internal run contract](docs/contracts.md) |
| Execution architecture and operational internals | [Operations](docs/operations.md) |
| Core-specific durable technical choices | [Core decisions](docs/decisions.md) |
| Configuration and running Core | [Deployment guide](deployment/README.md) |
| Development from this checkout | [Local development](deployment/local-dev/README.md) |
| Installing and running a wheel | [Local installation](deployment/local-install/README.md) |
| Optional container deployment | [Docker](deployment/docker/README.md) |

The repository [shared architecture](../docs/architecture.md) explains the
Core/Harness process boundary. The public contract is the stable interface for
Harness and other consumers; internal run files are not part of that contract.

## Development

Follow [Core development instructions](AGENTS.md). Tests use fakes and do not
access Drive or require real credentials. Do not put credentials in jobs,
logs, prompts, build context, or committed configuration.
