# CHG-12 — On-demand dossier drift reconciliation

## Context

Harness connects a Drive folder through personal OAuth. `status` loads
`_LitMan/manifest.json`, walks the dossier tree, lists unregistered original
candidates, and validates some registered IDs by membership
(`harness/src/litman_harness/dossier/service.py`, `tree.py`). The walk is bounded
at 2,000 resources. `Manifest.references()` currently omits published artifact
IDs and copied-original source IDs; the status check does not compare stored
names or original MD5. `recommended_action` follows the guided business flow
and may proceed while extra candidates remain (`dossier/recommendation.py`).

The v1 manifest stores registered originals with `file_id`, `observed_name`,
`md5_checksum`, placement/provenance, and analysis entries with immutable input
snapshots and published artifacts (`dossier/manifest.py`, `service.py`,
`publication.py`). Incorporation skips an already registered ID. Removing an
original from the list today would lose current registration, summary source
eligibility, and context representation. Recommendations and the context render
every registered original; no active/retired distinction exists. An accepted
summary stores source IDs and analysis IDs, and its refresh signal currently
depends only on subsequently published analyses (`dossier/summary.py`,
`context.py`, `recommendation.py`).

`read_file` and Google Docs/Sheets operations already check target membership.
Docs writes use a preview revision; Sheets writes re-read and hash the affected
ranges. Analysis plans verify selected originals' MD5 before and after download,
but preview accepts any eligible file ID inside the dossier and does not compare
a registered original to its manifest MD5 (`dossier/files.py`, `documents.py`,
`sheets.py`, `analysis/service.py`, `analysis/inputs.py`). `file_changes` permits
renaming registered originals and artifacts without updating their recorded
names; it blocks moving or trashing registered resources (`dossier/file_changes.py`).
These are verified code findings. We assume originals are ordinarily added or
removed, while material in `Oferta` and `Interno` is collaboratively edited.
No real Drive latency or account behavior has been measured for this design.

## Goal and scope

Make changes to registered dossier resources visible when the person requests
`status`, and make relevant operations check their own inputs before use. Offer
explicit, resumable preview/apply repairs for original registration and
retirement, visible names, and supported placements. No background watchers,
scheduled jobs, automatic analysis, silent manifest writes, or global Drive
searches. A read-only query never writes to Drive.

In scope: new original candidates; missing, trashed, inaccessible or moved-out
registered resources; name changes for recorded originals and artifacts;
registered-original MD5 differences as exceptional drift; originals outside
their registered folder; published artifact presence and folder placement;
external `contexto.md` edits; accepted summary sources affected by retirement
or loss of access, including copied-original source IDs; preservation of old analysis inputs;
targeted guards before analysis and registered-source reading; product-agent
guidance, Harness documentation and Unreleased changelog.

Out of scope: tracking each edit of `Oferta`, `Interno`, Google Docs/Sheets or
published output; in-place editing of PDF/DOCX/XLSX by Codex; full-content
rehashing of published artifacts on every status; replacing missing published
artifacts by a name match; changes to Core, product LLM invocation, Docker,
Core prompts, schemas, templates, or pipelines. Installed Harness agent
guidance for this workflow is in scope. Existing publication and context
checksums remain. No real credentials or Drive resources are used in tests.

## Acceptance criteria

- AC-01: Given an adopted v1 dossier, `status` reports deterministic drift for
  unregistered eligible originals, recorded-name changes, registered-original
  MD5 differences, misplaced originals and artifacts, and inaccessible or
  out-of-tree references including published artifacts, inaccessible accepted
  summary sources and externally edited `contexto.md`; it does not write or
  search outside the connected tree. A truncated walk says the candidate scan
  is incomplete and never claims a clean inventory — verified by fake-Drive
  status tests.
- AC-02: New files under registered `Interno`, `Oferta`, result and delivery
  folders are not proposed as originals; an eligible file elsewhere is only a
  candidate until explicitly selected. No candidate or unrelated drift forces
  a repeated recommendation loop — verified by tree and recommendation tests.
- AC-03: v1 manifests remain readable; v2 records active/retired originals and
  preserves existing IDs, copied-source provenance, analysis input snapshots,
  artifacts, accepted summary and operation history. A shared-state mutation
  upgrades v1 under the existing optimistic-concurrency gate; `status` does not
  migrate or write. Unknown versions remain read-only — verified by manifest,
  migration and gate tests.
- AC-04: An accepted retirement removes an original from future recommended
  analysis inputs without deleting, trashing, or rewriting its Drive file or
  old analysis source snapshots. Missing/inaccessible does not imply deleted;
  retirement requires the selected ID and person-accepted plan. A restored ID
  can be explicitly reactivated only with the same ID inside the dossier and
  the stored MD5; otherwise a different file must be registered as a new
  original — verified by reconciliation and analysis
  recommendation tests.
