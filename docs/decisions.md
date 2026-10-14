# Durable Technical Decisions

## Development-agent system

- Development agents live in `AGENTS.md`, `.codex/`, and `.agents/`; they are isolated from the product pipeline and its Codex CLI.
- Tasks that opt into the design workflow use untracked local memory in
  `.agent-work/<task>/`. A design.md requires human approval before `implement`;
  authorized direct changes may proceed without that workflow.
- Global memory is limited to essential architecture, durable decisions, and a navigation map. Memory Manager updates it after a satisfactory review.
- Coordination allows at most three concurrent subagents. Implementation remains sequential to avoid contention on shared files.

## Application namespace and Docker boundary

- `litman_core` is the only Python application package and owns CLI, orchestration, domain, pipelines, infrastructure, generation, configuration, and packaged resources.
- The former alternate Python package is removed rather than retained as a compatibility implementation.
- `litman-core` is the only public entry point. Docker invokes the same CLI and does not add a package worker entry point.
- Docker remains the external distribution and isolation boundary; domain and pipelines do not select or branch on runtime.
- Local development and local wheel consumption are documented as separate
  flows (`deployment/local-dev/` and `deployment/local-install/`). The wheel
  flow requires explicit persistent workspace and runs paths; la configuración
  diagnostic and does not create them. Docker continues to install a built
  wheel in its isolated runtime.

## Technical summary artifact contract

- `resumen_tecnico.docx` is a single compact technical brief generated
  deterministically from the detailed-analysis dossier. Its stable structure is
  one title followed by five numbered sections: context, objectives, phases and
  deliverables, technologies and resources, and key aspects.
- The artifact preserves critical requirements, criteria, phase deliverables,
  and explicit empty states; it may abbreviate descriptions deterministically
  but must not invent content or add a separate cover/detail section.
- The generator contract version is bumped when this structure changes; the
  rerender path continues to use only the persisted dossier snapshot.

## Bid preparation guide artifact contract

- `guia_preparacion_oferta.docx` remains a deterministic operational guide
  generated from the persisted dossier, with the canonical ID
  `bid-preparation-guide`.
- Its compact body has five fixed numbered sections: context, documents to
  submit, offer-preparation requirements, award criteria, and pending checks.
  The guide keeps operational requirements, rules, consequences, criteria, and
  pending actions, while omitting the technical-summary content and the
  evidence appendix; traceability remains in the dossier and persisted
  analysis results.
- Missing format data is grouped into one `No consta` notice, and unknown
  values use that same convention. The generator contract version is bumped
  when this structure changes; rerender continues to use only the persisted
  dossier snapshot.
