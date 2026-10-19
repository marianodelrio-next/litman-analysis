# CHG-0004 — Place tender originals in Originales and publish results without run folders

## Context
Verified on `master` at `e37b710`:

- Incorporation never moves or copies files. `ExpedienteService.preview_incorporation()`
  (`harness/src/litman_harness/dossier/service.py`) plans `create_folder` for each missing
  functional folder (`FOLDER_ROLES` in `dossier/manifest.py`: `originals` → `Originales`, …) and a
  `register_original` action per selected file; `_run_incorporation()` only appends the file's
  current ID to `manifest.originals` with `"provenance": "external"`. A person who connected a
  dossier therefore gets an empty `Originales` folder and the tender PDFs left in the root. This is
  what was observed on Windows with the Codex app.
- The person's Drive role can copy files but cannot move or delete them (a shared-drive
  "Contributor"-like role). Drive reports this per file in `capabilities`; the adapter currently
  requests only `canListChildren,canAddChildren,canDownload,canEdit` (`adapters/drive.py`,
  `_CAPABILITIES`). `DriveGateway` has no move or copy operation.
- Publication (`dossier/publication.py`) plans `create_run_folder` named
  `f"{completed_at[:10]} {publication_id}"` inside the registered phase folder (`initial` or
  `detailed`), uploads every artifact into it, records it as `analyses[].folder_id`, and returns
  `run_folder_id`. Core artifact names are fixed (`ficha_oportunidad.pdf`, `resumen_tecnico.docx`,
  `guia_preparacion_oferta.docx`, `simulador_economico.xlsx`, plus the technical proposal named from
  its plan), so without the run folder a repeated analysis would reuse the same names.
- `contexto.md` links `analyses[].folder_id` (`dossier/context.py`); `Manifest.references()` checks
  it; `_candidates()` already excludes everything below the `initial`/`detailed` folders, so the
  layout change does not affect inspection.
- `Manifest.summary_sources()` maps `originals[].file_id` to `"original"`; summary items cite
  sources by file ID and `read_document` reads only IDs from `summary_sources()`.
- `recommend()` (`dossier/recommendation.py`) has no Drive access; it receives precomputed inputs
  from `status()`.
- Tests: `harness/tests/fakes.py` (`FakeDrive`, `dossier_drive()`), `tests/dossier/test_dossier_service.py`,
  `tests/dossier/test_publication.py` (asserts `create_run_folder` and `run_folder_id`),
  `tests/analysis/test_analysis_publication.py`, `tests/dossier/test_recommendation.py`,
  `tests/adapters/test_drive_adapter.py`.

## Goal and scope
In scope:
1. Every original selected in an incorporation, and every original already registered outside
   `Originales`, ends up in the registered `originals` folder: moved when the person may move it,
   copied when they may only copy it, and left in place (with a visible warning) when they can do
   neither.
2. Analysis artifacts are uploaded directly into the registered phase folder (`Analisis inicial` /
   `Analisis detallado`) with no dated subfolder; a name already present gets a date suffix.
3. Affected docs: `harness/docs/architecture.md`, `harness/docs/decisions.md`,
   `docs/guia-litman-windows.md` and `docs/windows-codex-validation.md` where they describe
   incorporation or publication layout.

Out of scope: deleting or trashing any file (the root copy stays when only copying is allowed),
emptying a folder before a repeated analysis, migrating existing dated run folders, editing
documents (CHG-0005), Core, product prompts and the summary contract.

## Acceptance criteria
- AC-01: Given a selected original in the dossier root whose capabilities allow moving within the
  drive, when the incorporation is previewed and applied, then the plan shows `place_original` with
  strategy `move`, the file keeps its ID, its parents are exactly the `originals` folder, and
  `manifest.originals[].file_id` is that ID — verified by: test in
  `harness/tests/dossier/test_dossier_service.py`.
