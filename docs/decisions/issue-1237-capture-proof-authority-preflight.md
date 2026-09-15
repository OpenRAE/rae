# Issue 1237 capture admission and evidence-proof authority preflight

Status: non-normative architecture guidance. Requirements: EXP-708 and EXP-715;
GitHub issue #1237 is the delivery contract. Inspected baseline: current worktree.

[ADR-064](adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-066](adrs/adr-066-observability-evidence-plane-separation.md), and the
#1112 preflight already establish the relevant boundaries. No ADR is needed:
this issue must consolidate existing authority, not introduce a new evidence
architecture or public semantic model.

## Decision and boundaries

`raes_contracts.evidence_satisfaction` is the sole authority that turns
admitted capture requirements, records, emitted artifacts, and bounded content
into evidence satisfaction. Promote its private `_ValidatedEvidenceBinding` to
one public immutable proof result (and, if useful, a collection indexed by the
canonical capture-requirement identity). It must be constructed only after the
complete #1112 identity/window/disclosure/source/artifact/checksum/schema/
semantic-validator/field-selector checks have succeeded.

Task, run, study, metric, and condition validation may consume this proof
result and perform only their owning relation checks. They must not reconstruct
authority from `satisfies_refs`, artifact ids/URIs/checksums, record refs,
`payload_summary`, result `evidence_refs`, manifest offers, adapter receipts,
or metadata. Those are identity/provenance inputs or structural links, not
proof of emitted content. Keep `validate_experiment_run_structure_against_task`
explicitly structural; the authoritative path remains
`validate_experiment_run_against_task` with content-backed inputs.

The evidence-eligible output-contract registry must be one governed,
local-only registry in `raes_contracts`, replacing the split lookup between
`schema_bundle()` and `_OUTPUT_VALIDATORS`. Each entry atomically supplies:

- the versioned output-contract id and its exact published schema resolver;
- the owning closed semantic validator; and
- the allowed encoded root/media representation where that is presently
  supported.

Registration fails closed: a declared evidence output contract without either
the published schema or semantic validator is invalid at manifest admission and
at emitted-content validation. The registry is an adapter over the existing
schema bundle and contract models, not a second schema publication ledger or a
copy of JSON Schema. `contracts/schema-publication-manifest.json` remains the
only machine-readable publication registry under ADR-061.

Capture dimensions must be defined once as governed dimension metadata used by
the Pydantic offer model, `ObservationCaptureOffer` dataclass conversion,
`CaptureDemand` projection, matcher, and diagnostics. Preserve concrete closed
fields and their current domain-specific rules; do not replace them with an
untyped `dict[str, object]` or generic `constraints` bag. The metadata must
identify the canonical demand and offer projection, comparison semantics
(subset, exact, overlap, or scalar equality), and deterministic diagnostic
code. A new required capture dimension therefore has no valid partial path:
the parity/property suite must cover SDL projection, capture-spec projection,
manifest Pydantic/dataclass round trip, matching, diagnostics, and all ingress
callers before it can be accepted.

## Existing owners that must be reused

| Concern | Canonical incumbent and required use |
| --- | --- |
| Intent and plane split | `EvidenceRequirement`, `ExperimentCaptureSpecModel`, `ExperimentCaptureRequirementModel`, `ExperimentTaskModel`, and ADR-064/066. Do not make a backend capability or record reference into authored demand. |
| Offer contract | `ObservationCaptureOfferModel`, `ObservationCaptureOffer`, `ObservationCapabilitiesModel`/`ObservationCapabilities`, `backend_manifest_v2_model()`, and `backend_manifest_from_v2_model()`. Keep Pydantic/dataclass symmetry and the existing offer-coherence validation. |
| Admission | `raes_processor.capture_admission`, `compile_runtime_model()`, `planner.plan()`, trial compiler, admitted-plan digest/sealing, and `realize_admitted_trial_entry()`. One matcher, stable complete diagnostics, no backend-name branches. |
| Output proof | `evidence_satisfaction`, `_evidence_content_validation`, `json_ingress`, `profile_schema_registry`, `uri_safety`, associated-artifact validators, and `ExperimentRunEvidenceInputs`. Readers remain explicit bounded `BinaryIO`s. |
| Contract publication | `ContractModel(extra="forbid")`, `schema_bundle()`, `contracts/schemas/`, fixtures, schema publication manifest/entries, `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`, and ADR-061. Published schema is authoritative; do not hand-edit a generated mirror. |
| Errors, persistence, runtime | `Diagnostic`/`DiagnosticModel`, existing `ValueError`/Pydantic parse boundaries, `RuntimeManager.apply()`, `_submitted_plan_diagnostics()`, `_call_backend_apply()`, `ControlPlaneStore`, snapshots, `AuditEvent`, and redacted API errors. Add neither an exception hierarchy nor a proof store/log stream. |

