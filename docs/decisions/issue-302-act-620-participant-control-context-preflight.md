# Issue 302: Participant control-context assets

Architecture preflight, 2026-10-26. Requirement: ACT-620 (DRAFT).
This note guides the later contract implementation; it defines no published
contract, executable behavior, or implementation sequence.

## Decision and ownership

Publish only the missing participant asset identity/version, applicability,
authority, and lifecycle semantics. Reuse the existing artifact descriptors,
associated-artifact manifests, participant views, crossing decisions, delivery
records, and experiment evidence. No new ADR is needed:
[ADR-077](adrs/adr-077-associated-artifact-manifest-boundary.md) owns associated
bytes, [ADR-083](adrs/adr-083-participant-tool-decision-surface-and-exposure-semantics.md)
owns exposure strata,
[ADR-095](adrs/adr-095-participant-decision-epoch-state-cut-and-delivery-semantics.md)
owns exact state cuts and delivery, and
[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md)
owns control mechanisms. Issue #299 owns SDL references to these assets.

A directive, instruction, or policy **content asset** guides a participant.
Its kind does not make it an executable exposure/IFC policy, an action contract,
an API-409 controller authorization, or an API-424 mechanism/provider binding.
In particular, `ControlArtifactReferenceModel(kind="policy")` and
`ParticipantControlSelectionModel` belong to mechanism orchestration; their
names do not make them the ACT-620 asset model. Content may be adversarial or
contradictory without granting authority. Preserve ordinary action admission
and selected final-sink enforcement after the content is delivered.

## Asset and historical boundaries

- Give the reusable asset a stable logical identity and an immutable version.
  Keep contract schema version, asset version, manifest id/version, manifest-local
  `artifact_id`, set digest, content checksum, policy revision, and delivery
  occurrence distinct. A manifest entry alone has neither asset version nor
  lifecycle; attaching an artifact does not select or deliver it.
- Reuse `ExperimentArtifactRefModel` and `ExperimentChecksumModel` for content
  descriptors and byte integrity. Add only the asset-specific semantics around
  those shapes. A URI is an inert locator, never authority or byte evidence.
  A content checksum binds exact bytes; a descriptor digest, if needed, uses
  `canonical_contract_digest()` with an explicitly defined projection. Neither
  digest proves authenticity, permission, or participant understanding.
  Verify the same immutable bytes that will be used, not a second read from a
  mutable locator or decoded/reformatted text substituted for the raw bytes.
- Define kind, origin/provenance, participant/role applicability, and the
  separately required authority to publish/change, select/replace/withdraw,
  and disclose. Resolve roles to canonical participant identities at the
  applicable run/episode and cut; role membership, caller principal, SDL
  controller, participant implementation, and deployment tenant are different
  concepts. Self-declared authority refs are claims until checked against
  trusted context. Applicability is not disclosure permission.
  Multiple assets must not acquire implicit precedence from kind names,
  manifest iteration order, or last-write-wins selection.
- A revision creates a new immutable version; changing bytes under the same
  identity/version is a conflict. Replacement and withdrawal have an explicit
  authority, reason, effective cut/order domain, and retained predecessor link.
  They change future eligibility/selection without rewriting past facts.
  Resolve exact versions: no implicit `latest`, version fallback, mutable URI
  substitution, or inference from version-string ordering. Reject unknown,
  ambiguous, stale, conflicting, and unauthorized bindings.
- Asset lifecycle, per-participant selection, and per-audience withholding are
  independent. Withholding from one participant does not withdraw the reusable
  asset or alter another participant's selection. Withdrawal does not erase
  delivered knowledge, invalidate a formerly valid historical record, or prove
  participant memory reset. Retain historical version descriptors and evidence;
  authorized byte retention/deletion remains the consumer's policy. If bytes
  are unavailable, disclose that limit instead of claiming verified replay.
