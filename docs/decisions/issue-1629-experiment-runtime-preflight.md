# Issue #1629 — Experiment runtime preflight

Date: 2026-10-28. The supplied issue is the delivery contract.
No formal requirement is attached. Native GitHub blocked-by links govern
dependencies. This review does not certify their closure.
This note gives architecture guardrails, not an implementation plan.

## User clarification and implementation assessment

The runtime is the common engine for every OpenRAE workload.
Experiment sequencing belongs inside that runtime with its other optional modules.
The [revised design](issue-1629-shared-runtime-design.md) preserves that boundary and adds the required DFDs.
The code ties the engine lifetime to one run.
The [remediation plan](issue-1629-runtime-remediation-plan.md) proposes their internal separation.
The user approved this broader runtime refactor on 2026-10-28.
Retries must follow the relevant scenario author's choices through RAE's existing semantics.
The earlier claim that existing ADRs need no change is qualified by this assessment.
ADR-104 should state which parts live with the engine and which live with each run.
The existing scope, supervision, and evidence protections remain binding.
The revised scope also includes the existing Temporal path.
It already drives individual operations; it does not yet drive the full experiment loop.
The proposed shared run lifecycle must work through local and Temporal drivers.
New deployment services and coordinated P3 ownership remain outside scope.

## Ownership and current gaps

[ADR-084](adrs/adr-084-scenario-variation-and-deterministic-trial-realization.md),
[ADR-094](adrs/adr-094-authoritative-cross-plane-experiment-bindings.md),
[ADR-104 §11](adrs/adr-104-runtime-control-plane-architecture.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md) and
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) settle the owners.
No new ADR is needed. The processor admits and realizes plans through pure calls.
It also compiles replacement plans. The runtime owns live decisions and
supervision. It checks results before committing state. Backends own native
effects and observations. An allocator owns placement and live isolation.
Archive contracts own scientific records.

Paths below start at `implementations/python/packages/` unless stated otherwise.
The current checkout supplies the following pieces, with material limits:

- `raes_runtime/manager.py` aliases `RuntimeManager` to `RuntimeControlPlane`.
  That owner already directs apply, later evaluation and teardown.
  It also drives participant, time and workflow phases. Its settings, records
  and store are bound to **one target/run**. An experiment has many run IDs.
- `raes_processor/trial_realization.py::realize_admitted_trial_entry()` returns
  the instantiated scenario and native `ExecutionPlan`. It also returns portable
  plans and sealed participant configurations. It executes no live trial.
  It explicitly refuses mixed-composition entries.
- `raes_backend_protocols/trial_unit.py::BackendTrialUnit` defines a single-entry
  protocol. `raes_contracts/trial_unit.py` supplies bounded request/result
  carriers and structural joins. Neither installs an executor or checks evidence
  content. Neither supplies a resumable experiment loop.
- Participant model/prompt configurations reach the request, but the runtime
  does not yet prove they were applied. A digest cannot prove they ran.
  Nor can a fake adapter that echoes the request.
- The runtime persists operation records. `ControlPlaneStore` has no experiment
  decision record for dispatch or replacement budget claims.
  Neither `BatchSchedule` nor an archive receipt supplies that authority.

Extend the existing runtime owner to cover the experiment lifetime.
It must retain each run's scope. The public controller owns admission and
dispatch throughout the experiment. It also owns cancellation, settlement and
recovery. Each internal run context keeps its immutable `run:<entry.run_id>`
store, claims and snapshot. Do not replace the public controller between phases
or entries. Do not rebind a store to another run or replace run IDs with an
experiment ID. Experiment bookkeeping must not create a second backend
dispatcher or scenario interpreter.

The missing durable decision boundary needs an explicit experiment scope and
owner. Build on the existing store, transaction and recovery machinery.
Per-run operation ledgers remain the authority for actual effects.
The current store protocol cannot persist experiment decisions.
Do not hide them in `RuntimeSnapshot.metadata` or arbitrary operation results.
Do not introduce a separate database, workflow engine or storage service.
An in-memory composition cannot claim recovery after process loss.

