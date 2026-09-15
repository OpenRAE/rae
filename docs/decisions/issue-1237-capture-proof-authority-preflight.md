# Issue 1237 capture admission and evidence-proof authority preflight

Status: non-normative architecture guidance. Owning requirements: EXP-708 and
EXP-715. Supporting trust-and-integrity rationale: GOV-913. GitHub issue #1237
is the delivery contract. Inspected baseline: current worktree.

[ADR-064](adrs/adr-064-experiment-evidence-and-measure-contract-boundary.md),
[ADR-066](adrs/adr-066-observability-evidence-plane-separation.md), and the
#1112 preflight already establish the relevant boundaries. No ADR is needed:
this issue must consolidate existing authority, not introduce a new evidence
architecture or public semantic model.

GOV-913 supplies the trust-and-integrity rationale, but
[ADR-071](adrs/adr-071-reusable-asset-trust-and-integrity-policy.md), its
normative specification, and `reusable-asset-trust-policy-v1` remain the sole
reusable-asset policy authority. A content-backed run-evidence proof is not a
reusable-asset attestation, signature verification, trust decision, or policy
record. Neither the proof nor the output-contract registry may interpret
`mechanism_ref` values or duplicate ADR-071's asset-family policy.

## Decision and boundaries

`raes_contracts.evidence_satisfaction` is the sole authority that turns
admitted capture requirements, records, emitted artifacts, and bounded content
into evidence satisfaction. Promote its private `_ValidatedEvidenceBinding` to
one public immutable proof result (and, if useful, a collection indexed by the
canonical capture-requirement identity). It must be constructed only after the
complete #1112 identity/window/disclosure/source/artifact/checksum/schema/
semantic-validator/field-selector checks have succeeded.

The proof is an opaque, process-local validation result, not a cryptographic
proof or portable contract. It has no public decoder, wire schema, or durable
form; an exact-type check is a programming boundary rather than protection from
malicious code already executing in the validator process. Revalidate content
after every process, persistence, or trust-boundary crossing. Index internal
bindings by `(capture_spec_id, spec_version, requirement_id)` and study proofs
by `(run_id, run_version)`; a bare requirement or run id is safe only after the
owning validator has rejected ambiguity explicitly.

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

Keep that metadata dependency-neutral. `raes_contracts` may own closed
dimension descriptors and contract conversions; SDL/capture semantic
derivation stays in `raes_processor`, and protocol dataclass validation stays
in `raes_backend_protocols`. Do not reverse those imports, place processor
callbacks in the registry, or replace each owner's semantic validators with
unbounded reflection over arbitrary objects.

## Existing owners that must be reused

| Concern | Canonical incumbent and required use |
| --- | --- |
| Intent and plane split | `EvidenceRequirement`, `ExperimentCaptureSpecModel`, `ExperimentCaptureRequirementModel`, `ExperimentTaskModel`, and ADR-064/066. Do not make a backend capability or record reference into authored demand. |
| Offer contract | `ObservationCaptureOfferModel`, `ObservationCaptureOffer`, `ObservationCapabilitiesModel`/`ObservationCapabilities`, `backend_manifest_v2_model()`, and `backend_manifest_from_v2_model()`. Keep Pydantic/dataclass symmetry and the existing offer-coherence validation. |
| Admission | `raes_processor.capture_admission`, `compile_runtime_model()`, `planner.plan()`, trial compiler, admitted-plan digest/sealing, and `realize_admitted_trial_entry()`. One matcher, stable complete diagnostics, no backend-name branches. |
| Output proof | `evidence_satisfaction`, `_evidence_content_validation`, `json_ingress`, `profile_schema_registry`, `uri_safety`, associated-artifact validators and their validation-limit pattern, and `ExperimentRunEvidenceInputs`. Readers remain explicit bounded `BinaryIO`s. |
| Reusable-asset policy | ADR-071, `specs/supply-chain/reusable-asset-trust-integrity.md`, `reusable-asset-trust-policy-v1`, and its existing model/fixture tests. Keep this declarative family policy separate from run-content proof; #1237 may consume incumbent digest/checksum mechanisms but must not become its runtime enforcement layer. |
| Contract publication and packaging | `ContractModel(extra="forbid")`, `schema_bundle()`, `contracts/schemas/`, fixtures, schema publication manifest/entries, `corpus_family_root(SCHEMAS)`, the Hatch corpus force-include in `implementations/python/pyproject.toml`, `test_corpus_packaging.py`, `tools/check_generated_schemas.py`, `tools/check_schema_publication.py`, and ADR-061. Published schema is authoritative; do not hand-edit a generated mirror or resolve it through a checkout-relative path. |
| Errors, persistence, runtime | `Diagnostic`/`DiagnosticModel`, existing `ValueError`/Pydantic parse boundaries, `RuntimeManager.apply()`, `_submitted_plan_diagnostics()`, `_call_backend_apply()`, `ControlPlaneStore`, snapshots, `AuditEvent`, and redacted API errors. Add neither an exception hierarchy nor a proof store/log stream. |
| Requirement workflow | `tools/policy/requirement_order.yaml`, `test_issue_1237_governance.py`, requirement traceability, and the repository policy commands. The changed implementation surfaces belong to the `experiment-evidence` phase and are authorized by EXP-708/EXP-715; GOV-913 does not independently authorize them. Because the branch name has no requirement UID, policy execution must set the owning `RAES_REQUIREMENT_UID` explicitly. |

