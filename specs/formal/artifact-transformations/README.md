# Artifact transformation invariants

This subsystem defines the bounded FM2 obligations for AUT-810. The executable
surface consists of operation-specific functions in `raes.transformations`,
the closed `artifact-transformation-report/v1` contract, and the focused
transformation conformance corpus. It is not a generic patch or migration
language.

## Invariants

For an admitted source artifact (S), explicit request (R), and closed policy
(P), an operation returns exactly one of:

1. **Complete success:** an independently reconstructed and admitted target
   (T), plus a report whose target digest binds (T); or
2. **Complete refusal:** no target and a report containing at least one bounded
   diagnostic for a failed condition.

The following invariants hold for both outcomes:

- **Purity and isolation.** The output is a newly admitted value derived only
  from explicit arguments. The source's canonical bytes do not change.
- **Determinism.** Equal canonical inputs, request, and policy produce equal
  canonical output and equal reports. Reports contain no clock, random,
  filesystem, network, process, or caller-identity input.
- **Exact selection.** SDL declarations are selected by one exact canonical
  address. Aliases, collisions, unsupported identities, and ambiguity are
  refusals.
- **Admission closure.** Complete structural and semantic admission runs after
  every SDL candidate is reconstructed. A dangling or illegal resolved
  reference cannot be returned as output.
- **Named comparison.** Preservation is recorded under a named profile and a
  bounded evidence set, never as an unqualified Boolean claim.
- **Loss authorization.** Loss is rejected by default. Success with loss
  requires the policy to name every allowed loss kind and the report to carry
  the corresponding typed loss diagnostic.
- **Linked-artifact consistency.** Supplied external-concept subjects must bind
  the exact source digest. A rename retargets every supplied subject digest and
  the changed canonical reference atomically; stale documents cause refusal.

For declaration rename, let (f) map the selected address to its replacement.
It also maps each canonical address derived under that declaration to the same path under the replacement (ADR-076 §3).
Examples include services, runtime-family records, content items, and child entity paths.
It acts as identity on every other address, including a namespaced declaration whose key starts with the selected key.

The report's `identity_map` lists only the selected declaration.
A supplied external-concept binding with a derived-address subject causes refusal (`artifact-transformation.linked-artifact-stale`).
Issue #1586 tracks retargeting that subject.
The `sdl-declaration-identity-transport/v1` check requires:

- (f) is injective over the declaration index;
- the declaration kind and declaration count are unchanged;
- every rewritten reference is admitted against the target index; and
- applying (f^{-1}) to the admitted target restores the source's canonical
  SDL bytes.

The implementation evaluates the last condition with the inverse rename.
That operation shares the forward rewrite.
It therefore misses a rewrite of a section-qualified reference to a namespaced sibling.
An example is `nodes.shared.web` when root node `shared` is renamed.
Issue #1585 tracks this limitation.

This is finite verification over the supplied artifacts. It does not prove
behavioral, observational, epistemic, strategic, backend, or scientific
equivalence. `canonical-artifact-identity` establishes equality only under the
named owning canonicalization profile.

## Executable evidence

- Unit, property, composition, reference, loss, concept-binding, and portable
  contract coverage: `implementations/python/tests/test_artifact_transformations.py`
- Nested service, runtime-family, and content-item reference renames:
  `implementations/python/tests/test_issue_1573_rename_nested_references.py`
- Typed portable report: `contracts/schemas/artifact-transformations/artifact-transformation-report-v1.json`
- Focused cases: `contracts/fixtures/artifact-transformations-v1/cases`
- Case executor: `implementations/python/packages/raes_conformance/artifact_transformations.py`
