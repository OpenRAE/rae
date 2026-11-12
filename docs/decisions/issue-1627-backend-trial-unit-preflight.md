# Issue #1627 — Backend trial unit preflight

Date: 2026-10-25. The supplied issue title and body are the delivery contract;
there is no formal requirement scope. This is architecture guidance, not an
implementation plan. Native GitHub blocked-by relationships retain authority
over the issue's dependencies; this inspection does not certify their closure.

## Decision and ownership

[ADR-113](adrs/adr-113-reusable-execution-machinery.md) and
[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) already settle
the architecture. No new ADR is needed. Define one backend-facing trial unit
that composes the existing admitted-entry, configuration, execution, evidence
and cleanup contracts. Keep RAE's semantic execution authority and the backend's
native effect responsibility separate.

`raes_processor/trial_realization.py::realize_admitted_trial_entry()` produces
an instantiated scenario and three processor plans. It does not execute or
complete a trial. Reuse that result rather than creating another compiler,
planner or scenario interpreter. `RuntimeManager`/`RuntimeControlPlane` retain
live ordering, participant/time/workflow rules, result admission and supervision.
Backend implementations supply concrete realization, readiness, observations,
credential delivery and native cleanup. An external allocator supplies placement
and live isolation, without acquiring scenario interpretation authority.

Protocol declarations belong in `raes_backend_protocols`; shared request/result
values belong in `raes_contracts`. Use typed neutral carriers, composing existing
children rather than copying their fields. `RuntimeTarget` is the injected
composition dependency, not a serialized request field or a protocol-layer
import. Neither `TrialRealization`, `TrialRealizationInputs` nor processor
`ExecutionPlan` is a neutral public backend DTO.

The import gate in `tools/policy/adr_policy.yaml` currently permits runtime
imports from processor `compiler`, `models` and `planner` only. A direct runtime
import of `trial_realization` fails that gate. Keep pure realization upstream
and pass its neutral projections across the boundary; any necessary public
import allowance must be narrow, explicit and consistent with ADR-036. Do not
use a dynamic import, duplicate realization, broaden the entire allowlist, or
put live composition in `raes_operations` (which forbids runtime/processor
imports).

## Trial contract boundaries

- Bind the unit to the reconstructed complete plan and its exact entry, seals,
  preallocated `run_id`, selected backend/participant manifests and realization
  envelope. Bind executable projections to that same target/run/instantiation.
  Set `ControlPlaneConfiguration.run_scope` to `run:<entry.run_id>` explicitly;
  its `run:default` fallback is not an admitted trial identity.
  A caller-supplied entry, digest or target name alone supplies no authority.