- Preserve selected version and actual delivery as separate evidence. Join
  asset identity/version/checksum, selection authority and cut to the exact
  participant, run, episode/generation, audience, and exposure policy. Delivery
  additionally joins the authorized result identity/digest, delivery cut/basis,
  occurrence, and observation/evidence refs. A selected or disclosed asset can
  remain undelivered. A transformed/redacted result keeps its own identity and
  source relation; it must not masquerade as the original version's bytes.

Reuse ADR-095 v2 coordinates for actionable surfaces. Decision epoch, behavior
history index, policy-effective order, wall time, and delivery order are not
interchangeable. A mid-episode revision takes effect at a trusted comparable
cut; delivery rechecks current authority and withdrawal, even if derivation
preceded the change. Historical v1 records keep their historical meaning.

## Cross-cutting layers and required reuse

Package paths below are relative to `implementations/python/packages/`.
These are gates on the intended design, not a request to build each subsystem.

| Layer and canonical incumbent | Required boundary |
| --- | --- |
| Portable shape and ingress: `raes_contracts/contracts/experiment_artifacts.py`, `associated_artifacts.py`, `base.py`; `raes_contracts/json_ingress.py` | Use closed `ContractModel` shapes, existing digest/date/reference primitives, explicit count/string/byte/depth bounds, duplicate-member and non-finite-number rejection before model construction. Share structural rules with published JSON Schema; cross-artifact identity, authority, lifecycle and byte checks remain contextual validation with declared `x-raes-invariants`. No parallel parser, DTO family, checksum code, or exception hierarchy. |
| Content integrity/acquisition: `raes_contracts/associated_artifacts.py`, `uri_safety.py`; ADR-071 reusable-asset trust policy | Use `validate_associated_artifact_manifest()` for a concrete supported parent and the existing bounded byte-reader/limits path for payloads. `validate_associated_artifact_payloads()` alone does not authorize or join the parent. The manifest scope is scenario/experiment, not participant; do not invent participant parents. Acquisition and immutable staging belong to the consumer. Validate safe absolute URIs explicitly: the bare artifact descriptor does not apply the manifest's URI validator. URI validation does not authorize fetching or prevent SSRF/path traversal by itself. No automatic network/file resolution, symlink following, archive extraction, or ambient credentials in contract validation. |
| SDL/reference seam: `raes/parser.py`, `_source_validation.py`, `_base.py`, `validator/`; `participant_behavior/_view_boundaries.py` | #299 consumes the asset identity/version contract through the existing safe-YAML, normalized-key, closed-model, variable/reference, semantic and post-instantiation gates. Reuse `ParticipantViewRule`, `ParticipantObservationBoundary`, and the existing instruction/scaffold boundary classes. Asset kind is not a replacement visibility taxonomy. Do not add embedded executable text, another SDL asset registry, or a second reference validator here. |
| Applicability and exposure: `raes_contracts/contracts/participant_context.py`, `participant_decision_surface_exposure_v2.py`, `participant_decision_surface_v2_validation.py`; `raes_processor/models/participant_exposure_authority_v2.py` | Reuse source/transformation, marking inheritance, SEM-216 archival mediation, exact-cut exposure authorization and v2 participant-view/assurance separation. Context `source_layer`, artifact `role`, reference kinds and exposure-policy kinds are closed vocabularies; they are not interchangeable. Any necessary addition belongs to its owning governed contract/catalog. Do not disguise authored context as an observation, evidence record, or snapshot merely to fit an enum. Assurance refs and withheld asset existence/metadata are independently governed disclosures. |
| Host and transport authorization: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `participant_retrieval.py`, `control_plane_api_participant_retrieval.py`; [participant-access decision](issue-1356-control-plane-participant-access-preflight.md) | The trusted host binds its caller/session to target/run, participant, exact episode, audience and operation for every release, including retry/cache/export. P2 identities are target-bound administrative identities, not participant credentials; P0/P1 object access is privileged. `audience_scope`, a role, a ref, and a valid schema are insufficient entitlement. Require configured governed retrieval and trusted audience/evidence resolution for participant release; the legacy no-resolver path is not a safe fallback. No new HTTP route, role, token or IAM model is required by this issue. |
| Runtime crossing and delivery: `raes_contracts/contracts/participant_crossing_validation.py`, `raes_contracts/participant_decision_surface_delivery.py`; `raes_runtime/participant_crossing_mediation.py`, `participant_crossing_commit.py`, `participant_flow_sink.py`, `participant_control_orchestration.py` | Reuse API-423/RUN-319 independent gates and committed crossing evidence, ADR-095 delivery re-resolution, and selected SEM-233/RUN-320 enforcement. Deny unresolved or mismatched participant, audience, policy, cut, version and digest before release. Reuse actor-scoped idempotency, history-head checks and atomic commit; do not add an asset-specific dispatch/update workflow or claim exactly-once external delivery from a local commit. |
| Secret/config/environment: `raes_contracts/secret_references.py`, `contracts/experiment_bindings.py`; `raes/runtime_environment.py`, `runtime_configuration.py`, `runtime_generated_value.py`, `runtime_values.py` | Portable provenance carries safe refs/digests and authorized lifecycle/selection evidence, never private content or resolved secrets. Descriptions, source strings, URI fields and evidence refs can also leak. Keep secret configuration as `SecretReferenceBindingValueModel` with `SecretReferenceId`, declared target/type/sensitivity and no secret defaults. No env binding is needed; a later adapter must preserve unique names, literal/`value_from` exclusion, explicit sensitivity/provenance, redaction and generated-output checks. A private instruction is not an `operator_secret` binding. |
| Persistence/evidence: `raes_contracts/contracts/experiment_run.py`, `experiment_evidence.py`, `participant_manifests.py`; `raes_runtime/control_plane_store.py`, `control_plane_store_local_codec.py`, `control_plane_store_records.py` | Carry exact selections and linked delivery/withholding evidence through existing run/evidence and participant-history carriers; manifest/config provenance alone does not record delivery. Reuse `RuntimeSnapshot`, `ControlPlaneStore`, durable codec/integrity, target/run isolation, owner lease, snapshot revision/CAS and append-only histories. Keep private bytes in consumer-controlled storage and portable records reference-only. Preserve joins through serialization/recovery; never reconstruct historical selection from current state. No asset store, sidecar journal or audit-based delivery substitute. |
| Errors and observability: `raes_contracts/diagnostics.py`; `raes_runtime/control_plane_api/_responses.py`, API exception handlers, `control_plane_audit.py` | Reuse `Diagnostic`/`Severity`, `portable_diagnostic_payload`, operation receipts/status and stable coarse HTTP 4xx/422/500 envelopes. Expected refusal is distinct from resolver/infrastructure failure. Never echo Pydantic input/errors, resolver exception chains, private text, full rejected objects, credential-bearing locators or environment data. Audit permitted identifiers/codes through existing events; neither audit retention nor a log message proves participant delivery. Secondary audit failure must not replace the chosen safe error response. |
| Host/OS boundary | This contract needs no subprocess, listener, shell, filesystem materializer or secret resolver. Consumers must use approved acquisition/storage, immutable bounded inputs and authorized sinks. Do not place private instructions or credentials in argv, shell interpolation/tracing, environment dumps, stdout/stderr, temporary public files, crash reports or exported config. Retained store copies/backups remain privileged; redacted diagnostics do not sanitize them. |