## Cross-cutting security and whole-repository gates

| Layer | Required behavior |
| --- | --- |
| SDL and configuration ingress | Continue safe YAML limits, closed SDL models, canonical reference resolution, instantiation, and semantic revalidation. Unknown capture requirement/spec ids fail; no string/title/fallback resolution. |
| Manifest and contract shapes | Use the closed Pydantic contract, controlled vocabularies, supported-contract checks, offer coherence, schema parity, fixtures, and publication ledger. A manifest-supported contract id alone is transport compatibility, never proof authority. |
| Planning through realization | All existing pre-effect ingress points—planner, trial compilation, realization, runtime submission, and study/run analysis—must execute invariant-level conformance against the same semantics. Retain digest-bound inputs and reject before backend validation/apply. |
| Artifact/content ingress | Use caller-provided bounded readers, size/checksum verification, bounded JSON/JSONL parsing, offline schema resolution, and the atomic registry. Snapshot/revalidate mutable task, run, spec, record, and mapping inputs before lengthy reader I/O, and bind the proof to those exact stabilized inputs; hashing caller-owned objects only after validation leaves a mutation race. Bound artifact/record counts and aggregate declared bytes as well as each artifact, following `AssociatedArtifactValidationLimits`; a per-artifact cap alone permits unbounded total work. Read each unique artifact once and reuse its validated document for multiple requirement bindings, so shared artifacts and single-pass streams cannot make authority depend on iteration order or cursor state. Never fetch an artifact URI, search a host path, load a validator from data, or parse unbounded bytes. `ExperimentArtifactRefModel.uri` currently guarantees only a non-empty string, so any locator retained for path-qualified proof matching must first pass `uri_safety.validate_safe_absolute_uri`; model admission alone is not that guarantee. |
| Authorization and secret surfaces | No endpoint, role, token, environment variable, or secret-binding shape is needed. Preserve `ControlPlaneSecurityConfig`, role/target checks, request limits, idempotency, and audience separation. Proofs, diagnostics, and manifests contain safe ids/digests/state only; if path-qualified matching requires a locator, retain only an already validated inert credential-free value and keep it out of serialization and representation. Never retain credentials, signed URLs, raw sensitive evidence, environment dumps, or backend representations. |
| OS/process exposure | The registry, matcher, and proof construction are pure and spawn no process. Existing backend producers retain fixed/allowlisted argv, no shell, bounded output/time, and no secrets/raw evidence in argv, stderr, or logs. |
| Error envelopes and observability | Parser boundaries retain Pydantic errors; planner/runtime use deterministic `Diagnostic`s; control-plane responses/audits remain redacted. Do not include payloads, URIs, exception text, tracebacks, or validator internals in error envelopes. In particular, content-validation failures must never reach an HTTP route that renders `detail=str(exc)`; translate them to a stable public diagnostic first if a later API surface is added. |
| Persistence/recovery | Proof authority is recomputable from exact supplied records/readers and belongs only in existing typed run/study validation flows if persistence is necessary. Do not persist a free-standing "validated" flag or rely on snapshot/operation/audit metadata as proof. |
| Installed runtime | Resolve registered schemas only through the packaged contract corpus and deny remote `$ref` retrieval. The installed-wheel smoke must resolve and exercise every evidence-eligible registration without the source checkout present; directory-existence coverage alone is insufficient. |

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
- Do not let an unvalidated artifact URI enter the proof merely because the
  current artifact model accepted a non-empty value; signed query parameters,
  credential userinfo, host paths, and dereferenceable locators are not proof
  identity.
