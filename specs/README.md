# Specs

Find the exact SDL rules and formal contracts in this directory.
Normative prose follows the
[RAES SDL authority boundary](authority/authority-boundary.yaml).
Its authority does not depend on a reference implementation or generator.

For an authoring task, start with the [SDL guide](../docs/public/sdl/index.md).
For reasons behind the authority split, read the
[authority explanation](../docs/explain/reference/normative-artifact-authority.md).
To repeat local checks, use
[check specifications and contracts](../docs/develop/check-specification-contracts.md).

## Authority manifest

The machine-readable manifest identifies each authority root:

- [`specs/authority/authority-boundary.yaml`](authority/authority-boundary.yaml)
  — canonical authority manifest (ASR-517)

The decisions that govern this manifest:

- [ADR-009](../docs/decisions/adrs/adr-009-normative-artifact-authority-and-repository-structure.md)
  — the authority decision (immutable)
- [ADR-019](../docs/decisions/adrs/adr-019-normative-authority-boundary-manifest.md)
  — the canonical-seam decision that governs the manifest YAML

[`tools/check_authority_boundary.py`](../tools/check_authority_boundary.py)
compares the YAML, ADR-009, ADR-019, and this README in the CI policy lane.
Local commit hooks check hygiene and secrets.
No pre-push hook is configured.

## Subdirectories

- [`authority/`](authority/README.md): find the authority-boundary manifest.
- `agent-guidance/`: read the machine-readable guidance profile (AUT-811).
  The manifest's `normative_artifact_families` block classifies `agent-guidance.yaml` as `governance-guidance`.
  It overrides the root's default `prose` family.
  The [authority reference](authority/README.md) defines that rule.
- [`concept-authority/`](concept-authority/concept-authority.md): find concept families and controlled vocabularies under ADR-012.
- [`evolution/`](evolution/README.md): find versioning, deprecation, removal, and migration rules.
  ADR-075 governs GOV-901, GOV-902, and GOV-903.
- [`sdl/`](sdl/README.md): read the language-neutral SDL authoring reference.
  Its catalogs must agree with published `contracts/schemas/sdl/` schemas.
  ADR-001 and ADR-009 govern this reference.
- [`formal/`](formal/README.md): find optional formal artifacts for semantic and stateful subsystems.
  ADR-007 and ADR-018 govern the methods.
  ADR-081 governs the behavioral-relation taxonomy and claim discipline.
- [`supply-chain/`](supply-chain/README.md): read the Packaging & Supply Chain rules.
  They cover reusable-asset trust/authenticity/integrity, associated artifact manifests, and portable artifact requirement satisfaction.
  ADR-071, ADR-077, and ADR-098 govern them.

Revision-pinned lineage and derivation records remain in `contracts/provenance/`.
ADR-019 registers that normative authority.
Explanations consume those records and define no parallel source registry.
