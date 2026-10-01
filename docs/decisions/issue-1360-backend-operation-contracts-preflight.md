# Issue #1360 — Backend operation and supervision contracts preflight

Date: 2026-09-24. Scope: API-402 and supplied issue #1360; prerequisite #1348.
This is architecture guidance, not an implementation plan or a new contract.

The accepted [#1348 decision](issue-1348-operation-lifecycle.md) and
[supervision semantics S1–S6](../../specs/formal/runtime-control-plane/supervision.md)
already settle lifecycle meaning. Retain those authorities and ADR-104; no new
ADR is needed. The [earlier preflight](issue-1348-operation-lifecycle-preflight.md)
maps runtime integration risks. This note closes the publication-specific gaps.
Python paths below are relative to `implementations/python/packages/`.

## API-402 boundary: compose the existing live contracts

API-402's existing implementation and ACTIVE status do not establish delivery
of #1360's additional supervision carriers. Preserve these semantic owners:

| Surface | Canonical incumbent and boundary |
| --- | --- |
| Submission | `contracts/realization_plans.py` in `raes_contracts` owns `ProvisioningPlanModel`, `OrchestrationPlanModel` and `EvaluationPlanModel`; `_operation_routes.py` accepts these today. Reuse admitted plan identity and payloads inside any new backend request. An instantiation request is not an execution request, and authenticated submission does not replace planner authorization. |
| Live operation | `operation_lifecycle.py`, receipt/status models and their `control-plane/operation-{receipt,status}-v1.json` schemas own operation identity and state. Backend acknowledgement/progress are evidence for this authority, not replacement status models. |
| Results and history | Existing `workflow-result-envelope-v1`, `evaluation-result-envelope-v1`, and their separate `*-history-event-stream-v1` schemas remain authoritative. `contracts/execution_state.py`, `workflow_result_contracts.py` and `evaluation_result_contracts.py` preserve compiled result/execution-contract validation, workflow causality, evaluator chronology and final-state/history agreement. Supervision history must not become workflow step history or evaluator evidence. |
| Live snapshot | `contracts/realization_plans.py:RuntimeSnapshotEnvelopeModel`, `runtime_state.py` and `snapshots/runtime-snapshot-v1.json` retain the portable state projection. A snapshot is neither a continuation checkpoint nor proof of external cessation. |
| Archival provenance | ADR-065's `experiment-run-v1` remains the archival join point for results, evidence and provenance references. Do not add another run-record root, use an archive as a mutable operation journal, or require an experiment wrapper for ordinary live execution. Operational persistence does not turn a live carrier into archival provenance. |

Schema paths above are under `contracts/schemas/`. Keep the formal
[workflow](../../specs/formal/runtime-contracts/workflow-results.md) and
[evaluator](../../specs/formal/runtime-contracts/evaluator-results.md) contracts,
`contracts/README.md` and `docs/explain/sdl/runtime-architecture.md` aligned when
publication changes their public boundary. Some overview implementation mappings
still name the older processor ownership; use the current `raes_runtime` owners
above rather than introducing validation in the processor to match stale paths.

## Existing contracts and the gaps to publish

`raes_contracts/operation_lifecycle.py` owns operation kinds, immutable admission
context, legal state transitions and canonical terminal diagnostics.
`contracts/operation_carriers.py` in that package owns closed receipt/status wire
models; `runtime_state.py` owns their in-process counterparts. Reuse these
identities and meanings rather than introducing a competing backend lifecycle.
Domain (provisioning/orchestration/evaluation) is not operation kind.

The current carriers do **not** supply the whole #1360 protocol:

- `OperationAdmissionContext` lacks an explicit binding to selected supervision
  requirements, backend execution generation and control-request identity.
- `raes_backend_protocols/protocols.py` exposes synchronous `ApplyResult` methods.
  A returned failure with the predecessor snapshot does not establish absent
  effects. Wrapping that result cannot manufacture cessation or interruption.
- `recovery_observation.py` provides unversioned Python dataclasses and only
  absent/applied/indeterminate classifications. Applied requires a snapshot;
  other classifications forbid one. There is no known-partial or cessation
  carrier. Its operation/request checks do not supply every new correlation.
- Manifest `RecoveryObservationCapabilities` selects operation kinds only;
  method presence and that declaration do not establish contextual willingness,
  cancellation support, continuation, or satisfaction of requested guarantees.
- Receipt and status share `OPERATION_SCHEMA_VERSION = runtime-operation/v1`.
  Store codecs and HTTP projections explicitly reconstruct their fields; an
  added Python field alone can disappear at those boundaries.

Publish only the missing portable facts, with one semantic owner for each.
Requests, acknowledgements, progress, refusal, cancellation dispositions,
outcomes and reconciliation must have closed, versioned shapes and documented
cross-message invariants. JSON Schema covers structural constraints; shared
contract validators cover context, identity and evidence joins. Publish those
semantic obligations through the existing `schema_invariants.py` annotation
conventions where applicable, not independent validators in every transport.
Annotations identify obligations; a generic JSON Schema validator does not
execute them. Publish language-neutral rules and cross-message vectors, with
Python validators as reference bindings rather than the only definition.

The wire boundary is JSON data, not serialized Python objects, callbacks,
exceptions, futures, native handles or injected services. Reuse
`raes_contracts/canonical.py` for RFC 8785 commitments and
`control_plane_operation_context.py` for their authorized, value-free projection;
do not hash `repr()`, ad hoc JSON or resolved credentials. Specify omission/null,
defaults, ordering and numeric bounds consistently across schema and Python,
including finite numbers and interoperable integer limits for committed data.
`ContractModel` forbids extra fields but does not make every field strict or
bounded. Python coercion and `jsonable_fallback()` comparison markers must not
turn invalid wire inputs into accepted protocol facts.

## Meaning and ownership guardrails

**Separate the facts.** Capability, current willingness, acceptance, dispatch,
progress, cancellation acceptance, cessation, effect knowledge and runtime
terminal publication are different facts. Preserve the six existing operation
states; do not add `PARTIAL`, `TIMED_OUT`, `REFUSED` or `CANCELLING` states.
Backend completion is evidence submitted to the runtime, not authority to
commit a runtime terminal state. Progress cannot establish success, renew a
deadline, discharge quarantine or substitute for experiment evidence. Specify
ordering and duplicate/stale-message handling within an execution generation;
timestamps alone cannot order concurrent control and completion events.

**Bind the whole exchange.** Preserve original actor, authorization scope,
target/run, operation kind, request commitment and parent linkage. Correlate
backend invocation, execution generation, conflicting-effect scope, baseline
snapshot revision, exact admitted requirements/context and every response.
A supervisory request has its own actor and scoped idempotency identity;
it never replaces the original actor. Reject mismatched responses even when
each object independently validates. Operation, control request, backend job,
execution attempt and trial/run identities are not interchangeable.
Keep backend-native locators behind a bounded, non-authorizing correlation
boundary; identifiers are neither credentials nor executable commands.

**Name what fencing proves.** Runtime generation/revision checks reject stale
state publication. A remote fencing or cessation claim must identify its scope
and supporting backend guarantee/evidence; a lease, CAS token, timeout, PID,
cancelled future or killed local process supplies no such proof. Default effect
exclusion is target/run-wide unless the admitted contract establishes narrower
independence. Refusal and progress must also remain correlated to that scope.

**Represent uncertainty without upgrading evidence.** Keep effect knowledge
(absent, complete, known partial, unknown), cessation and satisfaction of all
admitted result/release gates independent. Known partial effects require
validated residual state/scope; unknown remainder or unproved cessation requires
indeterminacy and retained exclusion. An exception, unsafe snapshot, or
`success=false` is not evidence of no effect. Preserve ASR-532 predecessor
isolation. Reconciliation is bounded observation/classification, never replay.
An immutable indeterminate parent may gain separately authorized linked
resolution evidence, not a rewritten terminal outcome. Administrative snapshot
acceptance is not cessation, clean-state evidence or permission to retry.

**Contextual support is an optional protocol seam.** Bind support and willingness
to operation kind, exact selected requirements, backend contract version and
effective execution context. Preserve the existing manifest/installed-component
agreement; reject an unsupported required guarantee before effects, and recheck
after waiting. Missing support must not become best effort. The extensibility
parameter belongs here, not in backend-name branches or a global
`supports_cancel` Boolean. New cooperative interruption, observation or future
physical-OT capabilities should be selectable without changing P0 defaults or
requiring every backend to implement them. Publish invocation, concurrency,
side-effect and failure semantics so backend authors can implement the protocol
without owning scenario scheduling, retries, terminal commits or a second runtime.

Reuse authored workflow/time/trial authorities: `WorkflowExecutionContract`,
`ExecutionRetryPolicyModel`, `TrialExecutionAuthorityModel`,
`AdmittedExecutionControlModel`, cleanup plan/receipt models and
`require_cleanup_plan_capability()`. Transport duplicates do not create attempts;
recovery does not allocate trials. Continuation requires established authority
and a compatible boundary; do not invent a general checkpoint format here.
Operational stage budgets remain positive, finite apparatus bounds with explicit
origins; duplicate messages do not renew them. Reuse `control_plane_timeouts.py`
and the shared time validators. Portable UTC timestamps and authored semantic
clock/domain/segment identity are not restartable monotonic deadlines.

## Cross-cutting layers the design must pass

| Layer and canonical incumbents | Required treatment |
| --- | --- |
| Source and admitted plans: `raes` models/validators, `raes_processor/compiler`, workflow/time/trial contracts | Reference or carry admitted requirements without reinterpreting authored source. Reuse existing policy defaults and cross-object validators; do not hide execution policy in metadata or transport settings. Ordinary P0 work needs no trial or participant wrapper. |
| Configuration and capability shape: `ControlPlaneOptions`, `control_plane_configuration.py`, `RuntimeTarget`/`RuntimeTargetComponents` in `registry.py`, `registry_target_validation.py`, `raes_backend_protocols/{capabilities,manifest,backend_manifest,capability_admission}.py` | Extend closed models, manifest conversion and signature/presence checks together wherever integration is touched. A protocol declaration must not advertise an installed implementation. Registry probing checks call shape without invoking effects. Retain operation-kind restrictions, including the distinction between observation and administrative resolution. |
| Profile/version admission: `raes_contracts/{manifest_authority,backend_profiles,versions}.py`, `contracts/profiles/backend/`, `raes_runtime/control_plane_profiles.py` | Register contract IDs in the correct producer/consumer allowlists. Backend profiles enumerate required contracts; P0–P3 describe runtime/store/deployment guarantees. They are different axes. Preserve P1/P2 optional observation with indeterminate fallback; it cannot satisfy a request explicitly requiring provable recovery. P3 stays unavailable. Profile loading keeps grammar and payload-identity checks before path use. |
| Authentication/disclosure: `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `ControlPlaneIdentity`, `control_plane_plan_authorization.py`, `operation_admission_context()` | Derive actors from trusted identity, not request assertions. Reauthorize status, cancellation and reconciliation for the exact target/run/subject; preserve operator-only administrative resolution. A receipt, backend handle or fencing value grants no access. Retain hard failure for invalid bearer credentials and explicit proxy trust. Direct calls retain the trusted embedder boundary. |
| Request/value admission: `RequestSizeLimitMiddleware`, `_ControlPlaneCallExecutor`, `ContractModel`, `raes_contracts/runtime_value_limits.py`, `backend_input_contracts.py`, `backend_call_contracts.py` | Bound identifiers, collections, nesting, diagnostics and progress/evidence volume before copying, hashing or publication. Closed models alone do not imply strict booleans/numbers or finite budgets. Use existing strict primitives and calendar validation. Bound supervisory traffic independently of effect traffic; no unbounded iterator or acknowledged-but-discarded control request. |
| Secrets/environment: `SecretReferenceId`, `runtime_fact_dispatch.py`, `runtime_fact_binding_policy.py`, `raes/runtime_environment.py`, planner `stateful_admission.py` | Carry authorized references rather than resolved credentials in durable/public context. Preserve visibility/freshness and closed generated-environment projections. `value_from` excludes literal values and `operator_secret`; redacted/operator-secret values cannot contain raw material. Rebinding inputs reapplies the existing gates. `control_plane_operation_context.py` and `control_plane_admission.py` keep credential-sensitive retry proof ephemeral; a public commitment after restart is insufficient. |
| Backend result admission: `backend_calls.py`, `_validated_backend_result()`, `backend_result_diagnostics.py`, `result_contracts.py`, [result-admission spec](../../specs/formal/runtime-contracts/backend-result-admission.md) | Use isolated predecessors, native domain/workflow/participant/time validation, realization authority, changed-address accounting and credential egress checks for partial, recovery and late results too. Typed backend evidence remains untrusted. Known effects do not bypass final disclosure/release gates. |
| Persistence: `RuntimeMutationAuthority`, `RuntimeDurabilityMixin`, `ControlPlaneStoreCommitAdapter`, `control_plane_store_records.py`, `control_plane_store_record_migration.py`, `control_plane_store_paths.py` | Retain one writer, atomic claims and snapshot/terminal/audit commit, revision CAS, immutable terminal history and strict codecs. Unknown store acknowledgement requires authoritative readback/poisoning, distinct from unknown external effects. Preserve private paths, lease-before-inspection and close-before-lease-release. No new supervision store, callback-owned commit, or database transaction spanning backend execution. |
| Errors/observability: `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, canonical terminal diagnostics, `control_plane_api/_responses.py`, `_operation_routes.py`, `AuditEvent`, `control_plane_health.py` | Refusal and uncertainty are typed protocol facts with stable safe diagnostics, not a parallel exception hierarchy. Preserve redacted 422/500 and conflict envelopes. Reject input echoes, raw exception text, native output, credentials and sensitive locators in errors/audit/progress. Reuse bounded actor-bound audit and module loggers; keep health, operational progress, participant observations and archival evidence distinct. |
| Host/process and delivery: existing backend drivers, embedder deployment, `raes_contracts/corpus.py`, Python package configuration | Publishing this protocol needs no shell, port, process manager or new credential loader. Examples must not place tokens in argv, accept request-supplied executable paths, or dump/inherit broad environments. TLS/proxy and process lifecycle remain deployment duties. Load schemas/profiles through the packaged corpus seam, not checkout-relative path heuristics. |

These are obligations for the eventual implementation, not claims that current
runtime code already provides bounded supervision. In particular, current
external-call locking/drain and exception-to-failed-result behavior remain the
gaps documented by #1348; publishing models does not fix them.
For claim-bearing observability carriers, reuse ADR-066 and
`raes/observability_plane_semantics.py` when publishing `x-raes-plane`:
the classifier rejects unregistered contract IDs. Do not infer the plane from
an `evidence` field name or copy an archival annotation onto operational progress.

## Publication, compatibility and traceability

Follow ADR-009/061 and
[the evolution policy](../../specs/evolution/versioning-deprecation-and-migration.md).
Normative schemas live in `contracts/schemas/`; `schema_bundle()` and
`contracts/bundle_runtime.py` must generate identical artifacts. Keep
`tools/generate_contract_schemas.py` routing, public contract exports
(`contracts/__init__.py`/`_exports.py`), `versions.py`, manifests, profiles,
fixtures and public backend/API documentation consistent. Reuse
`corpus.py` and the existing wheel/sdist corpus inclusion in
`implementations/python/pyproject.toml`; backend owners must receive the
contract without a source checkout or a runtime implementation dependency.

The publication manifest is now a **v2 directory index**. Update each affected
`contracts/schema-publication/entries/<contract-id>.json` with its content hash
and `last_change`; use independent `tombstones/` records for removals. Do not
restore the older monolithic ledger described by some historical notes.

Choose lineage/discriminators under the existing stability policy and document
producer/consumer direction, semantic as well as structural compatibility, and
source/target migration rules. Optional fields and enum additions can break old
closed readers. Audit receipt/status DTOs, in-process conversions, store codecs,
HTTP response models and downstream CLI/MCP consumers for loss of meaning.
Do not change the shared operation version constant as an isolated edit.
Any legacy adapter must disclose missing guarantees: old applied/absent reports
cannot be promoted to cessation, partial-effect or safe-resume evidence.
Missing historical evidence stays unknown; migrations never replay work, invent
fences, silently discard fields or rewrite terminal history. New protocol
publication need not force a legacy-store rewrite if its carriers remain
separate; document that boundary explicitly.

API-402 is this delivery's requirement; #1360 supplies its acceptance scope.
Use `RAES_REQUIREMENT_UID=API-402` when the branch lacks a UID. Preserve the
supplied CONSTRAINS/TESTS/DOCUMENTS relationships and use existing
DOCUMENTS/IMPLEMENTS/TESTS conventions for new evidence. Adjacent owners
API-403/404, RUN-304, ASR-532 and #1348's change/retain table remain consistency
obligations, not substitutes for API-402. Distinguish contract publication from
runtime enforcement; do not mark the prerequisite's runtime gaps complete.

Preflight verification found a governance blocker: the repository-authority
check reports `requirement-policy-missing` because API-402 is not mapped in
`tools/policy/requirement_order.yaml`. Reconcile that mapping with the canonical
requirement authority before delivery; do not guess dependency ordering, use
API-404 to bypass the gate, or report requirement governance as passed. This
guidance does not change requirement policy or traceability records.

Delivery resolution: API-402's existing ACTIVE live control-plane contract now
maps to the existing `runtime-control-plane` phase beside API-404. A regression
exercises the real policy consumer, and requirement governance passes with
`RAES_REQUIREMENT_UID=API-402`. No dependency phase or prerequisite was removed.

## Examples and assurance boundary

Contract examples must demonstrate relationships, not just individually valid
JSON objects. Keep them in the existing fixture/conformance system:

| Required example | Meaning that must remain visible |
| --- | --- |
| Accepted work | Exact requirement/context binding, acknowledgement before execution, correlated progress and backend evidence; runtime success only after all gates. |
| Contextual refusal | Supported capability but unwilling context; pre-claim denial is audit only, accepted-before-dispatch refusal becomes cancellation with refusal diagnostic. Refusal after possible effects requires effect classification. |
| Cancellation races | Request recorded/accepted differs from cessation. Completion can win; cancellation can retain validated partial effects; late evidence cannot overwrite either terminal result. |
| Duplicate requests | Same scoped identity returns the same work/disposition without another invocation, interrupt or renewed budget. Changed commitments, actors, runs and generations cannot alias the claim. |
| Uncertain completion | Partial effect followed by exception, malformed evidence, absent-at-one-instant without cessation, and lost store acknowledgement retain their distinct uncertainties. Reconciliation supplies evidence without replay. |

Reuse lifecycle tests (`test_issue_1182_operation_lifecycle_contract.py`),
#1348's bounded supervision model, #1179 recovery, #1184 claims, #1187 durable
carrier/security tests, #1189 profile declarations, `test_backend_profiles.py`,
`test_runtime_contracts.py` and `test_contracts_facade_exports.py`. Include
negative cross-message identity/evidence cases and schema/Python parity;
`test_issue_1348_operation_supervision.py` is an abstract witness, not proof
that an installed backend can stop work. Use existing schema coverage and
fixture validation rather than tests that merely search for model names.
Each new publication needs actual routed corpus/conformance coverage or another
accepted coverage association under `tools/check_schema_coverage.py`; merely
adding a fixture directory does not demonstrate that a runner exercises it.

Repository conventions remain `.ground-control.yaml`, `.gc/plan-rules.md`,
`noxfile.py` and the existing policy, generated-schema, publication, coverage,
requirement-governance and ADR-pin tools. Run targeted checks for changed
artifacts locally; full/integration/fuzz suites belong to CI. This preflight
changes only guidance and requires no generated artifact or runtime test change.

Non-goals: implementing execution/supervision, new HTTP endpoints or transports,
a second scenario/workflow engine, generic durable-job/checkpoint services,
implicit retry/resume/rollback, universal cleanup, P3/multiple owners, or physical
containment/certification. Avoid free-form policy/evidence dictionaries,
duplicate lifecycle enums or cleanup schemas, parallel exception/audit systems,
and capability claims inferred from schema availability. Keep implementation
changes for #1360 confined to publishing usable contracts, their necessary
validation/compatibility boundaries and evidence, rather than solving the
prerequisite's entire runtime backlog.
