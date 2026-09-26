# Issue #1355 — Executable mixed mapping and time preflight

Date: 2026-09-24. Inspection baseline: `b00aba06389a`.
Scope: architecture guidance for the issue #1355 decision, not an accepted
normative amendment or an implementation plan.
This note does not activate a backend, publish a new contract, or establish a
mixed-execution conformance claim. The issue's title, body and acceptance
criteria remain the delivery contract. The supplied diagnosis is corroborated
by `raes_runtime/mixed_runtime_dispatch.py`: an edge's mapping and loss are
recorded but not executed, and one backend `success` value produces delivery and observation
facts. The existing reference explanation describes this behavior; it is not
evidence that those later stages occurred.
`MixedCompositionEdgeModel` carries routing and time references but no
executable subject translation, bridge invocation or result/readback binding.
`mixed_runtime_phase.py` also derives a `handoff` event from a permitted phase
evaluator; that fact alone cannot prove native responsibility transfer.

## Decision boundary

Keep the admitted `sem-234/rev1` profile as sealed intent and the one
`RuntimeControlPlane` as state authority. Resolve each active directed edge to
an executable, version/digest-matched mapping and bridge responsibility at the
existing trusted `MixedRuntimeBinding` / selected `RuntimeTarget` boundary.
The binding must identify the source semantic action or observation subject,
destination subject, owning operation and component, transformation, invocation
and readback contract, time-domain/order service, declared loss, failure
disposition and evidence obligations. An edge reference, callable method,
timestamp, manifest claim or backend name alone cannot establish any of these.
Use the existing compiled identities and admitted allocation/edge/time-model
refs; do not add apparatus choice or backend commands to portable SDL.

Execute the binding under the existing RUN-310 action/control,
RUN-319/API-423 crossing and final-sink gates. A direction or handoff does not
itself invoke an effect. Exact subject mapping must preserve participant,
episode, controlled scope, action-family and audience identity, and refuse
unmapped, ambiguous, conflicting or out-of-scope subjects before invocation.
Native addresses may change; their join to those semantic identities must not.
Validate both source and translated destination shapes and the final sink's
exact subject/policy cut. Bind units, cardinality, value ranges and lossy or
non-invertible transformations explicitly; never assume a reverse edge or
round-trip equivalence. A declared loss is acceptable only under admitted
requirements and authorized weakening, not because it was logged afterward.
The component that owns a native object or the destination of a directed edge
does not thereby become acting controller, release authority or owner of the
RAES operation. A bridge may narrow an authorized projection; it cannot
broaden it, transform an unauthorized value into an authorized one, or supply
an absent policy decision. Each actual edge crossing needs its own invocation
and result correlation; an edge in the profile does not imply a bridge call.

Time execution must use the incumbent `TimeModelDeclarationModel`,
`TimeRuntimeStateModel`, `TimeCoordinateModel`, progression/transition checks
and component `TimeRuntime` readback. Bind source and destination clock/domain,
segment, mapping direction, required comparison, ordering basis and selected
progression or synchronization service to the operation cut. Obtain grants or
barrier/serialization evidence where that admitted service is required; read
back the resulting state before asserting the comparison or delivery order.
An affine or identity declaration is a coordinate relation, not a scheduling
service. Partial order permits only demonstrated comparisons; incomparable
events remain incomparable. A timestamp-only source can support only its
declared weak claim. Operational monotonic supervision budgets remain separate
from authored scenario time. Physical or operational components may refuse
pause, reset, rollback, lookahead or tight coupling; the profile must admit
that limitation or the operation must be refused. No common clock, hard real
time, or physical-OT timing guarantee follows from shared time semantics.
Clock conversion must retain exact rational and segment/microstep semantics;
never round a fractional coordinate into an asserted exact tick. Cyclic coupling
needs an admitted progress basis and bounded stall disposition; topology alone
proves neither deadlock freedom nor safe rollback. Control-loop posture, world
assumption and membership remain independent axes.

## Outcome and handoff invariants