- AC-05: A summary citing a retired or unavailable source remains intact but
  is visibly flagged for review; a new summary cannot cite a retired source.
  Context shows active originals and marks a cited retired source without a
  misleading live link. Publication history is unchanged — verified by summary
  and context tests.
- AC-06: Accepted reconciliation of a recorded rename updates only that
  resource's current display name in the manifest and regenerated context.
  A moved original can be planned back into `Originales` using the existing
  move/copy/in-place rules; a published artifact moved within the dossier can
  be planned back to its registered analysis folder. An inaccessible resource
  is reported, never replaced by filename matching — verified by fake-Drive
  preview/apply tests.
- AC-07: Preview writes only a private account-bound plan. Apply rechecks the
  affected IDs, names, MD5 when relevant, membership, permissions, manifest
  content and context ETag; a changed input conflicts without overwriting it.
  Interrupted renames and moves resume by reading back the exact Drive ID and
  conflict if its state is neither the preview nor the accepted target state;
  operations resume without duplicate resources. A hand-edited
  context returns `context_conflict` rather than being overwritten — verified
  by conflict and recovery tests.
- AC-08: Before analysis, selected active registered originals are checked
  against the manifest MD5 and membership; a missing or changed selected input
  is explained before Core runs. A new unregistered eligible file is surfaced
  during analysis preview for human selection, never included by name alone.
  Reading/editing a target checks that target without a full dossier tree walk;
  unrelated internal edits do not block work — verified by service tests using
  call counters and the Core-run fake.
- AC-09: Renaming a managed original or published artifact through LitMan
  cannot silently leave the manifest name stale: it is handled by one accepted
  reconciliation plan or the general file-change preview directs the user to
  that plan. Existing Docs revision and Sheets range-conflict behavior is
  preserved — verified by file-change, Docs and Sheets tests.
- AC-10: `harness/docs/architecture.md`, `operations.md`, `decisions.md`, the
  installed `conectar-licitacion` and help resources, and `CHANGELOG.md` describe
  on-demand detection, confirmation, retirement and targeted checks without
  promising automatic writes or full artifact integrity validation — verified
  by review of the task diff and agent-resource registry tests.
- AC-11: The full Harness pytest suite passes using the repository-prescribed
  command — verified by `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q`
  from `harness/`.

## Approach

Use three layers. `status` performs a dossier inventory using metadata for
ordinary files and one content read/hash for the registered `contexto.md`,
alongside its existing manifest read. It returns a structured `drift` list
with stable codes, IDs, old/current values,
and a suggested next tool. Reuse the tree walk and fetched resources rather
than re-fetching every item when available; fetch known IDs individually to
distinguish out-of-tree or inaccessible resources. Do not claim an exhaustive
inventory when `tree_truncated` is true. Report Drive 403/404 as unavailable,
not definitively deleted. Compare original MD5, never Drive `version`, for
content drift. Compare artifact IDs, names and registered folder membership,
not contents; the stored publication SHA remains a publication snapshot.
Audit the distinct file IDs cited by the accepted summary, including
`copied_from`, without treating a copied source as the active registered copy.

Use the existing `preview_incorporation`/`apply_incorporation` pair to register
new originals. Add a closed `preview_reconciliation`/`apply_reconciliation`
pair with at most 20 closed actions: `retire_original(file_id)` and
`reactivate_original(file_id)` change shared state only;
`adopt_current_name(file_id)` accepts a manual Drive rename and changes shared
state only; `rename_managed(file_id, new_name)` renames the exact Drive ID and
updates shared state; `place_original(file_id)` uses the existing move/copy/
in-place rules; `return_artifact(file_id)` moves the exact published artifact
back to its recorded analysis folder when Drive permits. The existing
`preview_incorporation` pair registers new originals. Plans are bound to the active account, pin the manifest content
hash and observed Drive values, then apply with the existing shared-state
`If-Match`, operation markers and context conflict behavior. The action set is
explicit and bounded; no action infers replacement identity from a name.
The current `file_changes` path must reject direct managed renames with an
actionable code directing the caller to reconciliation (rather than leaving
metadata stale); reconciliation performs a requested managed Drive rename and
its manifest update under one accepted plan. Unmanaged file changes keep
working. After an interrupted rename or move, read the exact ID back: the
preview state means the action was not applied, the accepted target state
means it was applied, and any third state is a conflict. Never infer success
from a filename match elsewhere or claim it before manifest/context completion.