- AC-02: Given a selected original that can be copied but not moved, when applied, then a copy
  with the same name and MD5 is created in `originals` carrying the operation/action markers, the
  manifest registers the copy's ID with `provenance: "copied"` and `copied_from: <source id>`, the
  source stays untouched, and a later `status` no longer lists the source among
  `candidates.originals` (`inspect` has no manifest and keeps listing it) — verified by: test in
  `test_dossier_service.py`.
- AC-03: Given an original that can be neither moved nor copied (including a file whose
  capabilities omit `canMoveItemWithinDrive` and `canCopy`), when applied, then it is registered in
  place with `placement: "in_place"`, the preview action and the result carry a placement warning,
  and afterwards `status` does not recommend `organize_originals` for it (the guided flow reaches
  `run_assessment`, no loop) — verified by: tests in `test_dossier_service.py` and
  `test_recommendation.py`.
- AC-04: Given a planned `move` that Drive rejects with `insufficient_permission`, when applied,
  then the action falls back to `copy`; and given an interruption right after the copy was
  created, when the acceptance is repeated, then exactly one copy exists — verified by: tests in
  `test_dossier_service.py` (fake 403 on move; `crash_on_create`).
- AC-05: Given an adopted dossier whose registered originals are outside the `originals` folder
  and have no `placement: "in_place"`, with no pending publication, when `status` runs, then
  `recommended_action.kind` is `organize_originals` (tool `preview_incorporation`); when that
  preview is applied, then the originals are placed per AC-01–AC-03, a copied original keeps
  citations valid (`summary_sources()` and `read_document` accept its `copied_from` ID as an
  original), the next analysis plan uses the new ID, and a publication of an analysis that used the
  source ID still back-fills the original's `sha256`; a registered original whose current MD5
  differs from the manifest is not placed and gets a warning — verified by: tests in
  `test_dossier_service.py`, `test_recommendation.py`, `tests/dossier/test_summary.py` and
  `test_publication.py`.
- AC-06: Given an analysis to publish, when published, then no folder is created, every artifact's
  parent is the registered phase folder, `analyses[].folder_id` is that folder, the result returns
  `folder_id` instead of `run_folder_id`, and an artifact whose name already exists in that folder
  is uploaded as `<stem> (YYYY-MM-DD)<ext>` (then `<stem> (YYYY-MM-DD-2)<ext>`, …) with
  `YYYY-MM-DD` from the analysis `completed_at`; nothing existing is overwritten or removed; a
  resumed publication uploads nothing twice; a publication plan stored before this change (with
  `create_run_folder`) still resumes — verified by: tests in
  `harness/tests/dossier/test_publication.py` and `tests/analysis/test_analysis_publication.py`.
- AC-07: Architecture, decisions and both Windows guides describe the new placement and layout —
  verified by: manual conformance review.
- AC-08: The harness suite passes — verified by:
  `bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'`.

## Approach
**Placement strategy.** Decide per file at preview time from Drive capabilities, re-decide on
failure at apply time:

| Capability on the file | Strategy | Effect |
|---|---|---|
| `canMoveItemWithinDrive` is `true` | `move` | same ID, leaves the root |
| otherwise `canCopy` is `true` | `copy` | new ID in `Originales`, source stays |
| neither (a missing key counts as `false`) | `in_place` | registered where it is, `placement: "in_place"`, warning |

The target folder's `canAddChildren` is not checked at preview (the folder may be created by the
same plan); a refused write at apply goes through the fallback below. Already inside the
`originals` folder (the folder is an ancestor, checked with
`belongs_to_root(drive, originals_folder, item)`) → no placement action. An original recorded with
`placement: "in_place"` is never planned again (no loop); to retry, the person's permissions must
change and that is out of scope.

Alternatives rejected: copy and then trash the source (the person has no delete right, and it is
destructive for the team); always copy (duplicates files even when moving is allowed).

**Publication layout.** Upload into the phase folder, suffix on name collisions. Alternatives
rejected: empty the folder before a repeated analysis (deletes results the manifest, summary and
`contexto.md` still cite, and may lack permission); upload as a new revision of the previous file
(two analyses would share one file ID, breaking manifest traceability).

