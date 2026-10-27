# CHG-11 — Short technical proposal filename

## Context

Core's `TechnicalDocumentGenerator` builds the detailed analysis DOCX filename from
"Propuesta técnica", the tender reference, and a shortened title, with up to 180
characters before `.docx` (`core/src/litman_core/generation/technical_proposal/generator.py`).
Core creates it below an analysis run directory containing the operation ID and
timestamp. On Windows, the complete path can exceed the traditional 260-character
limit even when the filename itself fits in one filesystem component. The reported
case succeeded after long paths were enabled, but the exact failing path was not
retained here; the generated DOCX path is the most likely cause, not a proven one.

Harness already shortens local copies of Drive originals according to the input
path budget (`harness/src/litman_harness/analysis/inputs.py`). That protection
does not set the generated DOCX name. Core declares each deliverable's role and
name in the result. Harness validates by role and the declared name, then uses
the technical DOCX to create a Google Doc in `Oferta`
(`harness/src/litman_harness/analysis/results.py`,
`harness/src/litman_harness/dossier/publication.py`). Repeated analyses receive a
date suffix on upload rather than overwriting an existing artifact. The live
offer is tracked by Drive ID (`manifest.live_offer.document_id`), independently
of its visible name.

## Goal and scope

Generate the technical DOCX as `propuesta_tecnica.docx` for every detailed
analysis, regardless of tender title or reference. Keep the tender identity in
the document's content and dossier. Publish the short DOCX and convert it to a
Google Doc as before. The newly converted Google Doc initially receives the
basename `propuesta_tecnica`; renaming it must not break its registration.

Update relevant Core and Harness tests, their documentation, the public CLI
example of a detailed analysis result, and the Unreleased changelog. Do not
rename past artifacts or existing Google Docs, alter the role-based Core/Harness
CLI contract, change original-download handling, or touch LLM invocation,
prompts, schemas, templates, pipelines, Docker, or Drive credentials.

## Acceptance criteria

- AC-01: Given long or missing tender identity, technical-document generation
  emits `propuesta_tecnica.docx` and preserves the tender title/reference in the
  document content when present — verified by the focused Core generation tests.
- AC-02: A real generation manifest feeds Core's detailed delivery catalog,
  which declares exactly one `propuesta_tecnica.docx` with role
  `technical_document` — verified by a Core generation-to-catalog test.
- AC-03: Harness accepts and publishes the short DOCX, and a second detailed
  analysis publishes `propuesta_tecnica (YYYY-MM-DD).docx` without overwriting
  the first artifact — verified by focused Harness analysis and publication
  tests (the existing suffix test covers assessment only).
- AC-04: After the converted Google Doc in `Oferta` is renamed, dossier status
  remains adopted and another detailed analysis does not create a second live
  offer — verified by a dedicated fake-Drive Harness publication test named
  `test_renamed_live_offer_remains_registered`.
- AC-05: Core run documentation, Harness publication documentation, the public
  detailed-result example, and `CHANGELOG.md` describe the new filename and
  its scope without claiming that all Windows path limits disappear — verified
  by review of the task diff.
- AC-06: The complete Core and Harness pytest suites pass — verified by the
  repository's prescribed commands.

## Approach

Replace the title-derived filename in `TechnicalDocumentGenerator` with the
fixed portable basename `propuesta_tecnica.docx`. Keep the document plan's
identity fields and rendered title intact. Let the existing generation manifest,
Core artifact role, Harness role-based validation, date-suffix logic, and Drive
ID tracking carry the filename through publication.

Alternatives considered: a shorter title-derived name still varies with input
and can consume the path budget; a path-aware truncation policy adds complexity
for no business need when this deliverable has an unambiguous fixed role. This
change reduces a known variable path segment. Extremely deep configured work
roots remain outside its guarantee.

The public CLI schema and contract version need no change: they carry the
artifact's declared `name` and stable `role`, rather than prescribing this
specific technical DOCX basename. No ADR is needed for this scoped naming
decision; record it in the owning documentation and changelog.

## Implementation notes

- Change `core/src/litman_core/generation/technical_proposal/generator.py`;
  remove the obsolete title-based filename helper if it has no other callers.
  Do not remove the plan identity used inside the generated document.
- Replace the filename expectations in
  `core/tests/unit/generation/test_technical_proposal.py` with cases covering a
  long title and absent identity. Preserve meaningful assertions about visible
  document identity. Add a test that generates all detailed deliverables and
  passes their actual manifest to `detailed_analysis_delivery_catalog()`;
  assert the short name and technical role. Check the CLI tests for fixed
  filename assumptions, but retain explicit alternate-name fixtures where they
  prove the role-based contract rather than Core's default output.
- Update the default detailed artifact in `harness/tests/fakes.py` to mirror
  Core. Update affected Harness analysis/publication expectations and add a
  fake-Drive second-detailed-analysis assertion for the dated technical DOCX
  and preservation of the first artifact. Add a distinct rename-and-reanalysis
  test named `test_renamed_live_offer_remains_registered`. The existing implementation in
  `harness/src/litman_harness/dossier/publication.py` should not need a behavior
  change: `_available_name()` resolves repeats and `manifest.live_offer` stores
  `document_id`.
- Update `core/docs/contracts.md`, the relevant Harness publication text in
  `harness/docs/architecture.md` and `harness/docs/operations.md`,
  `docs/contracts/examples/success-detailed-analysis.json`, and `CHANGELOG.md`.
  Keep the root public contract's role-based wording. Document that the local
  filename is fixed while a repeated Drive upload may gain a date suffix and
  the live Google Doc may be renamed without losing its ID-based link.
- Preserve unrelated working-tree changes present before this design. No real
  Drive access or credentials are needed; use repository fakes.

## Tasks

```yaml
- id: CHG-11.1
  title: Use a fixed technical proposal filename and verify publication
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope:
    - core/src/litman_core/generation/technical_proposal/generator.py
    - core/tests/**
    - harness/tests/**
    - core/docs/contracts.md
    - harness/docs/architecture.md
    - harness/docs/operations.md
    - docs/contracts/examples/success-detailed-analysis.json
    - CHANGELOG.md
  integrate: pr
  acceptance:
    AC-01: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/unit/generation/test_technical_proposal.py'"
    AC-02: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/unit/generation/test_generation_service.py tests/unit/infrastructure/test_local_storage.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_analysis_service.py tests/dossier/test_publication.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_publication.py -k renamed_live_offer_remains_registered'"
    AC-05: manual
    AC-06: "bash -lc 'cd core && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q && cd ../harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions

- A custom work root can still make even a short path too long; this task does
  not promise support for arbitrary directory depth.
- The generated DOCX, its Drive artifact, and the converted Google Doc have
  distinct identities. The new filename applies to future generated DOCX files
  only; existing resources retain their IDs and names.
- No open product decision remains. The person chose PR integration.