Introduce `litman-dossier-v2` only for the active/retired distinction. v1 is
read with every original active; the first accepted shared-state write by the
new Harness migrates it to v2 after optimistic-concurrency checks. Older
Harness versions already expose unknown versions read-only. Keep retired
entries with their ID and provenance, but exclude them from current analysis
recommendations and active reference checks. Historical analysis snapshots
remain immutable. Preserve existing accepted summary values and citations;
flag a summary source that is retired or unavailable and require a new
accepted summary to change its content. New summary plans may cite only active,
reachable originals or reachable published artifacts. A restored original can
be reactivated explicitly only on the same ID with unchanged stored MD5. Do
not add per-edit versions for living documents.

Use a targeted preflight in analysis preview and selected-source reading, not
a call to full `status` before every tool. `read_file`, Docs and Sheets keep
their existing target membership/revision or range guards. Their unrelated
operations do not trigger a dossier scan. Analysis preview may perform one
candidate scan because choosing complete inputs is part of that expensive
operation; execution still rechecks selected inputs immediately before Core.
Result publication and the new reconciliation operation recheck only their
own dependencies at apply time.

Alternatives considered: a full `status` before every tool would repeat a
folder-by-folder traversal for paged reads; automatic background polling would
write or alert without a user request; treating modified originals as ordinary
new versions would add state the stated workflow does not need; dropping
retired originals would break current summary provenance and obscure old
analysis sources. A v1-only optional field would be silently ignored by older
clients, which could include retired originals in new analyses. The v2 format
instead makes that incompatibility explicit. Record this lifecycle decision in
`harness/docs/decisions.md`.

## Implementation notes

- `harness/src/litman_harness/dossier/service.py` owns status/load-state,
  reference checks and incorporation. Keep `inspect` and generic file reading
  read-only. Add drift diagnostics through a small deterministic helper; do
  not add new dependencies, cache arbitrary Drive state, or expand the search
  beyond the connected root.
- `harness/src/litman_harness/dossier/manifest.py` owns v1/v2 parsing,
  lifecycle validation, active-original helpers and serialization. Preserve
  old v1 reading and avoid mutating status query results. `references()` must
  include current published artifact IDs; retired IDs remain historical, not
  active missing-resource errors. Audit accepted summary citations separately,
  including copied-original source IDs, without mistaking a deleted copy source
  for the active registered file. Detect external context edits by downloading
  and hashing only the registered context text.
- `harness/src/litman_harness/dossier/recommendation.py` and `context.py`
  must use active originals. A retired summary citation remains in the
  accepted summary but is labeled for review. Existing analysis history and
  source snapshots are never removed or rewritten.
- Add `harness/src/litman_harness/dossier/reconciliation.py` following
  `summary.py` and `file_changes.py`: closed actions, account-bound PlanStore,
  `ExpedienteService.apply_plan`, shared-state writes, `OperationRun` resume.
  Implement exactly the six closed actions and 20-action limit above; only
  `rename_managed`, `place_original`, and `return_artifact` may mutate Drive
  files outside shared state. `reactivate_original` requires same-ID
  membership and stored-MD5 equality. Rename/move retries use exact-ID
  read-back because creation markers do not apply to those Drive operations.
  Watch `action_id()` in `service.py`: it does not hash `metadata`, so plan
  actions that could share kind/resource/parent/name need a unique nonce in a
  hashed field. Treat a context conflict as a completed business operation
  with a reported conflict, consistent with incorporation.
- `harness/src/litman_harness/dossier/summary.py` should separate sources
  already cited by an accepted summary from sources eligible for a new one.
  `read_document` may continue reading a historical source only while the
  target remains accessible and within the dossier; `read_file` remains the
  general reader for unregistered work material.
- `harness/src/litman_harness/analysis/service.py` must distinguish selected
  active registered IDs from unregistered candidates. Preview should report
  candidate IDs, not silently broaden input selection. Existing MD5 checks in
  `analysis/inputs.py` remain the execution gate. Do not alter Core invocation
  or public CLI contract.
- `harness/src/litman_harness/dossier/file_changes.py` and product-agent
  resources must route managed renames to reconciliation; a plan already
  accepted before upgrade should fail safely if it would now leave stale
  manifest metadata. Preserve ordinary file operations and current Docs/Sheets
  guards. Update `harness/src/litman_harness/interfaces/tools/dossier.py`,
  assembly/registry wiring, and their interface tests for new operations.
- Use existing `harness/tests/fakes.py` and focused tests under
  `harness/tests/dossier/`, `analysis/`, and `interfaces/`. Ensure new test
  modules have unique basenames. Cover personal-account boundaries, read-only
  metadata mode (`pending_concurrency_gate`), v1 migration, concurrent manifest
  and context edits, moved/trashed/inaccessible files, copied originals,
  status truncation and call count. No real credentials or Drive calls.
