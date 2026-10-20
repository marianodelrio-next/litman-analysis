# CHG-0009 — Explain dossier folders during initial organization

## Context

The user observed that initial dossier organization is described only as preparing
a working folder. The exact session transcript has not been inspected. Verified
repository behavior explains why such a brief response is possible:

- `harness/agent/skills/conectar-licitacion/SKILL.md`, steps 2–3, asks for a
  one-or-two-sentence summary and a business sentence before showing the plan,
  then immediately proposing the next recommended action after application.
  It does not require a folder explanation or a completion recap.
- `harness/src/litman_harness/dossier/service.py::_folder_actions` already emits
  `create_folder` or `register_folder` actions with the actual name and role.
  Already registered roles are omitted. `plans/models.py::Plan.json` exposes
  these actions in the preview.
- `dossier/manifest.py::FOLDER_ROLES` defines seven roles. Their business purposes
  already exist in `dossier/context.py::_ROLE_TEXT`.
- Incorporation creates or updates `contexto.md` in the dossier root and
  `manifest.json` under `_LitMan`. The apply result includes the manifest and
  operation evidence; `shared_result` can also report a context conflict.
- Product skills are installed resources, separate from Factory development
  skills; see `docs/architecture.md` and `harness/docs/development.md`.

## Goal and scope

Make the initial Drive dossier organization understandable before acceptance and
confirm its actual outcome before moving to the next action. This concerns the
Drive dossier, not the local `~/LitMan` installation workspace.

Change the installed `conectar-licitacion` skill, its affected documentation,
and the Unreleased changelog. Include focused validation evidence. This explicitly
authorizes changing that product-agent resource during implementation.

No backend, tool schema, folder layout, Core prompt, pipeline, installation
mechanism, or acceptance gate changes are needed. Do not perform real Drive
operations or access credentials for validation.

## Acceptance criteria

- AC-01: Given a fresh incorporation preview containing seven `create_folder`
  actions and context creation, the agent explains each actual folder name and
  purpose, the Drive location, and `contexto.md` before requesting acceptance.
  It speaks in future tense and does not claim the preview has written files.
  Verified by: a recorded manual conversation using the updated skill and
  synthetic tool responses, checked against the preview actions.
- AC-02: Given a partial incorporation preview with `create_folder` and
  `register_folder` actions, including an existing folder with a custom name,
  the agent distinguishes folders to create from existing folders to reuse,
  preserves actual names, and omits creation claims for roles absent from the
  plan. Original placement and context changes are described only when planned.
  Verified by: a recorded manual conversation with a mixed synthetic preview.
- AC-03: After an accepted incorporation, the agent summarizes confirmed created
  or reused folders and context outcome before the next recommendation. On
  failure, interruption, or `context_conflict`, it reports only confirmed effects,
  identifies incomplete or conflicting work, and does not claim full success.
  If evidence is insufficient it says so and may use the existing `recover`
  tool; it never retries through another route.
  Verified by: recorded manual conversations for success, an explicit apply
  failure, an interrupted apply with limited evidence, and an apply reporting
  `context_conflict`.

## Approach

Add explicit incorporation communication instructions alongside steps 2–3 of
`conectar-licitacion`. Keep routine status and other actions concise, but allow
a short folder list for incorporation so the current brevity instruction does
not suppress the explanation. Separate planned effects from confirmed effects.

Use `actions[].name` for the real name, `metadata.role` for its business purpose,
and the existing operation result for confirmation. Role descriptions may be
stated concisely in the skill, aligned with `_ROLE_TEXT`; no runtime dependency
on that private constant is introduced. The normal purposes are originals as
received, initial and detailed analysis results, live offer and working material,
internal company material, delivered versions, and LitMan technical state.

Mention `contexto.md` as the dossier map when its creation or update is planned.
Explain `_LitMan` as technical state and avoid unnecessary manifest details.
If file placement is mentioned, respect the planned move/copy/in-place/skipped
strategy and actual result, rather than saying all originals were moved.

Alternatives considered: a generic instruction to “explain more” remains
ambiguous; always listing seven default folder names misrepresents partial
plans and custom names; a new backend presentation payload adds an interface
change despite sufficient existing evidence. The explicit skill rule is the
smallest scoped solution. No ADR is required.

## Implementation notes

- Update `harness/agent/skills/conectar-licitacion/SKILL.md`; preserve existing
  preview/accept/apply semantics, recommendation routing, and tool restrictions.
  Follow the repository publication rule: new or rewritten instruction text and
  published documentation are English; user-facing conversations follow the
  person's language. Existing Spanish folder/file names remain literal names.
- Update the product-resource description in `harness/docs/architecture.md`
  and add an entry under `## [Unreleased]` in `CHANGELOG.md`.
- Record a concise manual validation report under
  `harness/docs/validation/CHG-0009.md` with synthetic inputs, observed responses,
  per-AC verdicts, agent/model used, and limitations. Exercise the actual updated
  skill with stubbed tool responses, not just a hand-written ideal response.
  Use an isolated agent conversation with the updated skill as its product
  instructions and no live Drive tools. The evaluator supplies a user request,
  lets the agent request the next tool, and supplies the matching synthetic
  JSON response as evaluation data. Continue through preview, user acceptance,
  and apply result; record tool requests as well as user-facing text. This
  manual protocol needs no new runner, dependency, or product-code change.
  Include six cases: fresh preview/success, mixed preview with a custom existing
  folder name, apply failure, interruption with only partial completion evidence,
  context conflict, and a preview-only turn before user acceptance. Cases may
  share fixtures. Base fixture keys on `Plan.json`, `shared_result`, and
  `OperationRun.envelope`; do not invent backend fields. Check each output
  against the AC rubric and document deviations rather than rewriting responses.
  No real Google resources are required. If such execution is unavailable,
  leave the conversational acceptance criteria unverified and report the gap.
- Existing installation coverage is in `harness/tests/test_installation.py`.
  Check that installed `conectar-licitacion/SKILL.md` equals its repository
  source for Codex and Claude using temporary homes and mocked registration;
  extend the existing relevant installation tests if necessary. This proves
  delivery, not conversational compliance. Avoid fragile exact-prose assertions.
- Run `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv run pytest -q` from `harness/`
  during implementation. Core and Docker validation are unrelated to this scope.
- Keep manual validation evidence separate from automated suite results; passing
  installation tests alone does not prove AC-01 through AC-03.

## Tasks

```yaml
- id: CHG-0009-01
  title: Explain planned dossier folders and confirm incorporation outcomes
  depends_on: []
  complexity: normal
  review: [quality, conformance]
  scope:
    - harness/agent/skills/conectar-licitacion/SKILL.md
    - harness/docs/architecture.md
    - harness/docs/validation/CHG-0009.md
    - harness/tests/test_installation.py
    - CHANGELOG.md
  acceptance:
    AC-01: manual
    AC-02: manual
    AC-03: manual
```

## Risks and open questions

- A skill constrains intent but cannot guarantee identical wording across
  agents or models. Manual conversations verify representative cases, not
  universal compliance.
- Role descriptions in the skill can drift from the existing context map;
  reviewers must compare them with `_ROLE_TEXT`.
- Existing installations need their normal resource update before using the
  revised skill; this task does not update the person's installed environment.
- No unresolved product decision remains. Availability of a stubbed agent
  conversation runner must be established during implementation; lack of a
  runner is a validation gap, never grounds to fabricate acceptance evidence.