| Boundary | Owning evidence and permissible claim |
| --- | --- |
| Request accepted | `OperationReceipt`/`ControlPlaneOperationRecord` and immutable admission context prove acceptance only. Recheck effective capability and contextual willingness before dispatch. |
| Decision and attempt committed | RUN-310/API-423 decision plus composition history and complete history-head/snapshot CAS prove authority for one attempt, not execution. A failed commit invokes nothing. |
| Backend execution | Correlated provider result and validated typed readback prove only the established effects. A contract-satisfying no-op need not change state. A boolean, exception-free return or echoed request is insufficient. |
| Directed delivery | API-423 delivery attempt and a destination receipt or equivalent admitted sink evidence prove delivery to that boundary. Mapping/bridge success alone does not. |
| Participant observation | API-423 observation is emitted only after its own participant/audience projection and observation evidence. Delivery, status-view construction, audit retention and experiment collection do not imply observation. |

Use the shared operation lifecycle (`ACCEPTED`, `RUNNING`, `SUCCEEDED`,
`FAILED`, `CANCELLED`, `INDETERMINATE`) and its supervision semantics for
settlement. Preserve known partial effects as correlated evidence and select
the terminal state from requirement satisfaction and cessation evidence; do
not add a `PARTIAL` state. At bounded settlement, unknown required effect,
delivery or observation is `INDETERMINATE`; a known, quiescent partial failure
retains its validated residual effects. A committed terminal parent is immutable:
later evidence belongs to an authorized linked resolution. Timeout cannot prove
zero effects or success. Pre-claim refusal remains audit-only; contextual refusal
after acceptance and before dispatch follows the shared cancellation rule.
Do not re-invoke an effect through idempotent replay, restart or phase
progression. Retain conflicting-effect
exclusion while cessation is unknown. Commit terminal operation, snapshot,
owning histories and safe audit through the incumbent store transaction; an
uncertain store acknowledgement poisons readiness until authoritative readback.
Correlation must distinguish operation, invocation/stage, directed edge,
component, phase revision and the original authority/time cut. Recover every
invoked stage from its persisted responsibility; the current single-component
`mixed_recovery_target()` alone cannot reconcile a multi-stage bridge operation.
Local atomic publication does not make effects across components atomic or
exactly once. Repeated, reordered or late receipts cannot create a second
effect or rewrite terminal history.

Use [the shared supervision semantics](../../specs/formal/runtime-control-plane/supervision.md)
for all external calls, including capability checks, bridge invocation, time
grants/barriers, handoff evaluators and readback. They require finite budgets,
retained conflicting-effect exclusion and a serviceable supervision path.
At this baseline, `RuntimeMutationAuthority.external_call()` prevents re-entry
but retains the logical mutation permit; it supplies neither interruption nor
the supervision guarantee. The #1348 tests are design-model witnesses. Treat
the shared supervision implementation as a dependency for any such positive
claim; do not hide a second timeout/worker engine in mixed dispatch. A finite
phase count or evaluator attempt bound does not bound callback duration.

For staged phases, quiesce outstanding attempts and deliveries under their
original provider before committing the next phase. Native responsibility
handoff has requested/offered/pending/committed/failed/expired/cancelled/stale
dispositions under MCB-013–017; only an evidenced, revision-fenced commit
changes responsibility. RUN-310 controller handoff is a separate API-409
occurrence and never follows from native ownership transfer. A stale
controller, authority, capability, policy, state/history head or governed
order refuses a new effect. Failed or unknown handoff leaves the last committed
responsibility fact unchanged and blocks dependent work. Unknown native transfer
does not prove the former provider can safely continue: quarantine that scope
until both responsibility and cessation are reconciled. Quiescence includes
lifecycle work, pending deliveries, time services and callbacks, not just the
action/crossing records currently scanned by `_mixed_runtime_is_quiescent()`.
Inter-trial changes retain distinct plan-entry/run identities and source lineage.

## Canonical owners and compatibility

Package-qualified paths below are relative to `implementations/python/packages/`.

