# Supply Chain Specs

Normative prose for the **Packaging & Supply Chain** wave, under the
[RAES SDL authority boundary](../authority/authority-boundary.yaml). Documents
here are authoritative independent of any reference implementation.

## Contents

- [Participant control-context assets](participant-control-context-assets.md) —
  immutable instruction, directive, policy, and guidance versions with scoped
  lifecycle, selection, withholding, and separate delivery evidence (ACT-620).
- [`reusable-asset-trust-integrity.md`](reusable-asset-trust-integrity.md) —
  the reusable-asset trust, authenticity, and integrity policy model
  (GOV-913, [ADR-071](../../docs/decisions/adrs/adr-071-reusable-asset-trust-and-integrity-policy.md)).
  Its machine-checkable surface is the published `reusable-asset-trust-policy-v1`
  contract under `contracts/schemas/asset-trust/`.
- [`associated-artifact-manifests.md`](associated-artifact-manifests.md) —
  portable attachment identities and byte-binding conformance
  ([ADR-077](../../docs/decisions/adrs/adr-077-associated-artifact-manifest-boundary.md)).
- [`artifact-requirement-satisfaction.md`](artifact-requirement-satisfaction.md) —
  exact, constrained, and open `Source` artifact demand, backend capability,
  admission, and runtime satisfaction disclosure
  (#920, [ADR-098](../../docs/decisions/adrs/adr-098-portable-artifact-requirement-satisfaction.md)).
