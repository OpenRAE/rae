# ADR-009: Normative Artifact Authority and Repository Structure

## Status

accepted

## Date

2026-04-04

## Context

The repository already contains several kinds of ecosystem assets:

- prose documentation and architecture notes
- JSON Schemas for portable contracts
- conformance fixtures and profiles
- Python implementation code
- tests, examples, and research material

However, the current repo layout blurs authority boundaries.

Today:

- `schemas/` is described as language-neutral source of truth, but the schemas
  are generated from Python models in `src/aces/core/runtime/contracts.py`
- `conformance/` is backend-focused in name while validating broader runtime
  contract surfaces
- `src/aces/core/...` mixes authoring, semantics, processing, and contract
  concerns inside one implementation tree

That is workable for a single reference stack, but it is the wrong authority
model for a processor- and backend-agnostic ecosystem. A Rust processor, a Go
backend, or a mixed-stack implementation should be able to work from published
normative artifacts and fixtures without treating the Python codebase as the
real specification.

The updated requirements architecture now makes this explicit:

- normative prose, schemas, fixtures, and conformance profiles must have an
  authority boundary independent of any reference implementation
- processor and backend contracts must be implementation-language agnostic
- participant-implementation declarations and provenance surfaces must also be
  treated as portable ecosystem artifacts when they are first-class run
  components
- canonical run provenance and capability manifests are portable ecosystem
  artifacts, not Python-internal types

The repository therefore needs an explicit target structure and authority model
that separates normative assets from reference implementations.

## Decision

Adopt an explicit normative-artifact authority boundary and a target repository
structure that separates specifications, machine-readable contracts,
conformance assets, and reference implementations.

### 1. Normative artifacts are authoritative

The authoritative ecosystem artifacts are:

- normative prose specifications
- normative machine-readable schemas
- conformance fixtures
- conformance profiles

These artifacts define externally visible meaning and contract shape.
Reference implementations consume them; they do not define them.

### 2. Reference implementations are non-normative

Implementation code is a reference realization of the ecosystem, not its
authority boundary.

Internal package names, object models, storage choices, async model, transport
choices, and framework choices are non-normative unless they are surfaced as
published contracts.

This means the ecosystem must stay valid for:

- Python implementations
- Rust implementations
- Go implementations
- mixed-language or multi-service implementations

so long as they honor the published semantics, schemas, fixtures, and profiles.

### 3. Standardize the core artifact families

The repository will maintain distinct normative families for:

- SDL language/specification artifacts
- processor manifests and processor-facing contracts
- backend manifests and backend-facing contracts
- participant-implementation manifests and participant-facing declaration
  surfaces
- live execution/control-plane contracts
- archival run provenance artifacts
- experiment/evidence/provenance artifact boundaries
- conformance fixtures and capability profiles

These families are related, but they are not interchangeable and must not be
collapsed into a single "runtime contracts" bucket.

### 4. Establish the target repository shape

The target repository shape is:

```text
specs/
  sdl/
  processor/
  backend/
  artifacts/
  conformance/

contracts/
  schemas/
  fixtures/
  profiles/

implementations/
  python/
    packages/
      aces_sdl/
      aces_processor/
      aces_backend_protocols/
      aces_conformance/
      aces_cli/

docs/
examples/
research/
tools/
```

Within this shape:

- `specs/` contains normative prose
- `contracts/` contains normative machine-readable artifacts
- `implementations/` contains reference code only
- `docs/` contains explanatory, tutorial, and migration material
- `examples/` contains worked examples rather than normative fixtures
- `research/` remains non-normative context material
- `tools/` contains maintenance/codegen/release helpers

### 5. Treat current top-level directories as transitional

Existing directories such as:

- `schemas/`
- `conformance/`
- `src/`

are transitional until migration is complete.

During migration, they may remain in place for compatibility, but they are not
the final authority model.

### 6. Migrate in authority-first order

Migration should happen in this order:

1. define or refine normative prose under `specs/`
2. establish authoritative schemas, fixtures, and profiles under
   `contracts/`
3. make reference implementations consume those artifacts
4. move Python code into `implementations/python/`
5. deprecate legacy paths once compatibility shims are no longer needed

This order prevents the repository from doing a cosmetic file move without
actually changing the authority boundary.

### 7. Flip schema/codegen direction

Generating schemas from implementation-owned Python models is acceptable only as
a temporary compatibility aid.

The steady-state model is:

- normative schemas exist independently
- optional code generation may produce implementation bindings from those
  schemas
- validation proves implementation compatibility with normative artifacts

The repository must not present generated implementation-derived schemas as if
they were independent normative authority.

## Consequences

### Positive

- The ecosystem becomes credible as a processor- and backend-agnostic contract
  system rather than as a Python-first codebase.
- Independent implementations can build against published artifacts without
  reverse-engineering the Python package structure.
- Processor, backend, live-state, and provenance contracts become easier to
  reason about and version independently.
- Repo structure will reflect the requirements architecture instead of fighting
  it.

### Negative

- Documentation, packaging, build scripts, tests, and import paths will need a
  phased migration.
- Some duplicate or transitional artifacts will exist while the authority flip
  is in progress.
- Contributors will need clearer guidance about what is normative versus
  explanatory versus implementation-specific.

### Risks

- If the repository moves files before the authority boundary is actually
  flipped, the migration will create churn without improving portability.
- If legacy paths stay "temporary" for too long, contributors will continue to
  treat the old layout as authoritative.
- If code generation remains one-way from Python into schemas, the ecosystem
  will still be coupled to the reference stack in practice even if the folder
  names improve.

## Amendments

| Date | Commit/PR | Summary |
|------|-----------|---------|
| 2026-11-06 | #1943 | Schema-publication records no longer store a `content_hash` or a `last_change` block, and the `schema-change-missing-manifest` rule is removed. Git holds schema history. Breaking-change detection against the base branch and removal tombstones still govern published schemas. The decision text above is unchanged. |
| 2026-06-14 | #499 | Section 7 milestone recorded as reached: `contracts/schemas/` is the hand-governed normative authority, `tools/check_generated_schemas.py` is repurposed to prove the reference implementation generates an identical bundle without overwriting the published schemas, and a manifest change-ledger (`schema-publication-manifest.json` `last_change` for added/modified schemas and `removed_schemas` tombstones for deletions) plus the `schema-change-missing-manifest` policy rule govern schema edits. Remaining: optional code generation *from* the normative schemas into implementation bindings, and incidental per-feature/historical doc language that describes the former generation direction. This amendment records the milestone only; the decision text above is unchanged.
