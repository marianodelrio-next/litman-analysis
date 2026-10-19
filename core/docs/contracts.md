# LitMan Core internal run contract

This page describes Core's current internal execution artifacts. It does not
define the process interface used by Harness or other consumers. Commands,
configuration keys, standard-output JSON, exit codes, artifact roles, and
compatibility rules belong exclusively to the repository
[public CLI contract](../../docs/contracts.md).

Internal files may evolve without increasing the public contract version.
Process consumers must not read them.

## Run lifecycle and layout

`JobRunner` materializes and normalizes one input bundle, executes either the
`assessment` or `detailed-analysis` pipeline, validates the complete run, and
publishes only after validation succeeds.

Each execution receives one `publication_id` and creates a persistent run
under `output.directory/<publication_id>/` with these internal directories:

- `input/` contains the materialized source set.
- `output/` contains pipeline results, validation, manifests, and generated
  deliverables.
- `logs/` contains run diagnostics.

Both pipelines produce `output/validation.json` and `output/result.json`.
Detailed analysis also produces `dossier.json`, `generation_manifest.json`,
and lineage metadata. Lineage records the dossier version, origin, relative
path, and SHA-256 digest used for generation.

## Validation and evidence

Versioned pipeline bundles declare their resources and hashes. Validation
results cover schema, semantic, and evidence errors. Document references keep
the source identifier, name, MIME type, and cited page or text when available.

Every provider response passes structural and semantic validation before
publication. A missing artifact, invalid `validation.json`, invalid manifest,
or incomplete upload prevents the run from being reported as successful.

## Publication internals

The publisher derives a closed deliverable catalog from the current run:

- `assessment` publishes `ficha_oportunidad.pdf`.
- `detailed-analysis` publishes `resumen_tecnico.docx`,
  `guia_preparacion_oferta.docx`, exactly one technical DOCX declared by the
  generation manifest, and `simulador_economico.xlsx`.

Diagnostics, lineage, and publication manifests are not deliverables. With
`publication.include_run_files = false`, the local run is reduced to the
catalog only after validation and any Drive replica both succeed. With
`true`, the complete tree is retained and published using `run_file` roles.

The immutable publication inventory contains relative paths and SHA-256
digests calculated from that execution's bytes. Digests are not compared
between executions. Drive uploads use a temporary folder that is promoted to
the final `publication_id` only after every upload succeeds.

## Runtime boundary

Core supports local and Google Drive sources and destinations in every
combination. Drive requires explicit credentials; tests use fakes and do not
access external services.

Container user checks, mounts, capabilities, and `no-new-privileges` are
deployment preflight concerns, not part of either the internal run model or
the public process contract. See [Core operations](operations.md) and the
[Docker guide](../deployment/docker/README.md).