## Admission and factorial fidelity

Reuse `raes_contracts/admitted_trial_plan_ingress.py`. External JSON uses
`parse_admitted_trial_plan_json()`. Caller-held plans use
`revalidate_admitted_trial_plan()`. Preserve bounded strict JSON, closed
`ContractModel` shapes, strict scalar constraints, whole-plan seals and joins.
Reconstruct retained nested values before effects. Frozen dataclasses do not
freeze their children. Bound total work and evidence before copying, hashing or
persisting them. A detached entry or a valid digest grants no effect permission.
A plan seal proves internal consistency. It cannot prove agreement with absent
original inputs or trust in the caller.

Use `raes_processor/trial_compiler` to admit complete plans and recheck source
joins. Use `trial_realization.py` to reconstruct each exact entry and select SDL.
It checks task, capture and apparatus pins and calls the planner.
Keep the native execution plan's original compiled input and apparatus context.
Keep its observation owner and run/value bindings. Portable plans alone do not
prove their source. Register exact trusted plans through
`control_plane_plan_authorization.py` before dispatch.

Preserve both typed structural selections and complete participant
configurations, including fixed/default values, model choices, pinned prompt
content and scope. Keep source descriptors, owner/manifest joins and digests.
`raes_contracts/participant_configuration.py` owns normalization and validation.
Do not rerun defaults, aliases or owner normalization at execution.
The selected concrete SDL still passes the public selector and whole-scenario
validators. Node removal must not bypass reference, runtime configuration,
participant/control-context, artifact or capture-demand checks. Unsupported
configuration application must refuse before effects. Never silently omit a
treatment. Require observations from existing participant/backend evidence
owners. A configuration record alone supplies no proof of execution.

`raes_processor/trial_scheduler.py::plan_batch_schedule()` and
`raes_contracts/contracts/trial_coordinate_order.py::canonical_entry_order()`
own dispatch order. Recorded allocations use `allocation.entry_order`.
Other plans use the existing coordinate policy. Never sort the randomized plan
again or redraw allocation/random streams. Keep preallocated ordinary run IDs.
Worker availability and completion order cannot choose the next coordinate.
`dispatch_batch_schedule()` is a callback traversal, not a durable scheduler.

Keep whole-plan trial-control admission from #1628 before the first effect,
including an unsupported later entry. Reuse
`raes_backend_protocols/trial_control_admission.py` and
`raes_contracts/contracts/trial_controls.py::required_trial_operation_guarantees()`.
Static declarations do not prove installed support or current willingness.
`control_plane_supervised_execution.py::invocation_request()` currently sends
no trial-derived guarantees for ordinary native operations. The trial adapter
must carry those demands into existing live capability/admission checks.
Compilation alone cannot supply them. Preserve exact command, backend,
capability digest and request bindings. Unsupported native recovery policies
remain refusals under `operation_policy_admission.py`.
`OperationKind` has no trial kind. Compose existing native operations.
A new kind would need changes to its closed contract consumers.
Do not disguise a trial as provisioning to bypass command validation.

## Persistence, interruption and cleanup

Persist authoritative dispatch intent before an entry can cause effects. Bind
the decision to the admitted plan/digest, entry, recorded ordinal, preallocated
run, distinct execution attempt, target, actor and resource ownership. Retain
operation references and the admitted deadline/budget origin. On restart, read
that decision and its operation ledger. A lost acknowledgement or final result
must not cause a new attempt.

Reuse `control_plane_mutation.py`, `control_plane_durability.py`,
`ControlPlaneStore`/`AtomicControlPlaneStore`, revision/history CAS, owner leases,
`RuntimeResourceClaim`, invocation generations and reconciliation. Backend calls
stay outside short state mutations. Only the runtime commits validated state.
Read back uncertain writes from their store. Keep existing poisoned readiness
until that check succeeds. Do not issue another write with a fresh identity.
A stale owner or late callback cannot advance a replacement, erase quarantine
or overwrite a committed terminal.