**Decision log.** Add two entries to `harness/docs/decisions.md`: "Originals are placed by
capability, never deleted" and "Results are published flat in the phase folder". The existing
decision "Publication is part of analysis execution" stays.

## Implementation notes
**CHG-0004-01 (originals).**
- `adapters/drive.py`: add `canMoveItemWithinDrive` and `canCopy` to `_CAPABILITIES`; add to
  `DriveGateway` and `GoogleDriveGateway`:
  `move(file_id, add_parent, remove_parents) -> Resource` (`files().update(fileId, addParents,
  removeParents, body={}, fields=_FIELDS, supportsAllDrives=True)`) and
  `copy(file_id, name, parent_id, operation_id, action_id) -> Resource` (`files().copy(fileId,
  body={"name", "parents": [parent_id], "appProperties": _markers(...)}, fields=_FIELDS, ...)`).
  Test both against the existing Drive adapter test style in `tests/adapters/test_drive_adapter.py`.
  Mirror them in `FakeDrive` (`tests/fakes.py`): `move` replaces `parents`; `copy` goes through
  `_create` (so `crash_on_create` works) with the source content; add a way to make `move` raise
  `HarnessError("insufficient_permission", …)` for given IDs. Check whether
  `adapters/metadata.py` (`MetadataGateway`) must satisfy the protocol; if so, make both methods
  raise the same read-only error its other writes raise.
- `dossier/service.py` `preview_incorporation()`: keep `register_original` exactly as today for
  new originals and add, for each of them and for each registered original not below the
  `originals` folder and without `placement: "in_place"`, a separate
  `PlanAction("place_original", <file id>, <name>, None, <md5>, {"strategy": …, "can_copy": bool,
  "role": "originals", "registered": bool, "warning": <Spanish text or None>})` after the folder
  actions (same `resource_id` as its `register_original`, so `action_id` stays stable). The
  target folder ID is resolved at apply time from `manifest.folders["originals"]` or the output of
  the plan's `create_folder` for that role. For a registered original, require the current Drive
  MD5 to equal `manifest.originals[].md5_checksum`; otherwise plan no placement and add the warning
  to the plan as a `place_original` with strategy `skipped`. A dossier whose only pending work is
  placement must not raise `no_changes`. Warnings travel in `PlanAction.metadata["warning"]`
  (already part of `Plan.json()`; no change to `plans/models.py`) and are copied into the apply
  result as `placement_warnings`.
- Existing fixtures: `dossier_drive()`'s `source` reports no move/copy capabilities, so it becomes
  `in_place`; keep it that way and add new fixtures with `canMoveItemWithinDrive`/`canCopy` for the
  new tests. Update existing incorporation tests whose expected action lists change.
- `_run_incorporation()`: run `place_original` after `create_folder`/`register_folder` and before
  building the manifest entries. `move`: fresh `get`; skip if already below `originals` (resume);
  otherwise `move(file_id, originals_id, remove_parents=<current parents from that get>)`; on
  `insufficient_permission` fall back to `copy` if `metadata["can_copy"]`, else `in_place`.
  `copy`: use `ensure_marked(run, action, originals_id, …)` like `create_folder` so a resume adopts
  the earlier copy; check containment like created folders and that the copy's `md5_checksum`
  equals `action.expected_version` (else `invalid_created_resource`). Store the outcome with
  `run.complete(action, {"strategy": …, "resource_id": …})`. For a new original the manifest entry
  uses the resulting ID; for a registered one, replace its `file_id` and set `copied_from` (keep
  `md5_checksum`, set `provenance: "copied"`). A `move` keeps `provenance: "external"`;
  `in_place` sets `placement: "in_place"`.
- `_verify_snapshot()`: a `place_original` resource must still be in the tree with the expected MD5
  (like `register_original`).
- `_candidates()`: exclude IDs listed in any `originals[].copied_from` (only effective in `status`,
  which passes the manifest).
