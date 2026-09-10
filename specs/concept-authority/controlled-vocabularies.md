# Controlled Vocabularies And Enumerations

## Scope

This specification defines the controlled-vocabulary authority surface for
portable declared terms whose values must compare consistently across RAES
artifacts.

It distinguishes two cases:

- closed enumerations, where the portable term set is fixed
- governed-extension vocabularies, where the portable base terms are fixed but
  controlled extension space remains available for RAES-native, experimental,
  or still-evolving declarations

Controlled vocabularies do not replace concept families, reference models, or
semantic profiles. They govern the stable term sets used inside those other
surfaces where cross-artifact comparison depends on shared portable values.

## Decision Record

[ADR-012](../../docs/decisions/adrs/adr-012-shared-concept-authority-and-raes-extension-discipline.md)
governs this specification.

## Controlled Vocabulary Catalog

Each controlled-vocabulary catalog declares:

- a stable `schema_version`
- a keyed `vocabularies` map

Each vocabulary declares:

- a human-readable `title`
- a `description`
- optional `source` metadata when the vocabulary base terms are adopted from or
  adapted from an external authority
- a `kind`, either `enumeration` or `vocabulary`
- optional `governed_scopes` identifying the published contract fields that
  use the vocabulary
- an `extension_policy`, either `closed` or `governed-extension`
- an `extension_pattern` when governed extensions are allowed
- a keyed `terms` map whose property names are the portable term identifiers

Controlled vocabulary identifiers are authoritative at the map key. They are
not duplicated inside each vocabulary object.

When `source.provenance` is `adopted`, base terms must preserve the cited
external authority's identifiers, names, URLs, and descriptions exactly as
published in the pinned source artifact. RAES may bind those terms to its own
fields and may permit governed extensions, but it must not rewrite the adopted
base-term meanings.

When `source.provenance` is `adapted`, the pinned source artifact must preserve
the external identifiers and source text while each catalog description clearly
states the narrower RAES binding. Adaptation must not claim endorsement or
conformance by the external authority.

### Enumeration Rules

Closed enumerations are for stable portable values where cross-artifact
comparison must remain exact.

Enumerations:

- must use `extension_policy: closed`
- must not declare `extension_pattern`
- may declare governed scopes when they are bound to a published field surface

### Governed-Extension Rules

Governed-extension vocabularies are for portable terms that need stable shared
comparison today while still permitting disciplined local extension space.

Governed-extension vocabularies:

- must declare at least one governed scope
- must declare an `extension_pattern`
- must use only governed scopes owned by the published contract surfaces

Extension values are valid only when they match the declared extension
pattern. Values that are neither declared portable terms nor valid governed
extensions are invalid.

## Initial Catalog

The initial GOV-922 catalog is:

`contracts/concept-authority/controlled-vocabularies-v1.json`

It defines:

- closed enumerations for processor features, workflow features, workflow
  state-predicate features, realization support modes, and concept provenance
  categories
- governed-extension vocabularies for backend capability surfaces where stable
  portable terms exist but controlled local extension space is still needed:
  provisioner node types, compute substrates, operating-system families, node CPU architectures,
  content types, account features, orchestrator supported sections, and
  evaluator supported sections
- a governed-extension vocabulary for
  `participant-offensive-behavior-activities`, whose base terms are a direct
  adoption of MITRE ATT&CK Enterprise tactics v19.1. The pinned source artifact
  is `contracts/concept-authority/attack-enterprise-tactics-source-v1.json`;
  the upstream STIX bundle is
  `https://raw.githubusercontent.com/mitre-attack/attack-stix-data/v19.1/enterprise-attack/enterprise-attack-19.1.json`;
  the recorded bundle digest is
  `sha256:bdf1ce86a4e604214c5076d37ae4dcb322678afc528df8492e6fdc1b554f5da3`.
  MITRE's ATT&CK version history, data and tools page, and terms of use are
  recorded in the source artifact's `citation_urls`.
- a separate governed-extension vocabulary for
  `participant-ai-offensive-behavior-activities`, whose base terms are a direct
  adoption of MITRE ATLAS tactics release v2026.06 (`collection.version`
  `2026.06`, `format-version` `6.0.0`). The pinned source artifact is
  `contracts/concept-authority/atlas-tactics-source-v1.json`; the upstream
  YAML release asset is
  `https://github.com/mitre-atlas/atlas-data/releases/download/v2026.06/ATLAS-2026.06.yaml`;
  the recorded asset digest is
  `sha256:b771de8b1489564b2838a709c7429849a9575dbd94073928817fe1a21661e70a`.
  MITRE ATLAS release, data-format, project, and license citations are recorded
  in the source artifact's `citation_urls`.