Experiment records and per-run records may be distinct commit domains. Retain
stable reference identities. Recovery must handle interruption between commits.
Do not claim a transaction across separate stores or the artifact archive.
`raes_operations/run_artifacts.py::RunMaterializationArchive` publishes protected
immutable materializations. That write is outside the operation-store
transaction. It is not an experiment ledger.

`control_plane_recovery.py`, `operation_invocation_ledger.py` and linked
reconciliation already distinguish absent, applied and indeterminate effects.
Reopening a store, process exit, timeout, cancellation acceptance, a successful
stop request and lease expiry do not prove cessation. Unknown effects retain
reservations. Resume first reconciles authorized work. Continuation needs the
existing supported boundary and policy. It does not grant unconditional
checkpoint continuation, effect retry or replacement.

Use the entry's `AdmittedExecutionControlModel` and referenced
`TrialCleanupPlanModel`, preserving triggers, dependency order, owned resource
boundaries, initial-state probes and obligation budgets. Attempt repetition is
owned by `TrialCleanupPlanModel.retry_policy`. Transport replay, native workflow
retry and fresh-trial replacement are different decisions.
Keep whole-attempt deadlines separate from operation, cleanup and observation
budgets and from authored scenario time. Convert durations explicitly within
`require_budget_ms()` bounds. Recovery must not reset or widen the deadline.
`LocalExecutionAdapter` retains occupied physical slots until callbacks exit and
provides separate control/store capacity. Do not add a timeout thread pool or
consume all control capacity with blocked trial effects.
Keep cancellation reachable while a backend blocks.
Never hold the mutation permit across the whole trial.

Preserve execution observations **before cleanup** in `TrialUnitResult`.
Execution failure, capture/evidence failure and cleanup failure remain distinct,
including when two fail together. Successful apply or an operation receipt is
not authored workflow completion or task evidence satisfaction. Cleanup is owed
under its admitted triggers after success, partial failure, timeout,
cancellation and abort. A missing result is not successful cleanup.

Reuse `validate_trial_unit_result()`, `validate_trial_cleanup_receipt()` and
`validate_batch_execution_receipt()` for structural accounting. They do not
prove evidence content or clean state. Trusted resolvers/probes must establish
cessation and the required state across all affected boundaries before reuse.
Failed, unsupported, partial or unverified cleanup keeps the target unavailable
for dependent work. No fabricated receipt, unconditional destroy in `finally`,
implicit rollback or reuse based only on a successful trial outcome.

## Replacement and archival authority

Use `raes_processor/trial_compiler/replacement.py::compile_replacement_trial()`
with exact original inputs and complete committed `previous_allocations`.
Atomically claim each root slot's next ordinal and retain the child plan and
archival successor decision before child dispatch. Duplicate notifications and
lost commit replies must return the same decision and debit the budget once.
The pure compiler does not supply that atomic claim.

The admitted policy selects archival `failed`/`invalidated` dispositions, not
arbitrary operation failures or trial cancellation/timeouts. Do not invent a
replacement trigger or select the best successful descendant. Preserve original
attempts and run versions through `trial_replacement_archive.py`.
Supersession does not overwrite them. Current replacement admission requires
reusable-state cleanup across the full scope. It refuses `fresh-range-required`.
A new identifier or target does not bypass that rule.
Replacement re-enters ordinary realization,
authorization and live admission with fresh run-local state and compiler-owned
child identity. Do not copy failed snapshots, histories or resolved secrets.

