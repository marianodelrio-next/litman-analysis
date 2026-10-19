# CHG-0001 — Archive the completed bid preparation guide simplification

## Context

This is a historical migration of the completed `.agent-work/simplificar-guia-preparacion-oferta/` task, not a request to rebuild the product. Its old design was approved and its final progress reported satisfactory review, no blockers, and a compact operational guide with five numbered sections. At migration time, `core/src/litman_core/generation/bid_preparation_guide/generator.py` identifies the artifact as `bid-preparation-guide`, version `bid-preparation-guide-generator-v4`, with filename `guia_preparacion_oferta.docx`. The renderer and `core/tests/unit/generation/test_bid_preparation_guide.py` cover the guide's current structure. On 2026-10-19 the focused suite passed: 5 passed.

The former progress record reported 153 passed, 2 skipped for the full Core suite at its completion. That is historical evidence, not a claim about the current full suite. The durable product contract is already recorded in `core/docs/decisions.md`.

## Goal and scope

Represent one completed legacy task in Factory so its history and current verification are visible. The single Factory task is a retrospective verification and record cleanup. The guide generator, renderer, tests, product prompts, schemas, and pipelines are outside this migration's change scope.

## Acceptance criteria

- AC-01: The current bid preparation guide still has five ordered operational sections, keeps offer documents, requirements, criteria, and pending actions, and omits the evidence appendix — verified by: `UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv --directory core run pytest -q tests/unit/generation/test_bid_preparation_guide.py`.
- AC-02: The retired `.agent-work/` tree is removed after this task's completion evidence is represented here, while the durable guide decision remains in `core/docs/decisions.md` — verified by: `test ! -e .agent-work && test -f core/docs/decisions.md`.
- AC-03: Factory shows one task whose title and scope clearly state that product implementation is already complete and only historical verification remains; the generator identity recorded above matches the current source — verified by: `swfactory design show CHG-0001 --json` and manual review of this design and `core/src/litman_core/generation/bid_preparation_guide/generator.py`.

## Approach

Migrate the old task's outcome and current evidence into this concise Factory design. Keep the implementation and durable product decision in their existing files. The old local task folder was removed after this design validated; the remaining retired `.agent-work/` tree was removed at the person's request. A full copy of the long old design was considered but would duplicate the current contract and make the sample harder to inspect. No ADR is needed because this migration introduces no new product decision.

## Implementation notes

The verified product paths are `core/src/litman_core/generation/bid_preparation_guide/{generator,renderer}.py`, `core/tests/unit/generation/test_bid_preparation_guide.py`, and `core/docs/decisions.md`. The former work record was in an ignored local directory. The Factory task should verify the current state and finish through the normal CLI gates after the change receives its own explicit approval; it must not infer that approval from the legacy `Approval status: approved` line.

## Tasks

```yaml
- id: CHG-0001-01
  title: Verify the completed bid preparation guide migration
  depends_on: []
  complexity: trivial
  review: []
  acceptance:
    AC-01: "UV_CACHE_DIR=/tmp/licitaBot-uv-cache uv --directory core run pytest -q tests/unit/generation/test_bid_preparation_guide.py"
    AC-02: "test ! -e .agent-work && test -f core/docs/decisions.md"
    AC-03: manual
```

## Risks and open questions

Factory has no historical import that can mark a legacy task done without a new named approval and task lifecycle. Until that happens, this task appears as awaiting approval even though the product work is complete. The old record's full-suite result is historical; only the focused test has been rerun for this migration. There are no product code changes or open functional decisions in this change.