Schema-shaped metadata is not an escape hatch. In particular,
`ParticipantExposurePolicyModel.constraints`, participant provenance `metadata`,
and free-form evidence descriptions cannot become an unvalidated asset
catalog, authority policy, lifecycle history, or delivery ledger. Existing
models solve carrier concerns; the missing semantic joins still need explicit
validation. Do not copy their validators into a new feature-local stack.
Checksums and identifiers for private assets are also disclosure-sensitive;
low-entropy content can be guessed from a public digest. Retention for an
authorized verifier does not make that digest safe for participant release.

## Extensibility and governance

The seam is a versioned asset descriptor plus an exact reference, resolved
against explicitly supplied trusted version/lifecycle/authority context and
bounded content readers. Applicability and selection are separate from the
reusable descriptor, so two participants can select one immutable version
without duplicating content or changing its identity. Effective-cut and
audience parameters permit later role changes, revision, withholding and
alternative approved transports without backend-name branches, an implicit
global current version, or an asset-kind-specific runtime workflow.
Unknown kinds fail closed; extensions use the owning governed vocabulary and
contract revision, not arbitrary strings or a universal plugin registry.

Normative semantics belong in `specs/`, portable schemas/fixtures in
`contracts/`, neutral models/validators in `raes_contracts`, projection in
`raes_processor`, and live mediation in `raes_runtime`. Backend protocols and
conformance retain their existing packages. This guidance note is not normative
authority. Reuse ADR-009/019 and `specs/authority/authority-boundary.yaml`.

