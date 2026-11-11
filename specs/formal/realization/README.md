# Realization semantics

This directory holds the normative semantic boundary for binding author
declarations versus concerns left open to backend realization (`SEM-218`).
In RAES the processor layer does not realize underspecified author
concerns: it compiles the typed runtime requirement and plans against
backend support. Realization happens at the backend layer, and only
backend manifests carry `realization_support`.

## Scope

- the three-class taxonomy of author intent: exact declaration, constrained
  declaration, open realization
- the rules that decide when realization is permitted, when an explicit
  declaration must be honored, and when an unsupported exact requirement
  must be rejected rather than silently approximated
- the cross-stage gate that the SDL, processor, and backend layers must
  pass for those rules to hold across authoring, validation, instantiation,
  compilation, planning, execution, and observation
- the capability-disclosure surface on **backend** manifests that
  declares which exact-requirement-kinds and constraint-kinds the
  backend supports, and the per-domain support mode that governs how
  those kinds may be realized — processor manifests carry no
  `realization_support` because the processor layer does not realize
  underspecified concerns
- the proposed realization-envelope semantics for issue #667: a
  versioned expression that denotes a set of scenario instances and
  supports membership, subsumption, witness generation, scoped
  closed-world posture, and negative conformance

## Out of scope

- new SDL syntax for declaring exact, constrained, or open authoring
  intent — the existing closed Pydantic SDL models, controlled
  vocabularies, semantic profiles, and apparatus manifests carry the
  necessary surfaces
- enumerating every future exact-requirement-kind or constraint-kind;
  governed extension happens through the controlled-vocabulary,
  reference-model, and semantic-profile authorities
- wave-3 participant semantics (`SEM-208`–`SEM-229`) that build on this
  boundary — those have their own owning requirements

## Realization status

The semantic boundary is normative.
The [explicitness reference](explicitness-and-realization.md#realization-status) maps enforcement across all seven `SEM-200` lifecycle phases.
It names the apparatus shape gates, SDL classifier, instantiation metadata, compiler emission, planner admission, runtime checks, and provenance ledger.
The [coverage reference](../../../docs/explain/reference/shared-semantic-integrity.md) records the `SEM-218` family as `active` across those seven phases.
The earlier authoring/validation/instantiation-only summary no longer describes the delivered reference implementation.
These bounded reference checks do not qualify every external backend.

## Implementation mapping

- realization support modes: `implementations/python/packages/raes_contracts/vocabulary.py`
  (`RealizationSupportMode`)
- apparatus declarations:
  `implementations/python/packages/raes_contracts/apparatus.py`
  (`RealizationSupportDeclaration`, `ConceptBinding`, `ApparatusIdentity`)
- contract-model gates and JSON schema (backend manifest):
  `implementations/python/packages/raes_contracts/contracts/`
  (`RealizationSupportDeclarationModel`)
- processor-vs-backend asymmetry:
  `implementations/python/packages/raes_contracts/contracts/`
  (`ProcessorManifestV2Model` rejects `realization_support`)
- backend-manifest payload encoding:
  `implementations/python/packages/raes_backend_protocols/manifest.py`
- native concept family for realization semantics:
  `contracts/concept-authority/concept-families-v1.json`
  (`realization-and-disclosure`)
- SDL classifier and instantiation downgrade:
  `implementations/python/packages/raes/explicitness.py`,
  `implementations/python/packages/raes/validator/`,
  `implementations/python/packages/raes/instantiate.py`
- invalid fixtures evidencing fail-closed rejection:
  `contracts/fixtures/backend-manifest/backend-manifest-v2/invalid/hollow-realization-support.json`,
  `contracts/fixtures/backend-manifest/backend-manifest-v2/invalid/malformed-realization-support.json`,
  `contracts/fixtures/processor-manifest/processor-manifest-v2/invalid/hollow-realization-support.json`,
  `contracts/fixtures/processor-manifest/processor-manifest-v2/invalid/malformed-realization-support.json`

## Tests

- `implementations/python/tests/test_backend_manifest.py` — shape-gate
  rejection of hollow / malformed backend `realization_support`
- `implementations/python/tests/test_processor_manifest.py` — processor
  manifest rejection of any `realization_support` section
  (`test_processor_manifest_v2_rejects_realization_support_section`)
- `implementations/python/tests/test_runtime_contracts.py` — JSON-schema
  conditional gate for backend manifests and the assertion that the
  generated processor schema carries no `realization_support` property
- `implementations/python/tests/test_sem_218_explicitness.py` —
  classifier coverage for exact, constrained, and open SDL declarations,
  instantiation downgrade, and unclassifiable variable diagnostics

## Notes

- `explicitness-and-realization.md` is the normative semantic boundary for
  `SEM-218`. It is the citable source for "is this declaration binding?",
  "when may a realizer pick a value?", and "must this unsupported exact
  requirement be rejected?".
- `envelope-semantics.md` is the design authority for issue #667. It is not
  executable yet; it defines the future formal seam that replaces the #663
  `reference_scenario` bridge once the schema, relation helper, and
  conformance probes land.
- The non-normative companion at
  `docs/explain/reference/explicitness-realization-semantics.md` records
  the architecture guardrails for the implementation that realizes the
  spec; it is implementer-facing reference and not itself authoritative.
- `SEM-218`'s coverage row in
  `docs/explain/reference/shared-semantic-integrity.md` tracks realization
  status across the seven `SEM-200` lifecycle phases.