- Update the owning Harness architecture/operations/decisions documentation,
  installed `conectar-licitacion` and `ayuda-litman` guidance, and Unreleased
  changelog. Keep product-agent resources in Spanish, repository artifacts in
  English, and no development skill changes. The Core package and shared Core
  CLI contract are outside this change.

## Tasks

```yaml
- id: CHG-12.1
  title: Diagnose registered dossier drift without Drive writes
  depends_on: []
  complexity: complex
  review: [quality, conformance]
  scope:
    - harness/src/litman_harness/dossier/service.py
    - harness/src/litman_harness/dossier/manifest.py
    - harness/src/litman_harness/dossier/recommendation.py
    - harness/tests/dossier/test_dossier_reconciliation.py
    - harness/tests/dossier/test_tree.py
    - harness/tests/dossier/test_recommendation.py
  integrate: pr
  acceptance:
    AC-01: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_reconciliation.py tests/dossier/test_tree.py'"
    AC-02: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_tree.py tests/dossier/test_recommendation.py'"
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-12.2
  title: Reconcile originals and managed references with accepted plans
  depends_on: [CHG-12.1]
  complexity: complex
  review: [quality, conformance]
  scope:
    - harness/src/litman_harness/dossier/manifest.py
    - harness/src/litman_harness/dossier/service.py
    - harness/src/litman_harness/dossier/reconciliation.py
    - harness/src/litman_harness/dossier/recommendation.py
    - harness/src/litman_harness/dossier/context.py
    - harness/src/litman_harness/dossier/summary.py
    - harness/src/litman_harness/dossier/file_changes.py
    - harness/src/litman_harness/interfaces/assembly.py
    - harness/src/litman_harness/interfaces/tools/dossier.py
    - harness/tests/dossier/**
    - harness/tests/interfaces/**
  integrate: pr
  acceptance:
    AC-03: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_reconciliation.py tests/dossier/test_dossier_service.py'"
    AC-04: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_reconciliation.py tests/dossier/test_recommendation.py'"
    AC-05: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_summary.py tests/dossier/test_dossier_reconciliation.py'"
    AC-06: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_reconciliation.py tests/dossier/test_file_changes.py'"
    AC-07: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_dossier_reconciliation.py'"
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
- id: CHG-12.3
  title: Guard relevant work and explain reconciliation in the product flow
  depends_on: [CHG-12.2]
  complexity: normal
  review: [quality, conformance]
  scope:
    - harness/src/litman_harness/analysis/service.py
    - harness/src/litman_harness/dossier/files.py
    - harness/src/litman_harness/dossier/summary.py
    - harness/src/litman_harness/dossier/file_changes.py
    - harness/src/litman_harness/interfaces/tools/analysis.py
    - harness/src/litman_harness/interfaces/tools/dossier.py
    - harness/agent/skills/conectar-licitacion/SKILL.md
    - harness/agent/skills/ayuda-litman/SKILL.md
    - harness/agent/workspace/AGENTS.md
    - harness/docs/architecture.md
    - harness/docs/operations.md
    - harness/docs/decisions.md
    - harness/tests/analysis/**
    - harness/tests/dossier/**
    - harness/tests/interfaces/**
    - CHANGELOG.md
  integrate: pr
  acceptance:
    AC-08: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/analysis/test_analysis_service.py tests/dossier/test_files.py tests/dossier/test_dossier_reconciliation.py'"
    AC-09: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q tests/dossier/test_file_changes.py tests/dossier/test_documents.py tests/dossier/test_sheets.py'"
    AC-10: manual
    AC-11: "bash -lc 'cd harness && UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q'"
```

## Risks and open questions

- Drive may return the same error for deletion and lost access. The UI must say
  unavailable, not deleted; only the person can choose retirement.
- A 2,000-resource truncated tree cannot prove the absence of new candidates.
  Known registered IDs can still be checked individually; report the scan as
  incomplete and never infer that an unlisted item is gone solely from the
  truncated walk.
- A manual rename can race with a reconciliation plan. Compare the observed
  name and manifest content again at apply; never overwrite a newer name.
- A managed rename changes Drive and shared state in separate API writes.
  Operation markers, read-back and local progress must allow safe resume; a
  failed manifest write must not be reported as full success.
- Existing v1 clients cannot write a v2 manifest. Release/update guidance must
  make that compatibility boundary explicit; v1 remains readable in new
  clients. This is a format version, not document version history.
- Existing accepted summaries may cite now-inaccessible originals. Preserve
  the accepted text and source ID, label the citation for review, and do not
  claim the text has been refreshed.
- No open product decision remains. The person selected PR integration and
  confirmed on-demand, approved changes rather than background activity.