Published schemas are hand-governed authority. Use the existing
`schema_bundle()`, schema publication index and per-contract entries under
`contracts/schema-publication/`, `last_change` hashes, fixtures, and
`tools/check_generated_schemas.py`, `check_schema_publication.py`,
`check_json_artifacts.py`, and `check_contract_requirement_tracing.py`.
Closed enum changes and additions to existing carriers require compatibility
review; preserve historical contracts. ADR-071's trust policy requires exactly
one entry for every canonical family: do not casually add a control-context
family and invalidate existing policies. Existing associated-set/checksum
mechanisms cover attached bytes; any genuinely new family requires explicit
policy compatibility treatment. Capability allowlists in `manifest_authority.py`
and controlled concept bindings must reflect actual consumption/support.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/check_repo_policy.py` and file-targeted `.pre-commit-config.yaml` hygiene
and secret checks. Set `RAES_REQUIREMENT_UID=ACT-620` when needed. Keep design
evidence distinct from IMPLEMENTS/TESTS fulfillment; this preflight does not
activate the DRAFT requirement. Do not edit release-managed versions/changelog
or accepted ADR bodies to bypass their governance.

## Evidence expectations and non-goals

Use the existing contract fixture loader and conformance runner. Relevant
regression homes in `implementations/python/tests/` include
`test_associated_artifact_manifests.py`, `test_sem_226_participant_exposure.py`,
`test_sem_216_boundary_semantics.py`,
`test_sem_220_participant_decision_surface_v2.py`,
`test_run_319_participant_flow_policy.py`, `test_experiment_bindings.py`, and
`test_runtime_control_plane_api.py`. Run only relevant modules/cases locally;
full test, integration, fuzz, policy and completion suites remain CI work.

Contract evidence must show one instruction version selected independently for
two participants, a new version selected at a later cut within an episode,
and intentional withholding without a fabricated delivery. Negative evidence
must distinguish structural validity from trusted resolution: unknown version,
same-version changed bytes, stale checksum, unauthorized replacement/withdrawal,
wrong participant/role/audience/run/episode, delivery after withdrawal, stale-cut
replay, unsupported source kind, and private content in provenance/errors.
Retain the old selection and actual delivery after revision/withdrawal, and
show that transformed content uses a distinct result digest. Persisted evidence
claims require round-trip/recovery coverage at the existing carrier boundary.
These are acceptance guardrails, not an implementation plan or proof of universal
noninterference, participant compliance, or knowledge erasure.

Non-goals: implementing #299's SDL references; installing, interpreting or
executing instructions; prompt precedence/composition or template execution;
mechanism orchestration under ADR-108/#1069; a generic policy language,
controller/IAM redesign, registry, acquisition service, storage service,
transport, logger, exception hierarchy, or parallel workflow. Publish the
missing contract surface and its agreement checks, not an asset-management
platform or an alternative participant context/delivery envelope.