| Concern | Existing owner to extend or reuse |
| --- | --- |
| Authored meaning and admission | `specs/formal/participant-semantics/cross-backend-participant-control.md` MCB-001–045, ADR-102, `MixedParticipantCompositionProfileModel`, bounded `parse_mixed_composition_profile()`, `validate_mixed_composition_context()`, `AdmittedTrialPlanModel`, `revalidate_admitted_trial_plan()` and trial compiler apparatus/capability admission. An evidence ref must resolve to evidence that supports its specific obligation; presence of the ref alone is insufficient. |
| Effective support | API-407 `BackendManifestV2Model` / `ParticipantFeatureSupportModel`, `manifest_authority.py`, `raes_backend_protocols/participant_feature_admission.py`, `capability_admission.py::time_model_capability_gaps`, `participant_control_admission.py`, registry component/method checks and selected realization envelopes. Separate declaration, installed implementation, per-context willingness, conformance evidence and authorized downgrade; no union of component manifests. |
| Runtime and persistence | `MixedRuntimeBinding`, `mixed_runtime_dispatch.py`, `RuntimeTarget`, `backend_calls.py`, `backend_snapshot_contracts.py`, `RuntimeMutationAuthority`, `ControlPlaneOperationRecord`, `ControlPlaneStoreCommitAdapter`, lease/CAS/recovery and `MixedCompositionRuntimeEventModel`. Composition history cites owning facts; it is not another operation, crossing or control ledger. |
| Policy and results | `participant_control_mediation.py`, `participant_crossing_{mediation,commit,egress}.py`, `participant_flow_sink.py`, `ParticipantActionAdmissionRequest`, API-423 contextual validation and API-408 projections. Use their final sinks and distinction between attempt, delivery and observation. |
| Time and evidence | `raes_contracts/contracts/time_model.py`, `raes_runtime/time_control.py`, `time_coordinator.py`, `ParticipantRuntimeOrderingBasis`, `TimeRuntime` and runtime readback; `raes_conformance/time_semantics.py` and the existing conformance probe/report framework, scoped observation demand, apparatus evidence and ASR-537 claim separation. Preserve declared loss and uncertainty through result and history. |
| Publication and verification | `ContractModel(extra="forbid")`, `schema_bundle()`, `contracts/schemas/`, schema publication manifest/entries/fixtures, ADR-061 compatibility, `.ground-control.yaml`, `.gc/plan-rules.md`, canonical nox/policy checks and targeted #1014–#1016, time, crossing and #1348 tests. |

The accepted issue decision should amend SEM-234's executable edge/handoff
meaning, API-407's effective mapping/time/bridge support obligations, and
ADR-102's reference-only boundary as needed, without silently changing the
meaning of an existing published `sem-234/rev1` profile or manifest. If an old
carrier cannot express a required executable binding or correlated stage
outcome, publish a versioned, closed contract and explicit reader/compatibility
rule. Historical reference-only records remain reference-only; do not
reinterpret their `success`, mapping refs or timestamps as delivery,
observation or governed timing proof. Keep supported old single-target/pure
paths working, while refusing a mixed arrangement whose new obligations have
no effective implementation. Executable examples must drive the actual
control-plane/target boundary, with positive and negative cases for pure,
simultaneous mixed, linked inter-trial and pre-admitted staged arrangements;
assert the call count, distinct stage facts, readback, loss and final state.

Use `specs/formal/runtime-contracts/participant-backend-contracts.md` for
API-407 changes. Keep its governed feature terms, scope/required-contract maps,
model/dataclass adapters and JSON Schema parity aligned; unknown extension
terms must not gain vacuous exact support from an empty required-contract set.
Support strength alone cannot compare incompatible constraints. Resolve evidence
and downgrade authority in trusted context; the existing feature resolver checks
reference presence and strength, not the truth of executable obligations.
Per-edge bindings belong outside the open capability `constraints` map. Reuse
API-424 mechanism/effect bindings where applicable without confusing mechanism
identity with SEM-234 apparatus identity.

### API-407 declaration boundary

Apply the incumbent [API-407 declaration/admission guardrails](issue-1072-api-407-feature-support-preflight.md)
to #1355. `capabilities.participant_runtime.feature_support` remains the sole
participant strength declaration, using the existing four-level scale
(`unsupported < disclosed_weak < bounded < exact`). Partial or constrained support is expressed through that level and
its constraint, limitation, disclosure and evidence references, not a new
`partial` enum or mixed-backend support block. Those four reference roles are
not interchangeable. SEM-218 `realization_support` and the selected realization
envelope remain independent cross-domain requirements. Neither establishes
participant support; participant support cannot waive them.

