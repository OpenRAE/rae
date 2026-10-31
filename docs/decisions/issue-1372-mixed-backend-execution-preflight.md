# Issue #1372 — Mixed execution through the shared runtime

Date: 2026-10-16. Architecture preflight for requirement-free issue #1372;
its supplied issue body and acceptance criteria are the delivery contract.
Prerequisites #1371 and #1362 supply contracts and execution machinery, not
automatic adoption by mixed dispatch. This note is guidance, not an
implementation plan or a claim of implemented behavior.

Retain [ADR-102 §13](adrs/adr-102-mixed-cross-backend-participant-control.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md), the
[mixed contract reader/settlement rules](../migration/mixed-backend-execution.md),
and the [shared operation protocol](../../specs/formal/runtime-contracts/backend-operation-supervision.md).
The [#1355 preflight](issue-1355-executable-mixed-mapping-time-preflight.md)
and [#1362 preflight](issue-1362-supervised-execution-preflight.md) provide the
cross-cutting guardrails; their historical gap descriptions are not a current
implementation inventory. These decisions suffice: no new ADR is needed.

## Boundary decisions and current integration traps

Package paths below are relative to `implementations/python/packages/`.

- **One operation owner.** `mixed_runtime_dispatch.py` already resolves the
  exact active allocation and joins controller, routing, crossing and final-sink
  authority. `participant_crossing_boundary.py` commits the decision/attempt,
  invokes the mixed callbacks and commits the result. `mixed_runtime_phase.py`
  separately invokes evaluators and handoffs. These paths do not currently
  attach a shared `InvocationLedger` or consume the published mixed carriers.
  Preserve their semantic checks while adopting #1362's one-use invocation,
  budgets, controls and settlement. Adding `RuntimeTarget.operation_provider`
  alone does not route these direct paths through shared supervision.
- **Binding identity is not a native plan.** #1371 requires `command` to equal
  `mixed_backend_binding_reference(binding)` and `backend_id` to name the pinned
  bridge/transfer service. The destination component remains the effect owner.
  `control_plane_supervised_execution.invocation_request()` and
  `operation_provider_execution.validate_outcome()` currently assume a native
  plan and its protected command commitment. Reuse their lifecycle machinery
  through the owning command/evidence resolution boundary; do not wrap a mixed
  binding in a fake provisioning plan, replace its digest with a plan digest,
  overwrite the plane's target, or bypass validation to fit those helpers.
  A service binding does not commit the native action/configuration itself:
  retain its exact admitted identity and resolve its existing typed artifact
  under the original request/authority commitment. Do not recover payload or
  dispatch permission from the binding alone. Controls and reconciliation must
  resolve the same pinned service; current provider helpers select the plane's
  single `operation_provider`, which is not necessarily that mixed service.
- **Non-identity does not change the authorized subject.** Both compiled
  action addresses remain equal under `subject_transformation=compiled-identity`.
  The pinned bridge may translate backend-native representation; an admitted
  affine-rational time mapping may also be non-identity. Neither permits changing
  participant, action instance/contract, configuration, implementation selection,
  authority, audience or terminal-outcome demand. Preserve these joins across
  translation and readback, together with operation/invocation/attempt,
  target/run/plan-entry, profile digest, phase revision and ordering identity.
- **Declarations and reports are not proof.** Reuse
  `raes_backend_protocols/mixed_backend.py`'s `MixedBackendBridge`,
  `MixedTimeCoordinator`, `MixedStageReader` and `require_mixed_backend_service()`.
  Reuse `validate_mixed_backend_bindings()`, `require_mixed_backend_admission()`
  and `validate_mixed_backend_stage_reports()` from `raes_contracts.contracts`.
  Shape checks neither install services nor establish willingness. The stage
  validator is pure, returns no terminal decision, and authenticates no producer
  or underlying evidence. The trusted embedder must bind each service and
  authenticate/resolve its content-bound evidence through the incumbent
  `OperationEvidenceResolver` boundary. Never accept a caller's self-labelled
  producer, digest or evidence reference as authority.

The extensibility seam belongs in **trusted, typed per-edge/per-transition
installation**, alongside `MixedRuntimeBinding` and registry validation: pinned
binding/service version and digest, role-specific implementations/readers,
native command/evidence resolution and admitted bounds. Keep portable carriers
plain data. A second conforming bridge or mapping must be selectable there
without backend-name switches, new SDL fields, an open metadata/constraints
policy language or another scheduler. Runtime declarations, API-407 support,
SEM-218 envelopes, installed service shape, contextual willingness and executed
conformance evidence remain separate admission checks.

## Evidence, ordering and handoff invariants

The owning effect may run only after the existing crossing/final-sink cut,
exact binding/contextual admission, committed attempt and confirmed one-use
dispatch authority, and an ordered grant over committed time readback. Invoke
the installed mapper/bridge and coordinator; reference presence is insufficient.
Recheck authority, phase, state/history heads and willingness after waiting.
Use the caller-resolved time-model reference/digest, both clock readbacks and
the committed composition state in `MixedBackendStageContext`, including for
edges where the pure validator allows that state to be omitted. Use RAES's own
post-invocation time readback, not the provider's asserted time. Grants advance
no clock. Preserve exact rational, segment and microstep semantics and declared
loss/coupling; wall-clock timestamps, receipt order and unproved comparisons
cannot establish governed order.

Authenticate distinct services for bridge/transfer, coordinator and each reader;
the published binding forbids sharing either service reference or digest across
roles. Do not collapse roles for convenience or treat distinct strings as proof
of deployment independence. Stage sequences are fixed chain positions
(time 1, execution/handoff 2, delivery/owner 3, observation 4), not shared response
sequence numbers or arrival order. Reordered reports may validate; this does
not authorize effects before the required grant. An acknowledgement proves
acceptance only. No owning effect follows refusal or an incomparable grant.

| Fact/outcome | Required evidence boundary |
| --- | --- |
| Execution | Correlated bridge report plus validated backend readback; retain known residual effects, scope and declared loss. A successful `ApplyResult`, echoed request or missing exception is insufficient. |
| Delivery | Pinned destination reader's receipt for this invocation and component. Execution evidence cannot substitute. |
| Observation | Pinned observation reader's participant/audience readback after delivery, subject to the existing projection/final-sink policy. Delivery, backend observation-runtime telemetry, API status, audit and archival evidence do not establish participant observation. |
| Edge success | #1371's succeeded execution, delivery and confirmed time, plus the shared protocol's satisfaction, native result, cessation and release gates. Observation is a separate fact, not an unconditional extra success requirement. An admitted observation obligation still must be satisfied. |
| Partial/unknown or missing delivery | Retain validated stage facts and residual state. #1371's partial/unknown execution and unresolved delivery establish `INDETERMINATE`; do not add a `PARTIAL` operation state or infer failure/absence. A later-stage error must not erase earlier knowledge. |
| Refusal/failure | Pre-claim refusal is audit-only; post-acceptance withdrawal before dispatch uses shared `CANCELLED` semantics. Once dispatch authority is consumed, classify from evidence accounting for that grant. An explicit incomparable grant with no invocation can support the contract's known failure; a missing grant/report cannot. Known failure still needs the shared effect/cessation evidence. |

Settlement must pass both the shared transcript and mixed stage gates. Keep
stage settlement rules with their incumbent contract owner rather than copy
another competing outcome table into dispatch. Neither validator verifies
physical truth. Native result resolution still passes `backend_calls.py` /
`_validated_backend_result()`, snapshot ownership/changed-address and credential
egress checks, and participant crossing/history/release validation. Do not use
generic snapshot acceptance to bypass the owning participant validators or to
let a backend write runtime-owned composition/control history.

The current generic `validate_outcome()` returns no native result for an
`INDETERMINATE` proposal. Mixed adoption must preserve independently validated
partial effects through the incumbent residual/snapshot boundary without
inventing success or releasing exclusion; recording only the status loses
required knowledge. Do not skip independent readback solely because a backend
returned an unsuccessful boolean.

Native handoff changes responsibility, not RUN-310 controller authority or the
RAES execution-owner generation. Reuse `mixed_runtime_phase.py`,
`mixed_runtime_handoff_execution.py` and the admitted transition evaluator.
The published carrier supports replacing exactly one component; unchanged
membership needs no transfer, and unsupported membership changes refuse.
Fence transfer evidence on the committed predecessor history head, phase
revision, source/destination owner refs and granted order. Commit the new phase
only after destination-owner readback at the next revision and confirmed time.
A stale/failed transfer is a known failure only with readback retaining the
source owner and confirmed time. Missing/contradictory owner evidence leaves
responsibility uncertain, blocks dependent work and cannot justify source-side
continuation. Quiescence must include retained invocation reservations,
lifecycle work, pending deliveries and callbacks, not only the operation kinds
and terminal states currently scanned by `_mixed_runtime_is_quiescent()`.

## Cross-cutting layers the implementation must pass

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Parsing, schemas and commitments: `raes_contracts/json_ingress.py`, `runtime_value_limits.py`, `contracts/{mixed_backend_binding,mixed_backend_stages,mixed_backend_validation,mixed_backend_transcript}.py`, `ContractModel` / `OperationContractModel` | Keep bounded bytes/depth/collections/numbers and closed strict models for in-process inputs too; bound before copying/hashing. Revalidate mutable nested carriers. Bind the sealed profile/time model and exact admitted destination allocation; refuse missing, foreign, duplicate or unsupported bindings. Use `mixed_backend_binding_reference()`, `backend_operation_request_digest()` and canonical report digests with materialized defaults/nulls and preserved array order. No duplicate DTO/schema or coercive validation. |
| Configuration and capabilities: `ControlPlaneConfiguration`, `MixedRuntimeBinding`, `RuntimeTarget` / `registry_target_validation.py`, `manifest_authority.py`, `capability_admission.py`, `operation_policy_admission.py` | Validate installed versions, roles/signatures, manifests/envelopes, normalized `run:<id>` scope and crossing resolver at composition. Require effective support and current willingness for the exact obligation. Keep strict finite budgets/capacities in `OperationSupervisionConfiguration`; no HTTP/env-selected service, mapping or destination, manifest unions, weakening or runtime fallback on refusal. |
| Auth and disclosure: `ControlPlaneIdentity`, `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `participant_crossing_{mediation,boundary,commit,egress}.py`, `participant_flow_sink.py` | Preserve original actor and exact target/run/controller/participant/audience bindings; supervisor/worker authority is separately authenticated. Preserve final-sink and projection checks for result, timing, capability reasons, membership and evidence refs. Service IDs and native owners grant no caller/disclosure authority. Existing HTTP size/queue/idempotency, route-authority inventory and sealed composition apply if transport surfaces change; no new endpoint is required. |
| Secrets and environment: `raes/runtime_environment.py`, planner `stateful_admission.py`, `prepared_node_projection.py`, `secret_references.py`, runtime-fact binding policy and `backend_account_credentials.py` | Resolve authorized secret refs only inside the native adapter. Preserve `value`/`value_from` exclusion, environment-name validation, redaction and generated-value classification rules. Generated environment delivery must also pass the planner's exact mode-specific projection keys, node/output/consumer and sensitivity joins. Mixed service installation adds no arbitrary env dictionary. Keep tokens, native payloads and credential-dependent unkeyed hashes out of durable requests/reports, engine history, logs and errors; retain protected native command/retry commitments. |
| Execution and control: `RuntimeMutationAuthority`, `LocalExecutionAdapter`, `operation_provider_{execution,control}.py`, `operation_worker_authority.py`, `control_plane_supervised_execution.py` | Bound every external mapper, declaration/admission probe, coordinator, evaluator, bridge/transfer and reader through the shared apparatus. Keep control/store capacity serviceable during blocked effects; nested work consumes remaining budget without refresh. No state permit, participant lock or store transaction may block authorized supervision behind native work. Preserve callback re-entry denial, isolated predecessor copies and at-most-one owning effect invocation. Timeout/thread cancellation proves no cessation. |
| Persistence and recovery: `InvocationLedger`, `ControlPlaneOperationRecord`, `RuntimeDurabilityMixin`, `ControlPlaneStoreCommitAdapter`, store codecs/version migrations and `operation_reconciliation{,_ledger}.py` | Retain bounded authenticated stage facts and their exact binding/trusted-cut identity in the incumbent durable operation machinery; the current ledger holds only shared responses/controls, while `MixedEdgeExecutionCapture` is transient. Reuse published stage models, append-only transitions, duplicate-content checks and one-use grants. Preserve them through memory/local/PostgreSQL codecs and any required existing store-version migration. Commit terminal record, validated snapshot, all owning history-head CAS and audit atomically; generic operation-only settlement does not supply the missing mixed-history join. Lost store acknowledgement poisons readiness pending readback. |
| Host/deployment: `control_plane_store_{paths,lease}.py`, served single-worker checks, existing backend drivers and configured execution adapters | Preserve lease-before-inspection, private database/WAL/sidecar permissions and link/descriptor checks. Keep native I/O behind admitted endpoints/host permissions; no arbitrary URL/import/path/command resolution, shell, token in argv or broad env inheritance. Reuse established distributed worker authentication if that composition is supported; do not provision services or claim support from local witnesses. |
| Errors, audit and observability: `Diagnostic`, `backend_result_diagnostics.py`, `portable_diagnostic_payload()`, `operation_terminal_diagnostics()`, `AuditEvent`, `control_plane_api/{_responses,_operation_routes}.py`, existing loggers/health | Preserve `StrictJsonIngressError`, validation errors, `SnapshotRevisionConflict` and safe value-free envelopes, redacted 422/500, unauthorized-operation concealment and no-store responses. No new exception hierarchy or raw exception/validator-input forwarding. Portable shape/bounded text is not redaction; sanitize addresses and causes too. Audit/progress records are operational facts under ADR-066, not participant observations. Readiness must retain unresolved-stage/effect quarantine. |

Recovery follows original pinned responsibilities for every invoked stage,
not just `mixed_recovery_target()`'s one destination component. Missing stage
evidence stays unknown; reopening, repeated delivery and idempotent replay must
never reissue a consumed effect grant. Terminal parents remain immutable;
later evidence uses separately authorized linked resolution. Current
`InvocationReconciliation` proves scoped absence/cessation only: do not expand
it implicitly into proof of a completed handoff or participant observation.
Administrative snapshot acceptance cannot release uncertain mixed work.
Local atomic publication promises neither distributed atomic effects nor
exactly-once backend execution.

## Verification boundary, non-goals and repository conventions

Reuse #1355's executed edge/handoff and store fixtures, #1371's closed-carrier
and transcript cases, #1016's admitted composition fixtures, and #1362's
supervision, state-authority, invocation-ledger, privacy and reconciliation
witnesses. The six issue witnesses must drive the actual shared runtime with
installed services: a non-identity mapping with observable translated native
values or affine coordinates while preserving the compiled subject, time-coordination failure,
contextual refusal, partial execution, stale handoff and missing delivery.
Assert owning-provider call counts and ordering, preserved subjects/configuration,
separate stage facts, retained residuals/authority and terminal/readiness state.
A callback merely labelled `map`, or validation of fixture JSON, is insufficient.
Also cover blocked callbacks with responsive control, forged/wrong-role reports,
changed duplicates, stale cuts/late completion, and store reopen without repeat
effects or fabricated observation. Keep these bounded and targeted locally;
distributed/integration/full/fuzz suites remain CI/CD-owned.

Whole-repo consumers include the admitted trial/profile/context, contract
corpus/publication, registry and backend protocols/adapters, participant and
mixed controllers, shared execution/control/recovery, all store encoders,
API receipt/status/error projections, host deployment and reference/migration
docs. Update adoption claims only when the actual paths execute the contracts;
historical reference-only evidence must remain reference-only.

Reuse `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/verification_plan.py`,
`noxfile.py`, `.pre-commit-config.yaml`, `tools/policy/adr_policy.yaml` and
`.github/workflows/canonical-verification.yml`. Preserve ADR-015/036 source
caps/import boundaries. No dependency or published schema change is implied;
if unavoidable, use the owning locks/artifact tooling or ADR-061 publication
entries, schema parity/fixtures and reader compatibility checks. No accepted
ADR edits, numbered research releases, changelog/version edits or invented
Ground Control requirement UID are justified by this requirement-free preflight.

Non-goals: a federation/bridge framework, new workflow/interpreter/supervisor,
parallel policy or evidence ledger, generic retry/rollback/compensation,
arbitrary membership changes, controller transfer, new support levels or SDL
syntax, physical timing guarantees, P3 activation, backend equivalence or new
hosting/services. Implementation is confined to executing admitted mixed
obligations through existing shared runtime authority and native adapters,
with truthful evidence, settlement, persistence and recovery. Pure/single-target
paths retain their own supported semantics without fabricated mixed stages.