- `Manifest.summary_sources()`: also map each `copied_from` to `"original"`. `Manifest.validate()`
  accepts the new optional keys (it does not restrict original keys today; keep it that way).
- `dossier/publication.py` `_run()`: the `sha256` back-fill also matches `original["copied_from"]`
  against `source["file_id"]`.
- `recommendation.py`: new `organize_originals` step placed after the `pending` publication check
  and before `run_assessment`, driven by a new `misplaced_originals: list[str]` argument computed in
  `status()` (registered originals not below the `originals` folder, excluding
  `placement: "in_place"`; empty when the folder is not registered). `recommendation_after()`
  passes none. Update the module docstring and the order list in `harness/docs/architecture.md`
  ("Guided product flow").
- User-facing messages in Spanish, like the existing ones.

**CHG-0004-02 (publication).**
- `dossier/publication.py` `preview()`: drop `create_run_folder`; each `upload_public_artifact`
  gets `parent_id = phase_folder.id` and its final name. Compute names from
  `self.drive.children(phase_folder.id, …)` plus names already chosen in this plan; suffix
  ` (YYYY-MM-DD)` then ` (YYYY-MM-DD-2)`, … before the extension (`Path.stem`/`suffix`). Names
  are compared exactly (case-sensitive), computed once in `preview()` and stored as `action.name`,
  so `action_id` and resume stay stable (`publish_after_analysis` reuses the saved plan). A same
  name appearing between preview and apply is accepted: Drive allows duplicates and nothing is
  overwritten. Keep `metadata["artifact"]` = the Core name so `_run()` can find the local file
  (today it looks up `local[action.name]`).
- `_run()`: upload to `action.parent_id`; `ensure_marked` with that parent; record
  `folder_id = phase folder`; return `folder_id` instead of `run_folder_id`.
  `_check_folders()`: check `upload_public_artifact` parents against the registered phase role
  instead of `create_run_folder`.
- `publication_intent()` is unchanged (its `publish_results` action already targets the phase
  folder). Grep for `run_folder` across `harness/` (src, agent, docs, tests) and update every use.
- Plans stored before this change still contain `create_run_folder`: keep handling it in `_run()`
  and `_check_folders()` (uploads without `parent_id` go to the run folder as today) and add a resume
  test with a pre-change plan.

## Tasks
```yaml
- id: CHG-0004-01
  title: Place incorporated and registered originals in the Originales folder by Drive capability
  depends_on: []
  complexity: complex
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/**", "harness/tests/**", "harness/docs/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_service.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_service.py'"
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_service.py tests/dossier/test_recommendation.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_service.py tests/adapters/test_drive_adapter.py'"
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier'"
    AC-07: manual
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-0004-02
  title: Publish analysis artifacts directly in the phase folder with date-suffixed collisions
  depends_on: [CHG-0004-01]
  complexity: normal
  review: [quality, conformance]
  scope: ["harness/src/litman_harness/dossier/publication.py", "harness/src/litman_harness/interfaces/**", "harness/agent/**", "harness/tests/**", "harness/docs/**", "docs/guia-litman-windows.md", "docs/windows-codex-validation.md"]
  acceptance:
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_publication.py tests/analysis/test_analysis_publication.py'"
    AC-07: manual
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions
- Assumption to confirm on the person's real account (manual step in
  `docs/windows-codex-validation.md`): that their role reports `canMoveItemWithinDrive: false` and
  `canCopy: true`, and that a shared-drive copy keeps `md5Checksum`. If `move` is reported allowed
  but fails, AC-04's fallback covers it.
- With copy-only permission the PDFs stay duplicated in the root; LitMan hides them from candidates
  but cannot remove them.
- Both tasks touch `harness/docs/architecture.md`, the Windows guides and `tests/fakes.py`, so
  CHG-0004-02 depends on CHG-0004-01. CHG-0005 and CHG-0006 also touch `tests/fakes.py`,
  `adapters/drive.py` and the Windows guides; expect small merges.