- an independent governed-extension vocabulary for
  `participant-defensive-behavior-activities`, whose base terms adapt the eight
  active NIST CSF 2.0 Detect, Respond, and Recover categories. The pinned source
  artifact is
  `contracts/concept-authority/nist-csf-defensive-categories-source-v1.json`;
  it records the official Core export URL, CSWP 29 citations, retrieval date,
  NIST use notice, and the canonical category-snapshot digest
  `sha256:014492980e87f8ce2c98d80ea040540392de96a08980c2f9901114ad4108b2c3`.

The MITRE notice for the adopted ATT&CK terms is recorded in the source
artifact and catalog metadata:

> &copy; 2026 The MITRE Corporation. This work is reproduced and distributed with
> the permission of The MITRE Corporation.

### ATT&CK Adoption Guardrail

The ACT-609 base term set is not editable by hand. To move from ATT&CK v19.1 to
another ATT&CK release, a change must update all of the following together:

- the pinned source artifact, including `source_version`, `source_url`,
  `source_digest`, retrieval date, citations, and license notice
- the adopted vocabulary terms in
  `contracts/concept-authority/controlled-vocabularies-v1.json`
- the controlled-vocabulary valid fixture
- generated schemas and the schema publication manifest when the source schema
  changes
- `tools/check_attack_tactic_vocabulary.py` evidence or test expectations for
  the new pinned release

### ATLAS Adoption Guardrail

The ACT-609 AI-offensive base term set is also not editable by hand. It is a
separate direct adoption of MITRE ATLAS tactics, not an extension or mutation of
the ATT&CK vocabulary. To move from ATLAS release v2026.06 to another ATLAS
release, a change must update all of the following together:

- the pinned ATLAS source artifact, including `source_version`,
  `source_format_version`, `source_url`, `source_digest`, retrieval date,
  citations, and license notice
- the adopted ATLAS vocabulary terms in
  `contracts/concept-authority/controlled-vocabularies-v1.json`
- the controlled-vocabulary valid fixture
- generated schemas and the schema publication manifest when the source schema
  changes
- `tools/check_atlas_tactic_vocabulary.py` evidence or test expectations for
  the new pinned release
- affected authoring and behavior-model documentation

ATT&CK, ATLAS, and NIST CSF remain distinct optional source catalogs. Their
`governed_scopes` are empty and their adopted term sets are closed. Generic
[external concept bindings](external-concept-bindings.md) carry explicit scheme
coordinates; no catalog governs a privileged SDL classification field.
Extensions require their own explicit source context, not an implicit adopted
authority.

`tools/check_attack_tactic_vocabulary.py` is part of the contract verification
stage. Its default offline mode compares the catalog to the pinned source
artifact. Its `--verify-remote` mode fetches the pinned upstream STIX bundle,
verifies the recorded SHA-256 digest, extracts Enterprise tactics in matrix
order, and compares them to the checked-in source artifact.

`tools/check_atlas_tactic_vocabulary.py` is part of the same contract
verification stage. Its default offline mode compares the catalog to the pinned
ATLAS source artifact. Its `--verify-remote` mode fetches the pinned upstream
YAML release asset, verifies the recorded SHA-256 digest, extracts ATLAS tactics
in matrix order, and compares them to the checked-in source artifact.

### NIST CSF Adaptation Guardrail

The ACT-610 base terms are adapted classifications, not claims that a NIST CSF
outcome was achieved. A source update must change the pinned category snapshot,
catalog, valid fixture, generated schemas and publication ledger when needed,
documentation, and `tools/check_nist_csf_defensive_vocabulary.py` together.
The checker's normal mode is offline. Its explicit `--verify-remote` mode
downloads the official NIST Core export, extracts the eight active categories,
and compares their canonical semantic digest and content with the checked-in
snapshot.

## Machine-Readable Artifacts

The JSON Schema for the catalog format is published at:

`contracts/schemas/concept-authority/controlled-vocabularies-v1.json`

The source-snapshot schema for the NIST CSF defensive adaptation is published
at:

`contracts/schemas/concept-authority/nist-csf-defensive-categories-source-v1.json`

The valid and invalid fixture corpus for controlled vocabularies is published
under:

`contracts/fixtures/concept-authority/controlled-vocabularies-v1/`

## Validation Expectations

Contract and runtime validation must treat the catalog as the authority for
the governed surfaces it declares.

For governed apparatus-manifest capability fields:

- declared base terms must validate against the catalog
- extension values must match the governed extension pattern
- closed enumerations must reject extension values

## Relationship To Other Requirements

- GOV-917: canonical concept authority
- GOV-918: cross-artifact concept binding
- GOV-919: disciplined RAES-native extensions
- GOV-920: shared semantic profiles
- GOV-921: shared reference models
- GOV-922: controlled vocabularies and enumerations