## Cross-cutting security and whole-repository gates

| Layer | Required behavior |
| --- | --- |
| SDL and configuration ingress | Continue safe YAML limits, closed SDL models, canonical reference resolution, instantiation, and semantic revalidation. Unknown capture requirement/spec ids fail; no string/title/fallback resolution. |
| Manifest and contract shapes | Use the closed Pydantic contract, controlled vocabularies, supported-contract checks, offer coherence, schema parity, fixtures, and publication ledger. A manifest-supported contract id alone is transport compatibility, never proof authority. |
| Planning through realization | All existing pre-effect ingress points—planner, trial compilation, realization, runtime submission, and study/run analysis—must execute invariant-level conformance against the same semantics. Retain digest-bound inputs and reject before backend validation/apply. |
| Artifact/content ingress | Use caller-provided bounded readers, size/checksum verification, bounded JSON/JSONL parsing, offline schema resolution, and the atomic registry. Never fetch an artifact URI, search a host path, load a validator from data, or parse unbounded bytes. |
| Authorization and secret surfaces | No endpoint, role, token, environment variable, or secret-binding shape is needed. Preserve `ControlPlaneSecurityConfig`, role/target checks, request limits, idempotency, and audience separation. Proofs, diagnostics, and manifests contain safe ids/digests/state only—never credentials, signed URLs, raw sensitive evidence, environment dumps, or backend representations. |
| OS/process exposure | The registry, matcher, and proof construction are pure and spawn no process. Existing backend producers retain fixed/allowlisted argv, no shell, bounded output/time, and no secrets/raw evidence in argv, stderr, or logs. |
| Error envelopes and observability | Parser boundaries retain Pydantic errors; planner/runtime use deterministic `Diagnostic`s; control-plane responses/audits remain redacted. Do not include payloads, URIs, exception text, tracebacks, or validator internals in error envelopes. |
| Persistence/recovery | Proof authority is recomputable from exact supplied records/readers and belongs only in existing typed run/study validation flows if persistence is necessary. Do not persist a free-standing "validated" flag or rely on snapshot/operation/audit metadata as proof. |

## Extensibility seam and conformance requirement

The extension seam is the versioned output-contract registry entry plus the
governed capture-dimension definition. A future capture dimension adds one
definition with its demand/offer accessors, comparison, diagnostic, and
round-trip/property cases; a future output contract adds one schema-backed
semantic-validator entry. Neither change may require a backend-specific
conditional, parallel schema registry, new consumer-specific proof logic, or
an authority-bearing free-form field.

Build a shared invariant-level conformance matrix, not copies of identical
example tests. It must execute the same accepted/rejected vectors at planning,
trial compilation, trial realization, direct runtime submission, and study/run
analysis. Generate dimension-deletion/mismatch vectors so every dimension is
observed in projection, round trip, matcher, and diagnostic output. Include
negative proof vectors where metadata and `satisfies_refs` align but bytes,
digest, schema, semantic validation, selector, source, window, redaction, or
loss conditions fail.

## Gotchas and anti-patterns

- Do not make a proof object a serializable self-attestation, or permit callers
  to instantiate it from references; its constructor/factory must remain behind
  complete validation.
- Do not use `satisfies_refs` to select or satisfy task/metric/condition/study
  evidence. It remains non-authoritative provenance metadata.
- Do not add a compatibility fallback for legacy coarse capability lists,
  booleans, supported contract ids, absent schema entries, absent validators, or
  incomplete capture-dimension projections.
- Do not accidentally create a Cartesian product by matching dimensions across
  distinct offers, nor make first-match/set-order diagnostics authoritative.
- Do not conflate schema validity, semantic validator success, manifest promise,
  record identity, byte integrity, and task/study satisfaction: each is a
  necessary layer, none substitutes for another.
- Do not absorb unrelated apparatus/time/cleanup/participant/evaluator
  admissions into capture admission; invoke their existing validators alongside
  it.

## Non-goals

This issue does not add collectors, storage/export services, evidence browsers,
new APIs/auth/config/env surfaces, subprocesses, backend-specific behavior,
new capture-policy syntax, a generic validation framework, a new persistence
repository, or a new exception/logging/workflow hierarchy. It does not change
ADR-064/066 plane ownership, #1112 fail-closed behavior, #1212 demand policy,
or claim that admission proves execution, scientific correctness, or semantic
truth beyond validated required content.
