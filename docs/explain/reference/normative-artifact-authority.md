# Normative Artifact Authority Guardrails

Contributor-facing guardrails for `ASR-517`. This note is explanatory; the
canonical authority boundary lives at
[`specs/authority/authority-boundary.yaml`](../../../specs/authority/authority-boundary.yaml),
governed by
[ADR-019](../../decisions/adrs/adr-019-normative-authority-boundary-manifest.md)
and enforced by
[`tools/check_authority_boundary.py`](../../../tools/check_authority_boundary.py).

`ADR-009` defines the repository-level authority boundary: normative prose,
schemas, fixtures, and conformance profiles are authoritative independent of
any reference implementation or code-generation pipeline. The canonical YAML
codifies that decision in a single machine-readable seam; `ADR-019` is the
canonical-seam decision that governs the YAML. This note remains as
contributor-facing reading material.

## Architecture Decisions

- `specs/` is the home for normative prose. Explanatory material belongs under
  `docs/`, and examples remain non-normative worked examples.
- `contracts/` is the home for normative machine-readable artifacts:
  published schemas, fixture corpora, capability profiles, semantic profiles,
  realization envelopes, and concept-authority catalogs.
- `implementations/` contains reference code only. Python models, CLI output,
  generated bindings, and conformance runners consume published authority; they
  do not define ecosystem meaning.
- `contracts/schema-publication-manifest.json` is the stable index for the
  sharded schema publication inventory under `contracts/schema-publication/`.
  The assembled catalog must stay aligned with `schema_bundle()` and
  `contracts/schemas/`.
- Code generation is support machinery. If a generated schema is published,
  the implementation must still describe it as a checked-in contract artifact,
  not as authority owned by the generator.

## Cross-Cutting Concerns

Reuse these existing surfaces before adding anything new:

- authority ADRs: `ADR-009`, `ADR-012`, and `ADR-014`
- normative prose surfaces: `specs/`, especially `specs/concept-authority/`
- machine-readable authority: `contracts/README.md`,
  `contracts/schemas/README.md`, `contracts/schema-publication-manifest.json`,
  `contracts/fixtures/`, `contracts/profiles/`, and
  `contracts/realization-envelopes/`
- contract model and schema bundle helpers:
  `raes_contracts.contracts.ContractModel`, `schema_bundle()`, and the
  published `*Model` validators
- manifest and profile authority helpers:
  `raes_contracts.manifest_authority`,
  `raes_contracts.backend_profiles`, `raes_contracts.semantic_profiles`,
  `raes_contracts.controlled_vocabularies`, and
  `raes_contracts.reference_models`
- generation and validation gates: `tools/generate_contract_schemas.py`,
  `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`, and
  `tools/check_json_artifacts.py`
- repo workflow gates: `.ground-control.yaml`, `.gc/plan-rules.md`,
  `noxfile.py`, `tools/check_repo_policy.py`,
  `tools/check_requirement_governance.py`, and `tools/verify_all.py`

## Security And Validation Gates

The authority-boundary work is mostly documentation and contract governance,
but it still passes through these gates:

- JSON parsing: contract artifacts must be local checked-in JSON loaded through
  the existing schema validation path; do not fetch remote schemas or execute
  fixture content.
- Contract shape validation: schemas, valid fixtures, concept-authority
  catalogs, and profiles must validate through `check-jsonschema` via
  `tools/check_json_artifacts.py` and the closed-world `ContractModel`
  descendants where Python validation exists.
- Publication validation: every published schema must have one independent
  record under `contracts/schema-publication/entries/`, and every record must
  point under `contracts/schemas/`.
- Schema authority direction (ADR-009 §7): the published schemas under
  `contracts/schemas/` are the hand-governed normative authority. A contract
  change is an edit to the published schema. A new schema also adds its record
  under `contracts/schema-publication/entries/`, and a deletion adds an
  independent tombstone record;
  `tools/check_generated_schemas.py` proves the reference implementation
  (`schema_bundle()`) still generates an identical bundle (into a throwaway
  directory — it never overwrites the published authority).
- Requirement governance: changed governed paths must carry the `ASR-517`
  context through the branch name or `RAES_REQUIREMENT_UID`, and Ground Control
  traceability must stay aligned.
- Secret and host exposure: authority docs, fixtures, diagnostics, command-line
  examples, and generated artifacts must not include bearer tokens,
  credentials, private keys, environment secrets, or instructions that place
  secrets in process arguments.
- Error-envelope leakage: any added tool or CLI surfaced by this work should
  reuse existing diagnostics/error patterns and avoid raw tracebacks or
  environment dumps.

## Extensibility Seam

The seam is the artifact family plus versioned `contract_id`, not a Python
class name, generator function, path convention, or profile-local table.

Adding an authoritative family should require a clear artifact location,
schema/profile/fixture registration where applicable, and one validation hook
in the existing manifest or contract-validation machinery. It should not
require re-editing unrelated consumers or copying a new authority list across
the repo.

Keep loader paths parameterized where they already are, such as
`fixtures_root`, `profiles_root`, and catalog roots used by contract helpers,
while keeping the defaults pointed at the checked-in `contracts/` authority.

## Gotchas And Anti-Patterns

Avoid:

- treating Python Pydantic models, generated JSON Schema output, or CLI output
  as the source of normative meaning
- creating duplicate schema registries, profile registries, fixture loaders,
  concept catalogs, vocabulary tables, or validation exception hierarchies
- collapsing concept authority, artifact schema authority, backend capability
  profiles, and semantic profiles into one generic "profile" or "runtime"
  bucket
- removing a published schema under `contracts/schemas/` without an
  independent tombstone record under `contracts/schema-publication/`, or
  treating a generator/Python
  edit as authorization for a schema change (the published schema is the
  authority; the generator only proves compatibility)
- adding new authority-bearing artifacts anywhere other than `specs/` (for
  normative prose) or `contracts/` (for normative machine-readable
  artifacts). `docs/`, `implementations/`, `examples/`, `research/`,
  `notes/`, and `tools/` are non-normative roots per the
  authority manifest and may not host authority artifacts
- preserving legacy or transitional path names as current authority when
  `ADR-009` already defines the target model
- making invalid fixtures multi-concern when one focused fixture can prove the
  contract rule

## Scope And Non-Goals

This page is contributor-facing reading material that accompanies the
shipped implementation of `ASR-517`. The actual authority boundary is
defined by:

- [`specs/authority/authority-boundary.yaml`](../../../specs/authority/authority-boundary.yaml)
  — canonical machine-readable manifest
- [ADR-019](../../decisions/adrs/adr-019-normative-authority-boundary-manifest.md)
  — canonical-seam decision
- [`tools/check_authority_boundary.py`](../../../tools/check_authority_boundary.py)
  — structural gate wired into `nox -s policy` (and therefore into
  `verify` and the pre-push hook)

This page is **not** itself authoritative. It does not add normative
artifacts, change schema generation direction, or supersede
[ADR-009](../../decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md).
Future changes to the boundary belong in the YAML and the immutable ADR
pair (`ADR-009` and `ADR-019`); this page evolves to track those decisions.