Shared time already has `TimeCapabilities` and
`capability_admission.py::time_model_capability_gaps`, covering domain,
authority, progression, synchronization, mapping, capacity, reset and replay
declarations. Reuse these for the applicable component time obligations;
do not copy their fields into API-407 or make every component support every
other component's clock. An exact participant feature claim does not establish
a barrier, bridge, serialization service or timing guarantee. Effective support
requires their installed implementation and evidence for the particular
provider, directed edge and phase. The mapping-kind check currently recognizes
`identity` and `affine_rational`; partial-order semantics cannot be introduced
as an arbitrary new string or inferred from timestamp ordering.

Two current validator seams need explicit treatment in the accepted design:

- `resolve_participant_feature_support()` returns `None` for a legacy listed
  feature outside the evidence-required set when no entry exists. This makes
  no strength claim. Preserve that legacy behavior outside the newly claimed
  scope, but require an explicit entry for a mixed obligation needing a
  strength. Unsupported never becomes an executable downgrade.
- Unknown governed extension terms can resolve to an empty required-contract
  set. Vocabulary syntax alone must not confer executable support. If new
  terms are necessary, align the vocabulary, scope, required-contract map,
  backend-contract allowlist, evidence-required set, schema and dataclass/model
  adapters. `BackendManifestV2Model._validate_participant_policy_contracts`
  currently indexes the **behavior** map for every evidence-required term;
  adding an interaction term to that set alone is invalid. Declaration-only
  terms must not enter `PARTICIPANT_RUNTIME_POLICY_FEATURES`, which also drives
  runtime policy behavior and reference-backend declarations.

The resolver compares strength and checks reference presence; trusted
`MixedCompositionResolutionContext` joins must establish evidence satisfaction
and exact downgrade authorization. Apply constraints to the selected binding:
equal strength does not make incompatible units, bounds or services compatible.
Keep requested and effective support distinct, retain weakening provenance,
and recheck current willingness before effects. A runtime refusal or unknown
operation outcome is not a new manifest support level. Use the existing
planner gaps and conformance runner, with provider-local negative cases in
`test_backend_manifest.py`, `test_issue_1014_mixed_composition_contracts.py`
and `test_issue_1015_mixed_staged_trial_admission.py`; declared references alone
cannot replace executed mapping/time probes.

ADR-059 requires an ADR-102 amendment row and matching `adr-index.yaml` record
and pin for any accepted-text change. ADR-061 and
`contracts/schema-publication/README.md` govern schema evolution: update the
owning `contracts/schema-publication/entries/` record (the root manifest is an
index), generated bundle parity and fixtures. Keep semantic revision, wire
version and evidence release distinct; preserve immutable historical evidence.
This preflight leaves those normative artifacts unchanged.

## Cross-cutting gates

1. **Ingress and configuration:** keep bounded JSON parsing, duplicate/depth
   checks through `json_ingress.py`, closed profile/plan models, digest and
   exact-context joins. Bound translated payloads, graph/context traversal and
   fan-out too. Direct Python inputs require the same validation; frozen
   dataclasses and mapping proxies do not deeply freeze nested models.
   `ControlPlaneConfiguration`, `MixedRuntimeBinding`, `RuntimeTarget` registry
   signatures and manifest/envelope identity checks validate the installed
   binding. Neither HTTP fields nor environment variables select a component,
   bridge, clock or mapping. New executable parameters belong in the trusted
   binding of an admitted edge, so another conforming adapter does not require
   changes to SDL, the dispatcher's semantic selection or store ownership.
   Parameterize that seam by pinned mapping/bridge version, source/destination
   subjects, service/readback contract and admissible bounds. Resolve installed
   implementations through the existing registry/protocol boundary; portable
   refs are not module imports, scripts, filesystem paths or fetchable URLs.
2. **HTTP and authorization:** retain `create_control_plane_app()`,
   `RequestSizeLimitMiddleware`, closed request DTOs, bounded queues,
   `Idempotency-Key`, `_ControlPlaneApiAuth`,
   `ControlPlaneSecurityConfig.strict_defaults()`, logical target binding and
   participant/controller/audience subjects. No backend token, native owner,
   component id or bridge identity supplies participant authority.
