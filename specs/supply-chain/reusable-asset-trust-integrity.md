# Reusable asset trust, authenticity, and integrity

Status: normative
Requirement: GOV-913 (Trust And Integrity Of Reusable Assets)
Decision: [ADR-071](../../docs/decisions/adrs/adr-071-reusable-asset-trust-and-integrity-policy.md)

This specification is the normative authority for GOV-913: *"The ecosystem shall
support trust, authenticity, and integrity policies for reusable scenarios,
modules, tasks, studies, behavior vocabularies, and comparable reusable
assets."* It defines the **policy model** the ecosystem uses to express those
expectations. It is deliberately contract-first: the machine-checkable surface is
the published `reusable-asset-trust-policy-v1` contract
(`contracts/schemas/asset-trust/`), and runtime enforcement conforms to this
policy under separate implementation work.

## 1. Model

"Reusable asset" is a **role played by existing asset families**, not a new
universal object. The ecosystem does not introduce a `TrustedAsset` abstraction,
a second registry, or per-reference digest fields. Trust, authenticity, and
integrity are expressed as a **declarative policy** that, per asset family,
requires specific **evidence classes**, each satisfied by an *existing* RAES
mechanism.

Trust rests on three orthogonal axes; a policy MUST keep them distinct:

- **Identity** — a name, id, or reference that names the asset. Identity is
  never, by itself, proof of authenticity or integrity.
- **Integrity** — a cryptographic digest bound to the asset's concrete payload
  bytes.
- **Authenticity** — a signature by a trusted signer set, verified against a
  declared threshold.

## 2. Evidence classes

| Evidence class | Meaning | Existing RAES mechanism |
|---|---|---|
| `integrity_digest` | Digest bound to canonical payload bytes | module `raes.lock.json` digest pins; scenario-snapshot binding; associated-artifact set digest; study-definition digest; controlled-vocabulary `source_digest`; manifest/config digests |
| `authenticity_signature` | Signature by a trusted signer set | `RegistryTrustPolicy` signature verification (`_verify_signatures`) |
| `provenance_lock_record` | Pinned inputs / derivation record | `LockRecord` / `resolve_lock_records`; experiment references pinned by digest; participant provenance |
| `governance_source` | Authoritative origin for governed terms | `controlled-vocabularies-v1` `source` (authority + version + extension policy) |
| `artifact_checksum` | Hard checksum over content-artifact bytes | `ExperimentChecksumModel` (associated payloads, evidence records, task/study artifacts) |

Each requirement declares an `enforcement` level: `required`, `recommended`, or
`optional`.

## 3. Policy invariants (normative)

A conforming reusable-asset trust policy MUST satisfy every invariant below.
Each is enforced in three places — the `reusable-asset-trust-policy-v1` contract
model (reference implementation), the published JSON Schema (the portable
surface external consumers validate against), and a negative conformance fixture
that pins the rejection:

1. **Complete family coverage.** The policy MUST declare exactly one entry for
   every canonical reusable asset family: `reusable_scenario`,
   `associated_artifact_set`, `sdl_module`,
   `experiment_task`, `experiment_study`, `behavior_vocabulary`,
   `participant_manifest`, `evidence_artifact`.
2. **Integrity baseline.** Every family MUST declare at least one integrity
   evidence class (`integrity_digest` or `artifact_checksum`) at `required`
   enforcement. Integrity is the GOV-913 floor for every reusable asset.
3. **Unique evidence classes.** A family MUST NOT declare the same evidence
   class more than once.
4. **Threshold-backed authenticity.** A family that requires or recommends
   `authenticity_signature` MUST declare an `authenticity_policy` naming a
   trusted-signer set and an M-of-N `threshold` (≥ 1). No single-key trust; an
   id is not authenticity.
5. **Governed vocabulary source.** `behavior_vocabulary` MUST declare a
   `governance_source` requirement at `required` enforcement — authoritative
   origin is a first-class evidence class for reusable semantics.
6. **No secret-bearing policy.** The policy is a closed contract: it carries
   references, digests-by-mechanism, enforcement levels, and thresholds only. It
   MUST NOT carry key material, credentials, or raw payloads (portable artifacts
   carry public verification material only).

## 4. Per-family policy (reference)

The ecosystem reference policy is published as the valid conformance fixture
`contracts/fixtures/asset-trust/reusable-asset-trust-policy-v1/valid/reference.json`.
Its shape per family:

- **reusable_scenario** — integrity via scenario-snapshot binding (required),
  provenance via composed-module lock records (required), authenticity via
  source-module signatures (recommended). Scenario *identity* stays distinct
  from scenario-snapshot *integrity*.
- **associated_artifact_set** — integrity via the derived
  `associated-artifact-set/v1` parent-plus-reference-set digest (required) and
  concrete payload checksums (required); an optional downstream signature over
  the derived set digest is independent authenticity evidence. Associated
  payloads do not change parent integrity.
- **sdl_module** — integrity via lockfile digest pin (required), provenance via
  lock record with drift checks (required), authenticity via
  `RegistryTrustPolicy` signatures (required).
- **experiment_task** — integrity via artifact checksum (required), provenance
  via pinned parent scenario/module (recommended).
- **experiment_study** — integrity via study-definition digest (required),
  provenance via pinned aggregated scenarios/results (required).
- **behavior_vocabulary** — integrity via `source_digest` (required),
  governance via controlled-vocabulary source (required).
- **participant_manifest** — integrity via manifest/configuration digests
  (required), provenance via participant provenance (recommended); no secrets or
  private configuration in the portable artifact.
- **evidence_artifact** — integrity via raw-content checksum (required),
  authenticity via signed claim over the checksum (recommended).

## 5. Non-goals

This specification does not define new cryptography, a hosted asset registry, a
certificate authority, a transparency log, key rotation, signer distribution, or
runtime verification/enforcement. Those are separate concerns; runtime
enforcement, when built, consumes and conforms to this policy.

## 6. Standards basis

ADR-071 records the supply-chain frameworks behind this policy model:

- SLSA: declarative expectation comparison and resolved-dependency provenance.
- in-toto: digest-bound subjects and authenticity separate from integrity.
- TUF: M-of-N thresholds, offline trust roots, and delegation.
- Sigstore: identity-bound signing and transparency.
- OCI image specification: content-addressable descriptors and out-of-band evidence.
- NIST SP 800-218 SSDF: PS.2 integrity verification and PS.3 provenance.
- C2PA: hard-binding hashes and signed claims for content assets.
