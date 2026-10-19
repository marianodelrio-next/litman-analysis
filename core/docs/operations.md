# LitMan Core operations

This page owns Core's execution architecture and operational internals. For
configuration and commands, use the [deployment guide](../deployment/README.md).
For the stable process interface, use the repository
[public CLI contract](../../docs/contracts.md).

## Execution architecture

Local and container installations execute the same flow:

```text
litman-core run -> source -> inventory and normalization -> LLM provider
                -> validation -> publisher -> temporary cleanup
```

The CLI loads `config.toml` and invokes `JobRunner`; the runner has no Docker
branches. It selects `LocalDocumentSource` or `GoogleDriveDocumentSource`,
builds one `DocumentBundle`, executes `AssessmentPipeline` or
`DetailedAnalysisPipeline`, validates the run, and then selects
`LocalArtifactPublisher` or `GoogleDriveArtifactPublisher`.

Drive IDs and MIME types enter the in-memory bundle. Digests are calculated
from downloaded bytes and carried into manifests, evidence, and lineage. All
four local/Drive source and destination combinations are supported.

Codex is the default LLM provider and defaults to the `gpt-5.6-luna` model.
Claude Code is also supported for local Ubuntu and Windows execution and
defaults to `claude-sonnet-5`. Provider selection and the optional model come
from `[llm]` in `config.toml`; there is no provider-selection environment
variable.

## Persistence and publication

One `publication_id` is assigned per execution using
`<job_id>-<UTC timestamp with microseconds>Z`. Core creates the persistent run
directly under `output.directory/<publication_id>/`. If Drive replication is
configured, the same identity names the remote folder.

The publisher validates an immutable inventory of relative paths and hashes
before reducing or replicating the run. On any error, the complete local run
is preserved. A Drive `storageQuotaExceeded` response is translated into an
explicit recommendation to use a Shared Drive.

Detailed-analysis output is always Spanish. Evidence quotations, identifiers,
file names, stable references, proper names, and schema-designated literal
formulas preserve the source text. Evidence verification requires the source
document and page and allows only artificial whitespace introduced by PDF
layout. An unverifiable quotation produces a partial report with warnings;
structural and semantic failures remain blocking.

## Container security boundary

The Docker deployment uses a non-root user, read-only root filesystem,
temporary `/tmp`, dropped capabilities, minimal mounts, and
`no-new-privileges`. The private LLM workspace is removed in `finally`; the
persistent run and its diagnostics are not.

Codex runs with `--dangerously-bypass-approvals-and-sandbox` inside the
container and can access its filesystem, network, and mounted secrets. There
is no nested Bubblewrap sandbox. The container is therefore the accepted
isolation boundary: do not mount material unrelated to the job.

On POSIX, Codex `auth.json` must have mode `0600`. On Windows, Core verifies
that the file is readable and `CODEX_HOME` is writable because POSIX mode bits
do not represent Windows ACLs. Preflight cannot detect a session stored only
in an operating-system credential store.

## Extending Core

Versioned pipeline and generation resources live under
`src/litman_core/resources/`. Add a source or publisher by implementing the
existing ports and composing the adapter in `JobRunner`; do not introduce a
second orchestrator. Any public CLI change must update the
[public contract](../../docs/contracts.md) and its schemas and examples.