`ExperimentRunModel` and `TrialRunProvenanceModel` own the archive shapes.
`validate_admitted_trial_run()` and `reconcile_admitted_trial_plan()` check
allocation/attempt/cleanup joins. Use `validate_experiment_run_against_task()`
and `ExperimentRunEvidenceInputs` to check content-backed task evidence.
Keep typed realized selections and participant bindings in archive records.
Shape checks and reference existence cannot award scientific validity.
Nor can backend success or a cleanup receipt. Retain failed runs.
Keep their retention separate from eligible study membership.
Preserve allocation counting, missing-data rules and evidence requirements.

## Cross-cutting security and configuration gates

| Layer | Canonical incumbent and required fit |
| --- | --- |
| Composition and installed shape | Reuse `ControlPlaneConfiguration`, `control_plane_composition.py`, `control_plane_profiles.py`, `registry.py::RuntimeTarget` and `registry_target_validation.py`. Keep typed settings and explicit run scope. Match installed components to manifests and check call shapes. Keep profile/store capability checks. Inject targets, trial adapters and scoped resolvers explicitly. No backend-name switches, ambient discovery, method-probing fallback or hidden optional-service construction. Durable resume needs an admitted durable composition. Local embedding still needs no service. |
| Authentication and authorization | Reuse `control_plane_admission.py`, `control_plane_plan_authorization.py` and `control_plane_operation_context.py`. Keep actor, exact plan, target/run and scoped idempotency authority. Dispatch, cancellation, cleanup, evidence access and replacement each need permission. P0 remains a trusted embedder boundary. HTTP retains `ControlPlaneSecurityConfig.strict_defaults()` and `control_plane_api/_auth.py`. Keep route seals, role/subject checks and denial audit. Keep request/offload bounds and no-store responses. P2 remains an administrative surface. Plan/entry IDs, seals, task tokens and receipts are not credentials. Do not enlarge the HTTP limit to match the 32 MiB plan parser bound. |
| Secret references and environment shapes | Reuse `raes_contracts/secret_references.py` and participant configuration owners. Keep `runtime_fact_binding_policy.py`, `runtime_fact_dispatch.py`, participant crossing and `participant_flow_sink.py`. They enforce authorized run-local sinks, provenance, audience and freshness. Reuse `raes/runtime_environment.py`, `runtime_configuration.py`, `runtime_generated_value.py` and semantic validators. They require unique names and sensitivity/provenance. A literal and `value_from` cannot coexist. Generated values cannot claim `operator_secret`. Keep references opaque until authorized backend delivery. No flattened configuration/env dictionary, copied credential cache, shared secret mount or ambient credential lookup. |
| Backend input, results and evidence | Reuse `backend_input_contracts.py`, `backend_calls.py` and snapshot/transition/result validators. Keep workflow/participant/time validators and `OperationEvidenceResolver`. Check isolated input and untrusted results against the trusted predecessor. Include partial/failed and late results. Keep changed-address accounting and the single observation owner. `backend_account_credentials.py` sanitizes its account-specific surface. It is not a general participant-payload sanitizer. Resolve content through installed trusted owners, never arbitrary backend URLs or paths. |
| Host and storage exposure | Reuse `control_plane_store_paths.py`, store codecs/migrations and `control_plane_store_lease.py`. Keep backend naming/containment. Preserve safe owned paths, private directories/files and symlink/hard-link checks. Bound decoding and check ownership. PostgreSQL keeps its typed `PostgreSQLStoreConfiguration` and secret password carrier. Keep explicit bootstrap, TLS choice and bounded calls if that established store is selected. Native processes use controlled argv/environment and private run-local resources. No shell interpolation, token in argv or broad environment inheritance. Keep hostile code outside trusted workers. Local locks do not prove isolation across hosts. Add no listener, service or data destination. |
| Public errors and diagnostics | Reuse `AdmittedTrialPlanIngressError`, compiler `CompilationFailure`/safe result diagnostics, shared `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()` and `backend_result_diagnostics.py`. HTTP keeps `_responses.py::_conflict_detail()` and the redacted 422/500 handlers. No parallel exception hierarchy. Do not expose validator inputs, owner/backend exception text, cause chains, host paths, commands, stdout/stderr, resolved credentials or model/prompt payloads through errors. |
| Audit and observability | Reuse `AuditEvent`, `control_plane_audit.py` and module loggers. Keep scoped operation/attempt correlation. Audit detail keys are closed per action. Arbitrary plan/run/attempt keys currently fail `require_audit_event_fields()`. Extend that canonical validator and its carriers when needed. Do not add a free-form logger/store. Preserve actor-bound atomic terminal/snapshot/audit commits. Keep protected configuration/evidence artifacts separate from general telemetry. ADR-066 and `raes/observability_plane_semantics.py` separate three planes. These are operational progress, participant observations and scientific evidence. Logs and engine history are not execution truth. |

