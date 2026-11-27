# Issue #972 — Shared-runtime crossing mapping preflight

Date: 2026-10-27. Inspected revision:
`9b387e67d40a07d3e594323cdbb86694c44d8ab9`.
Requirements: SEM-232 (runtime mapping) and API-404 (operating-profile safety).
Implementation boundary: supplied GitHub issue #972.
This note constrains the mapping boundary, without implementing it or prescribing
an implementation sequence. The companion [mapping design](../../specs/formal/participant-semantics/participant-crossing-runtime-mapping.md)
records the data flow and evidence boundary; neither document establishes a result.

## Decision and scope

Retain [ADR-100](adrs/adr-100-participant-crossing-bisimulation.md) and the
[executable #971 authority](../../specs/formal/participant-semantics/participant-crossing-models.md).
The target is exactly `participant-crossing-dpbb-finite-v1@rev2`, concrete model
`api-423-run-319-crossing-kernel@rev2`, projection
`participant-crossing-projection@rev1`, taxonomy `raes-behavioral-relations@rev8`.
Use the existing revision-aware profile/catalog loaders. The separately governed
#1395 multi-operation profile is not a substitute. No new ADR is needed.

Mapping is a third, offline evidence artifact alongside the independent models.
It must describe a selected, admitted runtime configuration and actual public
execution, with explicit incompatible and unexercised cases. A matching synthetic
record, source digest, final snapshot or visible trace alone establishes no
execution correspondence. Keep #971's transition authorities independent: the
runtime must not import a model oracle, and the mapping must not generate runtime
observations from expected model successors.

The carrier admits one fresh logical operation and its retries, fixed
participant/audience/controller/episode, two policy cuts, sequential total order,
and one logical result batch (`h0 -> h1`; `h2/h3` unreachable). Time, probability,
concurrency, handoff and identity recycling are excluded. Additional effects,
decisions or failure outcomes require a demonstrated mapping under these
assumptions or an incompatibility report. Silently disabling a gate, collapsing
identities, extending a domain or hiding an extra transition cannot make a case
compatible. Changing the profile requires a separate governed decision.

## API-404 operating-profile boundary

[API-404's clause matrix](../requirements/API-404/requirement.md#profile-to-clause-matrix)
and [ADR-104](adrs/adr-104-runtime-control-plane-architecture.md) govern the
runtime composition. The finite behavioral profile governs the mapping carrier;
it selects no operating profile and grants no authentication or durability.
Reuse the existing [clause-to-profile evidence map](../research/runtime-control-plane/conformance.md#api-404-clause-verification)
instead of creating another conformance matrix or workflow.

| Boundary | Required evidence and canonical owner |
| --- | --- |
| Explicit selection | `control_plane.py::_prepare_control_plane_store()`, `select_profile()`, `store_capabilities()` and `require_profile_capabilities()` admit the core. Record its actual `profile_declaration`, target/run and store capabilities. `profile=None` is a legacy composition with no profile claim; neither the store class nor the supplied identity implies P0/P1/P2. The current `participant_crossing_fixtures.py::action_plane()` does not select a profile. Reusing it requires an explicit fixture composition parameter before claiming selected-profile evidence. P3 remains unavailable. |
| C1: P0, P1, P2 | Preserve original actor/authorization scope, request commitment, immutable receipt/status context, target/run and history/revision bindings through admission, dispatch and readback. Use `operation_admission_context()`, store replay validators, `RuntimeMutationAuthority` and the existing crossing commit. Observe authoritative before/after revisions, snapshots, records and audit, alongside independently counted owner/backend calls. Raw store reads are privileged test observations, never evidence that a participant could perform an authorized read. |
| C2: P1, P2 | Local evidence uses the admitted `LocalControlPlaneStore`, ownership lease, WAL/path checks, strict codecs, startup reconciliation and `RuntimeDurabilityMixin` readback. A successful local transaction or orderly close/reopen does not establish process-loss conformance. Reuse `control_plane_conformance_fixtures.py`, `control_plane_crash_fixtures.py` and the #1187 fault boundaries for any such evidence, within the existing CI lanes. Interrupted/unknown work retains its exclusion and one-use invocation facts; a retained key never grants a second dispatch or a renewed execution budget. No remote service is needed for #972. |
| C3: P2 only | `create_control_plane_app(..., profile=ControlPlaneProfile.P2)` requires an explicitly selected P1 core. If exercised, use the original sealed app, configured `ControlPlaneSecurityConfig`, method-bound route authority, bounded offload/body admission, authenticated readback, revision-bearing reads and `no-store` errors/results. Do not override dependencies, exception handlers or middleware to insert observers: the composition seal rejects those changes. Embedded public Python calls leave transport authentication unexercised. P2 administrative read authority includes raw operational views; participant/audience binding does not narrow it. The host still owns participant authentication and release. |
| C4: all evidence | Preserve profile nonclaims: no P3, high availability, multitenancy, concurrent owners, exactly-once external effects, TLS/proxy correctness or universal recovery proof. A finite mapping match adds none of these guarantees. Local stub execution establishes no concrete backend conformance. |

Keep runtime contract checks independent of model compatibility. A legitimate
additional owner operation can be incompatible with rev2 while satisfying
API-404. Unauthorized execution/disclosure, rewritten history, broken replay
ownership or partial terminal publication is a failed runtime obligation, even
if that path is also unmappable. Malformed or insufficient observations are an
evidence failure/gap. Neither category may become an acceptable incompatibility
or disappear into aggregate counts; affected checks must fail and retain a
safe reason. A refused invalid identity is expected negative evidence, while
accepting that identity is a defect. This distinction needs no new runtime
exception, state, DTO or public assurance claim.

Refusal comparisons must validate exact append-only prefixes and permit only
the specific new refusal/evaluation/audit facts owned by that call. Dropping
the entire crossing or control-evaluation history from comparison can hide
tampering with old rows, another participant or an unrelated evaluation.
Independent consequences after parent denial need their own allowed state
changes and witnessed dispatch; they are not blanket refusal exemptions.
For each committed cut, join the exact snapshot revision/history heads,
operation receipt/status and expected audit event. Reuse the relevant store
transition, audit-binding and strict record validators. Mere presence of an
audit with the same actor/operation does not establish its disposition,
contents or atomicity. A lost acknowledgement can leave a valid committed
result; authoritative readback, cache reconciliation and poison/readiness
rules decide the outcome, not the raised exception alone.

## Correspondence boundaries

Python module paths below are relative to `implementations/python/packages/`;
unqualified modules belong to `raes_runtime`.

| Subject | Existing owner and mapping obligation |
| --- | --- |
| Intent and identity | `participant_crossing_intents.py`, `ParticipantCrossingIntent`, `ParticipantCrossingEvidence`, `ControlPlaneIdentity` and `operation_admission_context()` derive the protected operation and caller context. Bind model singletons to exact runtime coordinates before projection. Principal, participant, controller, target/run, episode and audience are distinct identities. Logical retry identity must join operation id, key, semantic commitment and API-423 request/predecessor identities; generated occurrence UUIDs alone do not identify one logical operation. Detect mismatches before normalization. |
| Occurrences and state | `ParticipantCrossingOccurrenceModel`, `validate_participant_crossing_occurrence_context()` and `participant_crossing_history.py` own closed shapes, typed subjects, resolvable policy/evidence/authority, predecessor ordering and exact append-only prefixes. Use their validated facts as evidence. Do not create another occurrence schema, payload carrier, history validator or authority resolver. Model phases need evidence of their owning boundary; absent intermediate evidence is a gap, not a stage inferred from the expected path. |
| Cuts and order | `participant_crossing_state_cut.py::expected_participant_history_heads()` binds episode, behavior, control, crossing and control-evaluation heads. `RuntimeSnapshot`, snapshot revision/CAS and mixed-composition heads add their own constraints where selected. Map `p0/p1` to explicit policy cuts and declare the permitted history vectors. Policy revision, history head, snapshot revision, decision epoch, effective order, time and execution generation are not interchangeable. History advance without policy advance is not `policy.cut.advance`. |
| Gates and support | `participant_crossing_policy.py` owns independent gates, required `not-applicable -> unknown` handling and deny-before-unsupported composition. API-407 `resolve_participant_feature_support()` and installed control/provider support own effective strength, admitted downgrades and evidence. A manifest declaration, provider method or matching feature name is insufficient. Unresolved required support must prevent execution/release. Preserve each gate's reason and effective support before projecting to the model's gate/capability coordinates; an unresolved policy with no API-423 decision is not automatically a modeled unsupported decision. |
| Transformations | `participant_crossing_records.py`, `participant_crossing_transform.py`, ordinary action/control binding and `_governed_egress_view()` own source/result identity, lineage, actual transformed carrier and fresh admission. API-423's `transform` disposition also carries declassification through `required_operation`; it is not the model's plain permit. Map permit/change order explicitly. Transformed ingress creates fresh requested/decided occurrences and can be denied on revalidation. Those extra choices cannot be silently erased into `internal.prepare-record`. Reuse `stable_projection_subject()` only for its declared runtime-owned revision paths; caller-controlled fields remain identity-bearing. |
| Atomic outcomes and history | `commit_prepared_crossing()`, `RuntimeDurabilityMixin`, `ControlPlaneStore.commit_participant_transition()`, strict record codecs and snapshot/history transition validators own claims, revisions, snapshot/record/audit publication and readback. The model head counts one logical result batch, not API-423 rows or SQL transactions. Action authorization commits before external execution and terminalization commits afterward. Their intermediate `RUNNING`, stale-result, interrupted and indeterminate states must be accounted for; atomic individual commits do not establish an atomic world effect. Detect partial publication across snapshot, status, history, evaluation receipt and audit. A commit exception or timeout does not establish rollback; retain authoritative readback and poisoned-readiness behavior. |
| Refusal | Refusal preserves protected backend/application state and prevents unauthorized release; it can append the incumbent safe refusal history, failed status, evaluation and denial audit. Declare those permitted deltas precisely and compare all other relevant state/effect counters. Under #1369 an independently authorized consequence can run after a complete parent denial. It is a separate owner operation, not a refusal side effect that may be ignored; a handoff or second fresh operation exceeds this carrier. Never weaken legitimate effect semantics to satisfy the finite fixture. |
| Idempotency and replay | `control_plane_store.py::require_idempotency_key()` / `_require_same_idempotency_replay()`, `control_plane_operation_context.py` and actor/scope-authorized readback own replay. Current replay accepts the original decision or result head vector with matching immutable context and fingerprint. Keep durable value-free commitments separate from ephemeral exact sensitive retry proofs. Same-cut replay returns an incumbent result without another logical commit/effect; preparation callbacks may still run. Explain how the model's repeated outcome observations correspond to that readback without inventing new delivery/observation events. Later-cut refusal preserves the incumbent; changed-input identity reuse is an invalid-environment negative case, not another admitted input class. |
| Delivery and observation | `participant_retrieval.py`, `ParticipantViewSerialization`, final SEM-233 sink resolution and API-424 orchestration own actual release. An API-423 permit or accepted receipt does not establish final success. #1358 retains earlier permit facts but commits `FAILED`, no releasable payload and a denied audit on final-sink refusal, including replay and a racing incumbent claim. A permit-then-final-refusal path must be mapped honestly or reported incompatible with the model's permit/delivery protocol. Existing history permits `delivery-attempted/withheld` only after API-423 deny; do not fabricate it after permit. Ordinary retrieval does not always append delivery/observation facts, and directed delivery does not establish observation. Prove the selected observable boundary; never infer participant consumption from serialization, an owner success boolean or a convenient stage name. |

Only the five profile-declared hidden classes may become `internal`. UUIDs,
timestamps, error details, host paths, audit facts and bookkeeping may be omitted
only with a reason they cannot change an enabled visible choice, refusal or
completion for the selected projection. Redacted occurrence existence is still
visible. Preserve semantic hidden classes in review data and check finite
progress; matching a completed trace cannot rule out a hidden loop or lost
branch. Unknown labels and unmappable transitions fail compatibility admission.

## Public execution and extension seam

Evidence must drive `RuntimeControlPlane.admit_participant_action()`,
`record_participant_control()`, public participant retrieval and
`dispatch_participant_control_effects()` as applicable. Include
`admit_participant_decision_surface_selection_v2()` through its actual delivered
surface, anchor/delivery validation and ordinary admission. Reuse
`ParticipantSubmissionOptions`; preserve its forwarded original identity,
crossing evidence and retry context. Surface derivation/delivery cuts do not
replace fresh ingress authority. This Python method has no existing v2 HTTP
admission route; no route is required for correspondence.

The repaired provider path must run installed API-424 providers through the
existing dependency evaluation, composition, committed evaluation, effect claim,
owner dispatch and evidenced outcome/continuation machinery. Reuse
`participant_control_evaluation_v2.py`, `participant_control_effects.py`,
`participant_control_effect_owners.py`, `participant_control_effect_evidence.py`,
`participant_control_effect_continuations.py` and `participant_control_receipts.py`.
Parent permission, required predecessor, success-dependent consequence and
independent consequence remain distinct. Accepted owner work is not necessarily
applied work. Handoff, additional world injects, cancellation/recovery or other
extra behavior must remain explicit incompatible cases where rev2 cannot map it.
Exercising such a case is evidence about the repaired path, not a positive
single-operation realization result.

Where a selected effect uses the backend operation provider, retain
`operation_provider_execution.py`, registry/provider shape admission, backend
request/policy/response validators, one-use invocation consumption and
`OperationEvidenceResolver`. A provider's outcome must bind the exact request,
sequence and execution generation; the control-provider protocol and backend
operation-provider protocol are separate contracts.

Reuse `participant_crossing_fixtures.py`, v2 surface/runtime fixtures,
`governed_effect_runtime_fixtures.py`, API-424 v2 fixtures and final-sink fixtures.
Deterministic providers/resolvers and a local backend double may supply bounded
inputs around unmodified production orchestration. Hand-built evaluation or
occurrence data alone, direct calls to preparation helpers, patched admission
decisions, or a fake atomic commit cannot satisfy execution correspondence.
Read-only observation at existing owner seams may explain transitions; it must
not supply authority or change control flow. Existing fixtures that select
`enforce_final_sink_flow_control=False` establish only that legacy configuration,
not default final-sink enforcement.

Behavioral anchors already exist in `test_run_319_participant_flow_policy.py`,
`test_sem_220_participant_decision_surface_v2_runtime.py`, the
`test_issue_1369_*` effect/continuation/recovery cases and
`test_issue_1003_final_sink_flow_enforcement.py`. Extend their boundary patterns,
not a parallel runtime simulator. Preserve authoritative state through a retry
sequence; rebuilding a fresh fixture between its calls would hide drift.

The extension seam belongs in the offline case-to-model mapping: explicit
profile/model/projection pins, input class, public entry/sink, runtime bindings,
explicit operating profile (or legacy no-claim composition), store capabilities,
final-sink configuration, installed support, observed state
coordinates and exclusions. Parameterize existing
fixtures by those admitted choices rather than backend names or view-model
branches. Keep one closed mapping-evidence checker; do not introduce a second
runtime policy engine, generic event bus, plugin registry or public proof DTO.
A future governed profile can supply its own adapter and evidence identity
without editing rev2 or reusing rev2 evidence under a new scope.

Report matched cases, demonstrated incompatibilities, observation gaps and
unexercised obligations separately. Lack of an observable intermediate state
cannot prove either a matching transition or a semantic incompatibility.
Bind each mapped source/target pair and observed path to the retained concrete
state map. Record enabled choices and finite hidden progress where witnessed;
the expected successor cannot supply missing observations. No amount of sampled
case success establishes complete runtime coverage or checks the formal pair's
complete quantified carrier. The latter remains #974's distinct obligation.
A runtime incompatibility record is not a machine-checked counterexample to
the formal model pair; #973/#974 own that separate evidence boundary.

## Cross-cutting security and repository boundaries

| Layer and canonical incumbents | Required fit |
| --- | --- |
| Repository file and JSON ingress | `implementations/formal/participant_crossing/ingress.py::read_bytes()` owns descriptor-relative, regular-file, no-follow, byte-bounded reads; its `safe_path()` and `tools.policy.common.safe_repo_path()` own repository containment. `raes_contracts.json_ingress.parse_bounded_json_object()` owns duplicate-key/nonfinite/depth/root rejection. Reuse these in that order for mapping inputs; containment alone is not race-safe file admission, and a `SafeRef` is not path authorization. Bound individual and aggregate evidence collections/bytes and offline work; use genuine integer coordinates, not bool/string coercion. |
| Contracts and callback validation | `ContractModel(extra="forbid")`, existing revisioned profiles and contextual validators own structure and semantic joins. Revalidate detached callback outputs and trusted references; an accepted shape or matching digest is not authority. Whole snapshots pass `validate_realization_value()`, `RUNTIME_SNAPSHOT_VALUE_LIMITS`, runtime-owned history and backend snapshot validators. Keep a small internal evidence format separate from published runtime carriers. Any necessary public shape change follows ADR-009/061/075, published schemas/fixtures, `schema_bundle()` parity and `contracts/schema-publication/entries/` plus manifest hashes; do not modify schemas to fit the checker. |
| Authored scenarios and plans, when exercised | Existing typed fixture/runtime builders remain canonical. If a case loads SDL, `raes/parser.py`, `_yaml_loader.py`, `SemanticValidator`, compiler/planner validation and `control_plane_plan_authorization.py` retain bounded parsing, reference-purpose checks, compiled policy identity and exact installed consumer context. Direct model construction or a callback-supplied plan digest cannot bypass those owners. No new YAML parser, authoring syntax or mapping annotation is needed. |
| Assurance claims and similarly named reports | `BehavioralClaimBindingModel`, `validate_behavioral_claim_binding()`, revision-aware `behavioral_relations.py` / `behavioral_relation_profiles.py`, ADR-081/100 and `tools/check_behavioral_relation_claims.py` own relation/profile/projection joins, quantifiers and independent assurance axes. The current catalog must not replace pinned rev8. Use canonical claim bindings if making a claim, not a lookalike free-form relation object; finite case evidence cannot carry universal quantifiers or a proof status. `SemanticComparisonResultModel` compares governed authored artifacts; `SemanticProjectionReportModel` reports concept predicates. Neither is a runtime transition map or the participant/audience observation projection. Reuse base primitives, not those unrelated report semantics. |
| Configuration and installed capability | `ControlPlaneOptions` / `ControlPlaneConfiguration`, `PlanScope`, `RuntimeTarget`/registry validation, `control_plane_composition.py`, `control_plane_profiles.py` and profile admission own typed run/store/provider/resolver bindings and final-sink selection. Record the admitted configuration and installed capabilities in evidence. Declaration alone grants no capability. Do not bypass configuration checks or make a runtime profile claim from a finite proof-profile id. |
| Authentication and read authorization | `ControlPlaneIdentity`, participant control/audience subject bindings, `_require_crossing_identity()`, effect `require_drain_authority()` / `origin_principal()` and operation readback retain exact actor/role/target/run/subject authority before replay disclosure. Typed fixture identities model trusted embedded callers, not transport authentication. P0/P1 embedded objects and stores stay in the trusted host; an audience binding does not restrict raw snapshot access. |
| HTTP, when exercised | `create_control_plane_app()`, `ControlPlaneSecurityConfig.strict_defaults()`, sealed route authority in `_auth.py`, `RequestSizeLimitMiddleware`, `_operation_routes.py` and `_responses.py` retain authentication before validation disclosure, request/admission bounds, stable redacted 4xx/5xx and `no-store`. Use an in-process client, no new listener. HTTP error/status/timing distinctions do not silently become a modeled refusal or hidden step; transport behavior outside the projection is an explicit limitation. No new endpoint, proxy trust or public DTO is needed. |
| Secrets, environment and OS | Mapping needs no live credentials, secret files, network service or external upload. Use local synthetic values; never read `/home/atomik/.secrets`. Preserve `SecretReferenceId`, `raes/runtime_environment.py::RuntimeEnvironmentVariable` name/classification/provenance and literal/`value_from` exclusions, runtime fact-binding policy and `raes/runtime_values.py::enforce_observed_value_redaction()`. Do not invent an environment-variable bag or resolver. No new subprocess is needed; credentials/private payloads must not enter argv, URLs, shell interpolation, environment dumps or evidence. Existing local-store ownership, restrictive file/sidecar permissions and single-writer leases still apply. |
| Mutation, persistence and recovery | `RuntimeMutationAuthority`, `control_plane_mutation()` / `external_control_plane_call()`, supervision limits, one-use `InvocationLedger`, store CAS/expected-head checks, strict codecs and `RuntimeDurabilityMixin` retain writer fencing and durable identity. Extensions release the writer permit; recheck the captured cut after callbacks. Reuse memory/local-store tests and their admitted restart/readback paths; neither another journal/cache nor retries after uncertain effects are justified. Additional store/profile evidence remains explicitly scoped; no remote database service is needed for this issue. |
| Errors, audit and evidence | Reuse `Diagnostic`, `portable_diagnostic_payload()`, `operation_terminal_diagnostics()`, `OperationReceipt`/`OperationStatus`, existing `PermissionError`/`ValueError`/`SnapshotRevisionConflict`, `AuditEvent` and `control_plane_audit.py` closed keys. No duplicate exception hierarchy or logger. Omit raw exceptions, Pydantic inputs, carrier reprs, evidence bodies and backend output from logs/errors. Portable diagnostics validate shape and address encoding; they do not sanitize message content. The committed baseline of `_bind_participant_decision_surface_v2()` places `str(exc)` from binding callbacks in a diagnostic; a pre-existing working-tree change replaces it with fixed text. Error-path evidence must verify caller response, stored diagnostics and audit before claiming redaction. This preflight makes no runtime repair. ADR-066 separates telemetry, audit, participant disclosure and experiment evidence; a denial log cannot substitute for an observed transition. Untimed evidence establishes no latency, absence-window or timeout equivalence. |
| Workflow and publication | `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`, `tools/nox_support/`, `tools/verification_plan.py`, `tools/policy/adr_policy.yaml`, authority/concept/behavioral-claim/schema/assurance gates and `.github/workflows/ci.yml` remain canonical. ADR-015/036 keep runtime dependent on contracts/protocols and public processor seams, not formal/conformance machinery or concrete backend implementations. Use explicit relevant tests and scoped policy/hygiene locally; full/integration/fuzz/completion suites belong to CI. Set `RAES_REQUIREMENT_UID=SEM-232` on this branch, which lacks a UID; #972 evidence does not complete SEM-232. Release-owned version/changelog and accepted ADR bytes remain untouched. |

Artifact output reuses `export.py::publish_bundle()` for staged complete bundles
only under its documented trusted-parent, exclusive-writer boundary. Use a
distinct mapping destination and read-only drift checking; never overwrite
retained construction evidence. Its `safe_path()` followed by `os.rename()` is
not a race-proof no-replace protocol for untrusted or concurrent destinations.
Extending that boundary requires descriptor-relative, no-follow, atomic
no-replace publication, not another copy of the current publisher. Keep raw
store files and diagnostic payloads out of the export; local store permissions,
including sidecars and owner leases, still apply.

## Evidence integrity and non-goals

Publish the state/transition mapping with observed public-call outcomes, ordered
validated facts, committed state/record/audit joins, differential results,
admitted-case coverage, gaps, incompatibilities, limitations and non-claims.
Cover the five inputs at the admitted cuts, retries and stale cuts, transformed
revalidation, v2 context, repaired provider/effect execution and final egress.
Negative evidence includes identity/context mismatch, unresolved required
capability, changed request under a key, protected state changes on refusal,
partial commit/lost acknowledgment, unsafe errors and unsupported timing
projection. Distinguish precondition rejection from a modeled transition.
Fault injection at existing provider/store seams must retain production
admission and readback. Samples and negative fixtures do not establish the
complete live-runtime transition relation or the downstream equivalence result.
Join each observed transition to concrete source/target states and its witnessed
path through the declared hidden classes. Cut advance is admitted only at idle
or terminal; a callback-time stale cut cannot be silently reordered into that
environment action. Existing shared-time/expiry admission stays with its owner;
an apparatus timeout is not automatically a modeled unsupported decision.

Use `raes_contracts.canonical.canonical_json_bytes()` / `canonical_json_digest()`
for semantic JSON identity and exact-byte hashes for source, AUT and serialized
artifacts; pretty JSON bytes are a different identity. Bind mapping/driver and
fixture source, selected runtime dependency closure (including provider/effect,
v2, sink, commit/recovery and validation owners), profile/projection/catalog,
configuration, lockfile/environment and retained model artifact identities.
Record actual interpreter, distribution, driver and store versions and the safe
platform identity; a lockfile alone does not attest installed tools. Never use
an environment dump as provenance.
Hash the bytes actually consumed by a fresh executing checkout, including dirty
source, with an acyclic manifest. Unknown/missing pins and changed sources,
schemas, config, mappings, counts or model artifacts invalidate affected current
evidence until reviewed and rechecked. Reuse model ingress/export/AUT plumbing
for nonsemantic work; do not copy its transition logic into a differential oracle.

The earlier preflight recorded successful exact-profile validation and in-memory
bundle construction, but a read-only single-profile CLI comparison failure
against the retained bundle. Eleven paths differed from the retained rev2 source inventory.
This is historical-source drift, not a malformed profile or authorization to
regenerate its manifest or change model pins.
Preserve the #971 bundle and publish separate current mapping evidence with
honest source identities and compatibility status. Source-bound formal research
snapshots/analyses use immutable content-addressed branch captures through
`tools.research_capture record`, following
[research-capture conventions](../develop/research-captures.md). No numbered
release allocation, rewritten published history or shared narrative index edit.

Earlier preflight checks recorded on 2026-10-27: scoped repo policy passed before
and after editing; profile validation and in-memory construction passed; read-only retained-bundle
checking reported the drift above. The selected runtime checks did not complete:
`test_v2_selection_forwards_authenticated_context_to_governed_admission` timed
out at the configured 120 seconds, and an isolated retry timed out at 15 seconds.
The reported `runtime-execution` portal thread was waiting in the event loop;
the cause is not established. Both invocations were interrupted after timeout.
Do not treat those attempts as passing prerequisite evidence. Public execution
progress remains an unresolved verification risk for the implementation owner;
this preflight authorizes no runtime repair. These checks establish no new
mapping or assurance result.

The API-404 follow-up on the same date checked the canonical profile matrix,
requirement-to-profile alignment and clause-map profile bindings: three targeted
tests passed. File-local repo policy passed before and after the guidance edit.
These are structural/profile checks, not a rerun of the earlier timed-out
execution checks or evidence that the draft runtime mapping conforms.

Non-goals: implementing runtime repairs or new policy semantics, expanding the
finite carrier, changing retry behavior, adding a schema/store/service/workflow,
running a checker per request, making a #974 bisimulation decision or #975
independent-reproduction claim, concrete backend conformance, whole-runtime
equivalence, noninterference/opacity, concurrency or timing guarantees. Report
incompatibility rather than repairing or hiding an operation to obtain a pass.