- Carry the sealed `ParticipantConfigurationResultModel` values returned by
  realization, with their participant, owner, manifest and configuration joins.
  [The #1626 note](issue-1626-trial-participant-bindings-preflight.md) explains
  why execution must not rerun defaults, owner normalization or alias resolution.
  A retained configuration digest proves identity, not runtime application.
  Refuse an unsupported configured participant before effects; do not silently
  drop configurations or synthesize them for unbound legacy participants.
- Reuse `AdmittedExecutionControlModel` and the entry's referenced
  `TrialCleanupPlanModel`. Resolve and check that reference before dispatch.
  Preserve whole-attempt timeout and cancellation dispositions, dependency
  ordering, owned resource boundaries, clean-state probes and obligation budgets.
  Cleanup retry policy remains in the cleanup plan; do not duplicate it in the
  trial request or infer effect retry permission from idempotency.
- Return the existing operation receipts/references, a validated runtime
  snapshot, typed evidence and `TrialCleanupReceiptModel` with its evidence.
  Specify which execution point the returned snapshot represents. Preserve
  trial observations before teardown; a post-cleanup snapshot cannot silently
  replace them. An instantiated SDL digest and a live runtime snapshot are
  different artifacts. A successful apply/start acknowledgement does not prove
  authored workflow completion, evaluation success or evidence satisfaction.
- Keep plan, entry, run, execution attempt, operation, invocation and engine
  delivery identities distinct. `TrialOutcome`, operation state and cleanup
  status remain separate facts. Honest partial, unsupported or unverified
  cleanup must remain representable even when trial execution succeeded.
  Join receipts through `validate_trial_cleanup_receipt()` and, when a batch
  receipt is produced, `validate_batch_execution_receipt()`. Reference strings
  alone do not prove that evidence exists, is accessible or matches this attempt.

The current `OperationKind` has no trial kind, and
`require_backend_execution_policy_admission()` accepts only the exact native
provisioning/orchestration/evaluation plan kinds. A local trial composition can
reuse those operations; it must not disguise a trial as provisioning or use an
arbitrary artifact reference to bypass command-owner validation. If a new live
operation kind is needed, evolve its closed consumers and governed contracts
together. Do not introduce a competing lifecycle beside `BackendOperationProvider`.

## Cross-cutting gates to reuse

Package paths in this table start at `implementations/python/packages/`;
unqualified runtime files belong to `raes_runtime`.

| Layer | Canonical incumbent and required fit |
| --- | --- |
| External ingress and integrity | `raes_contracts/admitted_trial_plan_ingress.py`: bytes use `parse_admitted_trial_plan_json()`; caller-held models use `revalidate_admitted_trial_plan()`. Preserve strict bounded JSON, duplicate-member/non-finite-number rejection, complete-plan seals and nested joins. Use `ContractModel`, existing strict primitives, canonical digest helpers and `runtime_value_limits.py`; bound new aggregate collections and evidence before copying/hashing. Closed shapes alone do not enforce strict scalar types or total size. No detached-entry parser or second validator. |
| Manifest, capability and configuration shape | `RuntimeTarget.__post_init__`, registry shape/signature checks, backend manifests/profiles and capability admission own installed component checks. An added optional protocol must keep explicit declaration, installed component and call shape consistent; preserve existing targets that do not declare it. No method-discovery fallback or backend-name switch. `ControlPlaneConfiguration`, `control_plane_composition.py` and `control_plane_profiles.py` retain scoped resolvers, participant control, information-state and store/profile compatibility checks. A component being callable proves neither willingness nor conformance. |
| Authentication, authorization and disclosure | P0 retains the trusted embedder boundary; no new HTTP/auth surface is required. When composed through the control plane, reuse `control_plane_admission.py`, `control_plane_plan_authorization.py`, `control_plane_operation_context.py` and the current actor/target/run context. Dispatch, cancellation, cleanup and evidence access each need their appropriate authority. Participant crossing, information-state and final-sink rules still apply to disclosures. If a later transport is added, retain `ControlPlaneSecurityConfig.strict_defaults()`, `_auth.py`, route authority, request/offload limits, denial audit and no-store responses. A seal, receipt or task token is never a credential. |
| Secrets and environment binding | `SecretReferenceId`, participant configuration value kinds and manifest-owner validation retain non-sensitive reference identities. Secret resolution belongs at the authorized backend sink. `runtime_fact_binding_policy.py`/`runtime_fact_dispatch.py` enforce run-local provenance, freshness and sink permission. `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py` and their semantic validators retain unique environment names, sensitivity/provenance and literal/`value_from` exclusivity; generated values cannot claim `operator_secret`. Do not turn participant target IDs into environment names or flatten configurations into arbitrary env dictionaries. No ambient env/credential lookup is added to pure contracts. |
| Backend input, result and credential egress | Reuse `backend_input_contracts.py`, `backend_calls.py`, `backend_call_contracts.py`, `backend_apply_results.py`, snapshot/transition diagnostics and native workflow/evaluation/participant/time validators. Validate isolated inputs and results against the trusted predecessor, including failed/partial and late results. Retain realization authority, changed-address accounting and `backend_account_credentials.py`'s closed value-free projections. That account-specific sanitizer does not automatically sanitize arbitrary participant data: the new aggregate must carry only approved outputs, never backend details or a full configuration dump. |
| Evidence and archival joins | Reuse `OperationEvidenceResolver`, existing capture demands and evidence satisfaction/content validators, `ExperimentEvidenceRecordModel`, redaction/loss disclosures and content-bound references. Resolve evidence through its trusted owner; do not fetch arbitrary backend URLs or accept self-attested strings as proof. Operational progress, participant observations and experimental evidence keep ADR-066's separate planes; `raes/observability_plane_semantics.py` owns registered carrier classification. `ExperimentRunModel`, `TrialRunProvenanceModel` and `validate_admitted_trial_run()` remain the archival authority. The trial result is a handoff to that authority, not a second run record or scoring system. |
| Persistence and observability | Reuse `ControlPlaneStore`/atomic commit adapters, scoped idempotency, revision/history checks, invocation claims, owner generations, durability/reconciliation and `AuditEvent`. Backend calls stay outside short state mutations; only the runtime publishes validated state. Reuse operation/attempt correlation and module loggers. Logs, backend history and an execution result do not replace the ledger. `raes_operations/run_artifacts.py::RunMaterializationArchive` retains only its established materialization archive role; no new trial database, secret archive or callback-owned state writer. |
| Safe errors | Reuse `AdmittedTrialPlanIngressError`, `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()` and `backend_result_diagnostics.py`; refusals and uncertainty remain typed facts. HTTP compositions retain `_responses.py::_conflict_detail()` and existing redacted 422/500 handlers. Do not expose validator input, owner/native exception text, chained tracebacks, host paths, argv or stdout/stderr through result/error/audit/log fields. No parallel exception hierarchy or logging framework. |
| Host/OS boundary | This in-process composition needs no subprocess, listener, daemon discovery or credential loader. Concrete backends retain containment and native lifecycle. Reuse backend naming and store-path hardening. Any backend process binding must use controlled arguments/environment, private owned paths and bounded calls; no shell interpolation, resolved token in argv, broad environment inheritance, shared secret cache/mount or execution of hostile trial code inside trusted runtime workers. RAES must not discover, adopt or destroy native resources itself. |

## Failure, cleanup and extension guardrails

`LocalExecutionAdapter` and `OperationSupervisionConfiguration` already provide
bounded AnyIO execution and separate effect/control/store capacity. A blocked
effect retains its occupied slot after caller timeout. Do not add another
thread-pool timeout loop or claim that cancelling a future stopped the backend.
Deployment budgets may narrow admitted bounds, never widen them. Convert
seconds to milliseconds explicitly within `require_budget_ms()` limits.
Duplicate delivery/recovery must not reset a budget or redispatch an effect;
reuse scoped idempotency and reconciliation. An authorized new attempt gets a
distinct attempt identity while retaining the admitted run identity.
Unknown effects retain reservations until existing fencing/cessation and result
release gates are satisfied. Preserve partial resource inventory for cleanup;
returning the old snapshot on an error does not prove that nothing was created.

Cleanup remains owed after success, partial failure, timeout, cancellation and
abort according to the admitted triggers. Its bounded control capacity must
remain available after the execution budget expires. Cleanup failure must not
erase execution evidence, and execution failure must not suppress cleanup
evidence. No fabricated successful receipt, automatic retry/reset, unconditional
destroy in `finally`, or resource reuse while cessation/clean state is unknown.
The existing receipt validators check structural joins and obligation coverage;
backend probes and trusted evidence resolution establish actual cleanup.

The extension seam is an explicitly injected `RuntimeTarget`, installed scoped
resolvers, sealed configurations and admitted execution/cleanup policy. Keep
backend selection and finite supervision budgets as parameters. Another backend
or participant revision should change those inputs, not the trial coordinator.
The existing `trial_scheduler.py`/`trial_coordinate_order.py` own canonical batch
dispatch and `AllocatorGrant` records effective live isolation; a trial unit
does not select its own batch order or parallelism. Local claims are not
multi-host leases. Mixed-composition entries currently fail closed in the
single-entry realizer; do not silently fall back to a single backend.

## Repository gates and non-goals

Retain `.ground-control.yaml`, `.gc/plan-rules.md`, ADR-036 import policy,
`specs/authority/authority-boundary.yaml`, `tools/check_repo_policy.py`, schema
publication/coverage/parity checks, `tools/verification_plan.py`, `noxfile.py`
and `.github/workflows/ci.yml`. Published schemas are normative under ADR-009/061.
Any new portable carrier or changed schema needs its governed publication entry,
change ledger/content hash, bundled `schema_bundle()` parity and consumer
admission; do not edit generated output alone. Do not invent a requirement UID
for this requirement-free issue; retain the tooling's existing scope resolution.

Behavioral evidence should extend the existing trial-realization, #1626 binding,
SCE-006 cleanup/batch, runtime-contract-boundary and #1362 supervision/lost-ack/
reconciliation tests. Exercise wrong joins and tampered models before effects,
unsupported capability, configuration handoff, duplicate delivery, partial
effects, timeout/cancel races, unavailable cleanup and secret-free failures.
Use only relevant local cases; full, integration, fuzz and completion suites
belong to CI. Stubs and installed conformance prove portable behavior, not live
backend interoperability or physical isolation.

Non-goals include concrete backends, plugin discovery, native resource management,
new HTTP/CLI routes, and distributed deployment.
No new queue, store, scheduler, selection policy, run allocator, or scoring system is needed.
The contract adds no automatic mixed-backend support, universal rollback, or exactly-once external-effect claim.
This preflight defines architecture guidance only.