## Extensibility, repository gates and acceptance boundary

Keep backend/allocator selection, scoped durable composition, evidence resolvers,
deployment capacity caps and finite supervision budgets explicit inputs to the
existing seams. Treatment semantics stay in versioned admitted profiles, not
runtime model/prompt keys or a generic policy bag. A new participant manifest or
backend should change those inputs, not require editing the experiment loop.
Preserve serial default. Parallel execution needs the embedded isolation proof
and current live leases. `AllocatorGrant.effective_parallelism` cannot exceed
the admitted ceiling or actual owned capacity. Recovery must re-establish
ownership. Expired proof references cannot supply it.

The repository-level `tools/policy/adr_policy.yaml` currently allows runtime
imports from processor `compiler`, `models` and `planner` only. Direct imports
of `trial_realization`, `trial_scheduler` or `trial_compiler` fail that gate.
Keep pure processor ownership and neutral contract carriers. Any needed public
import change must be narrow and explicit under ADR-036. No dynamic import,
copied compiler, broad allowlist relaxation or live coordinator in
`raes_operations`, which forbids runtime/processor imports.

Retain `specs/authority/authority-boundary.yaml`, `.ground-control.yaml`,
`.gc/plan-rules.md`, `tools/check_repo_policy.py`, `tools/verification_plan.py`,
`noxfile.py`, `.pre-commit-config.yaml` and `.github/workflows/ci.yml`.
Keep source modules within the existing 500-line limit. Published schemas under
`contracts/schemas/` remain normative under ADR-009/061. A portable contract
change needs its publication entry/change hash and `schema_bundle()` parity.
Keep semantic invariants, fixtures and consumer admission aligned.
Internal durable record changes need explicit codecs, migrations and scope.
Check store capabilities. An unversioned JSON bag does not avoid these duties.
Do not invent a requirement UID for this requirement-free issue.
Do not edit release-owned versions and changelogs.

Behavioral incumbents include `test_issue_1660_runtime_lifetime.py`,
`test_issue_1627_trial_unit.py`, `test_issue_1628_trial_control_admission.py`,
`test_issue_1666_factorial_compilation.py`, `test_issue_1666_factorial_replay.py`,
`test_sce_006_batch_scheduler.py`, `test_sce_006_cleanup_contracts.py`,
`test_issue_1396_trial_replacement.py` and #1362 lost-ack/reconciliation tests.
Public runtime integration evidence must cross model/prompt choices with node
presence/configuration, and observe actual application through the same owner.
Exercise cancellation and interruption at decision/effect/commit boundaries.
Cover concurrent/duplicate delivery and changed input on resume.
Cover cleanup refusal or missing evidence. Cover replacement exhaustion while
retaining originals. Protocol fakes
and compiler-only tests do not establish end-to-end runtime behavior. Run only
targeted checks locally; full, integration, fuzz and completion suites run in CI.

Non-goals include new factorial selection or scoring rules and concrete backends.
They include native resource discovery/management and automatic mixed-backend
support. Do not add a second controller/store/queue framework or new HTTP/CLI
surfaces. New distributed deployment is outside scope. So are universal rollback,
unconditional continuation and exactly-once external-effect claims.
This preflight changes guidance only.