3. **Secrets, environment and host:** retain `RuntimeEnvironmentVariable`
   name/value versus `value_from`, classification and redaction validators,
   `secret_references.py`, runtime-fact binding policy, credential sanitizers
   and `control_plane_store_paths.py`/`control_plane_store_lease.py` checks.
   Environment names must be nonblank and exclude `=`; `value` and `value_from`
   are exclusive, generated values cannot claim `operator_secret`, and redacted
   or operator-secret values cannot carry plaintext. Keep these authored runtime
   shapes distinct from host credential injection. Carry safe ids, refs and bounded
   diagnostics, not secret values, payloads, host paths or low-entropy secret
   digests. The coordinator adds no subprocess, shell, socket or argv/env
   authority; backend-owned native I/O must stay behind admitted endpoints and
   host permissions, never arbitrary request-selected destinations. Never expose
   tokens or action data in process arguments, logs or tracebacks. Existing
   `require_single_worker_configuration()` and store ownership, link and private
   file/sidecar permission gates still apply.
   If an adapter consumes generated environment values, it must also pass
   `raes_processor/planner/stateful_admission.py`'s exact projection keys,
   delivery mode, node/output, consumer and sensitivity joins. Reuse
   `prepared_node_projection.py`; an arbitrary environment dictionary cannot
   bypass these checks merely because the SDL value shape was valid.
4. **Backend and publication:** keep deep-copy call isolation, backend result
   type/ownership/changed-address checks, time readback, strict snapshot codec,
   history-head and revision CAS. `Diagnostic` and existing result envelopes
   use `backend_result_diagnostics.py`, `backend_account_credentials.py` and
   `portable_diagnostic_payload()` for stable value-free codes;
   `control_plane_api/_responses.py` and `_operation_routes.py` keep conflict,
   validation and 500 responses redacted. Preserve `StrictJsonIngressError`,
   validation errors and `SnapshotRevisionConflict` instead of adding a bridge
   exception hierarchy. `AuditEvent` and the existing module loggers record safe
   operational facts, not participant observation or experimental evidence.
   `portable_diagnostic_payload()` checks the portable shape, not redaction.
   Manifest/admission validation messages can interpolate rejected terms;
   new public responses, audit and logs must not forward raw exception text,
   rejected values or exception causes. Sanitize addresses as well as messages.
   Apply the existing plane/audience projections to capability reasons, evidence
   refs, membership and timing metadata too; a safe string can still disclose
   information to an unauthorized participant.

## Gotchas, non-goals and assurance boundary

Avoid a second bridge policy engine, operation ledger, exception hierarchy,
schema base, clock, store, controller state or workflow engine. Do not infer
execution from a method signature, feature declaration, source timestamp,
edge presence, profile evidence ref, `ApplyResult.success`, receipt order or
metadata. Do not manufacture delivery/observation from backend success; do not
erase prior knowledge on retraction/replay or use audit as participant evidence.
Do not turn partial order into total order, weaken an exact requirement because
one backend is weak, or use runtime fallback after contextual refusal.

This issue does not require a generic federation framework, backend-native
HLA/FMI/HELICS support, a new physical backend, multi-controller or leased
authority, distributed transactions, universal rollback/retry, universal
collection, empirical transfer, backend equivalence or IFC/noninterference
proof. The accepted design and executable examples must state the bounded
guarantee and test zero prohibited calls for pre-effect refusals, distinct
execution/delivery/observation evidence, partial/unknown after-effect paths,
stale and failed handoff, incompatible clocks and weak timing, restart
reconciliation, and a successful mapped exchange.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/requirement_order.yaml`,
`noxfile.py` and `.pre-commit-config.yaml` for workflow and verification. Set
`RAES_REQUIREMENT_UID=API-407` for this requirement's work, or `SEM-234` for
its semantic-owner work, when needed. Run only targeted local checks;
full, integration and fuzz suites remain CI-owned. Extend the #1014–#1016,
#1200, API-421/shared-time, crossing, API and operation-lifecycle witnesses
where their owning boundary changes; design-model tests and golden metadata
cannot replace executed adapter/bridge probes. No implementation or new tests
are part of this preflight.
