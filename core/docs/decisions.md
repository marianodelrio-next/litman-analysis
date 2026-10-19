# Core technical decisions

This log contains durable choices owned by the Core package. Cross-package
architecture and development-process decisions belong in the repository
[decision log](../../docs/decisions/README.md); Harness decisions belong to
Harness documentation.

## Application namespace and Docker boundary

- `litman_core` is the only Core application package. It owns the CLI,
  orchestration, domain, pipelines, infrastructure, generation,
  configuration, and packaged resources.
- The former alternate Python package was removed rather than retained as a
  compatibility implementation.
- `litman-core` is Core's only public entry point. Docker invokes the same CLI
  and does not add a worker entry point.
- Docker remains the external distribution and isolation boundary. Domain and
  pipeline code do not select or branch on runtime.
- Development from the checkout and consumption of an installed wheel are
  separate flows. Docker installs a built wheel into its isolated runtime.

## Core and Harness process boundary

- Harness is a separate distribution. Core does not import or know about it.
- Harness and every other consumer invoke Core as a process and use only the
  versioned [public CLI contract](../../docs/contracts.md).
- Internal run files, manifests, and diagnostics are not integration
  interfaces. Harness consumes only the exit status and JSON written to
  standard output.

## Technical summary artifact contract

- `resumen_tecnico.docx` is a compact technical brief generated
  deterministically from the detailed-analysis dossier.
- Its stable structure is one title followed by five numbered sections:
  context, objectives, phases and deliverables, technologies and resources,
  and key aspects.
- The artifact preserves critical requirements, criteria, phase deliverables,
  and explicit empty states. It may abbreviate descriptions deterministically
  but must not invent content or add a separate cover or detail section.
- The generator contract version increases when this structure changes.

## Bid preparation guide artifact contract

- `guia_preparacion_oferta.docx` is a deterministic operational guide built
  from the persisted dossier. Its canonical ID is `bid-preparation-guide`.
- Its compact body has five fixed numbered sections: context, documents to
  submit, offer-preparation requirements, award criteria, and pending checks.
- The guide retains operational requirements, rules, consequences, criteria,
  and pending actions while omitting technical-summary content and the
  evidence appendix. Traceability remains in the dossier and persisted
  analysis results.
- Missing format data is grouped into one `No consta` notice, and unknown
  values use the same convention.
- The generator contract version increases when this structure changes.