- Do not treat hashing a locator as sanitization. Low-entropy or credential-
  bearing locators remain sensitive and must be rejected before any digest is
  retained, compared, logged, or exposed.
- Do not validate mutable caller-owned carriers and only then compute their
  proof digests; stabilize the full validation cut so concurrent or callback
  mutation cannot bind a proof to content that skipped an earlier invariant.
- Do not key bindings or per-run evidence inputs by a bare id when versioned or
  spec-local identities can coexist, and do not consume the same reader once
  per binding when one artifact may satisfy several requirements.
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
- Do not conflate the content proof with ADR-071 trust-policy compliance,
  authenticity, signature validation, or reusable-asset admission.
- Do not absorb unrelated apparatus/time/cleanup/participant/evaluator
  admissions into capture admission; invoke their existing validators alongside
  it.

## Non-goals

### Authorized delivery-governance extension

The user's subsequent scope expansion adds mixed-requirement workflow governance
under GOV-913. The evidence-plane non-goals below remain unchanged; they do not
prohibit this explicitly authorized tooling work. The reviewed, issue-bound
`docs/governance/requirement-scopes/1237.json` assigns exact delivery files to
EXP-708, EXP-715, GOV-913, SEM-218, or ASR-519. `tools/policy/requirement_scope.py` reuses the existing
status, prerequisite, ownership, and traceability evaluator independently for
every assigned owner. Scope is not a union of partial permissions, an ownership
exception, or a replacement requirement authority.

The canonical `tools/requirement_context.py` resolver is shared by the direct
checker, Make/Nox policy, hooks, and detached canonical CI. Its new
`RAES_REQUIREMENT_BRANCH` input identifies workflow context only: it carries no
credentials, commands, remote URL, or alternative authority location. Exact
canonical manifest selection, strict bounded parsing, explicit primary-UID
agreement, and reject-before-skip behavior are enforced by regression tests.
The issue's Requirements section and the reviewed manifest name the same five
UIDs. Requirement records remain the configured offline source.

The expanded code review identified two concrete repairs: established scopes
must not disappear into legacy fallback, and compute-substrate/conformance
source checks must use the canonical exact-source predicate. Git index/history
inspection preserves established scope authority across deletion and rename.
SEM-218 covers substrate admission, native binding, and reuse; ASR-519 covers
honesty conformance. Selection without an observation demand remains valid and
does not trigger readback. When readback is demanded without an explicit source,
driver-reported metadata cannot substitute for daemon or guest observation.
Conformance rejects a different source even when the former rank called it
stronger. Regression tests cover each ingress and both positive/negative paths.

The implementation retains published support for inert relative artifact paths;
the absolute-URI-only recommendation above is therefore narrowed, not applied
as a compatibility break. Relative locators are checked as URI paths with the
canonical secret-field validator; host paths, file URIs, userinfo, fragments,
and secret queries are rejected before reader I/O or locator hashing. Proofs
retain only the admitted locator's identity digest. Metadata is revalidated into
independent snapshots before I/O, bounded to 1024 items and 256 MiB aggregate
declared bytes (64 MiB per artifact), and each shared artifact/document is read
and validated once per invocation while each requirement's relation checks run.
Installed-wheel coverage resolves and exercises both evidence registrations.

This issue does not add collectors, storage/export services, evidence browsers,
new APIs/auth/config/env surfaces, subprocesses, backend-specific behavior,
new capture-policy syntax, a generic validation framework, a new persistence
repository, or a new exception/logging/workflow hierarchy. It does not change
ADR-064/066 plane ownership, #1112 fail-closed behavior, #1212 demand policy,
or ADR-071 reusable-asset policy. It does not enforce signatures or asset-family
trust requirements, or claim that admission proves execution, scientific
correctness, or semantic truth beyond validated required content.
