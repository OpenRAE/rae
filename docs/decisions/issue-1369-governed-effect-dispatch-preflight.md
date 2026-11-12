# Issue #1369 — Governed effect dispatch preflight

Date: 2026-10-25. Inspected base: `4927340780d3e3256c9825d8f52b3f1405e0bded`.
The supplied issue title, body and acceptance criteria are the contract; this
run has no formal requirement assignment. This note constrains implementation,
without implementing it or prescribing an implementation sequence.

Retain [ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[ADR-111](adrs/adr-111-control-applicability-and-effect-decisions.md),
[CA-06/07](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md),
[ADR-112](adrs/adr-112-external-inject-triggering-and-execution.md) and
[ADR-104/113](adrs/adr-113-reusable-execution-machinery.md).
The [#1069](issue-1069-run-320-runtime-orchestration-preflight.md),
[#1364](issue-1364-repeatable-control-cancellation-preflight.md) and
[#1368](issue-1368-directed-inject-occurrence-preflight.md) preflights supply
the adjacent owner boundaries. No new ADR or semantic primitive is needed.
The issue's diagnosis was inspected in local Git at
`077f7d04:docs/research/runtime-refactor/diagnosis.md`, sections 3–4. Its
counterexamples motivate the work; its old source observations are historical.
Python module paths below are relative to `implementations/python/packages/`;
unqualified modules belong to `raes_runtime`.

## Decisions and observed integration risks

Parent permission is decided before scheduling. A mandatory deny/withhold
targeting the exact parent prevents its execution regardless of a provider's
phase label. Use the existing contract-owned composition, not a second reducer
in the dispatcher. API-424/v2 already separates `ControlParentDecisionV2Model`
from executable effects and supplies `derive_control_effect_plan_v2()` and
`admitted_control_effect_ids_v2()`. Keep required coverage, mandatory input
satisfaction, support and incumbent gates conjoined. Required advice is not a
direct veto, and optional failure cannot cancel otherwise authorized work.

| Relation | Required behavior |
| --- | --- |
| Required predecessor | Commit a withheld parent and separately admit the predecessor only when its result can satisfy the remaining blockers. Resume through fresh-cut admission with the exact applied owner receipt and retained causal linkage; never rewrite a terminal refusal into success or resume merely because a drain returned. |
| Success-dependent consequence | Require the declared exact parent admission or application receipt. Acceptance, intent commit and dispatch attempt do not establish application. Failure cannot roll back a settled parent. |
| Independent consequence | Use its own authority, target, support and allowed parent dispositions. A complete deny/withhold may trigger an authorized audit/review, but unrelated mandatory failure, stale context or unsupported coverage supplies no such permission. It cannot release the parent. |

Check the combined parent/effect graph, not just provider dependencies or each
phase separately. Missing, failed, unsupported or indeterminate predecessors
authorize no dependent operation. Receipt joins must also establish target,
full intent, originating cut and validity. Ordering cannot repair conflicting
transforms/routes/handoffs or make a terminated target live.

At the inspected base the following are integration gaps, not extension points
to bypass:

- `participant_control_effects.py` drains v1 by `admitted_effect_phase()` and
  returns unsupported v2 effects. Its owner bindings cover only inject/handoff;
  its default submission branch records control for handoff. Extending target
  resolution without corresponding owner dispatch would misroute new kinds.
  Admit only an explicit supported owner/target/operation combination. A required
  unsupported kind must refuse before parent execution, rather than become an
  eligible plan with a later unsupported drain result. Optional unsupported
  contributions use the incumbent isolated lost-advice/unapplied semantics.
- `participant_control_evaluation_v2.py` constructs `commit.status="prepared"`,
  no commit receipt and empty dispatchable IDs; history append alone does not
  finalize that boundary. Optional executable effects are explicitly disabled
  through `normalize_optional_control_result_v2(..., executable_effects_supported=False)`.
  Narrow these guards only for a complete supported path. The durable committed
  projection, transaction receipt, intent digests, consumed budgets and
  dispatchable IDs must agree atomically; never fabricate authorization on read.
- The v1 realization writer and `participant_control_receipts.py` assume v1
  evaluation/owner shapes. Extending the drain alone misses contextual readers,
  origin joins, causal folds, realization commits, retry lookup and restoration.
  Preserve original versioned history and meaning. New amended behavior needs
  explicit consumer admission; unsafe fresh legacy requests fail closed, and
  historical unsafe pending work needs owner reconciliation, never automatic
  upgrade or redispatch.
- `claim_outcome()` maps owner operation success to applied. That is sufficient
  only when that owner's success establishes the requested effect. Successful
  control recording proves acceptance, not target cancellation; a successful
  crossing proves its stated delivery boundary, not world inject execution or
  participant observation.

## Incumbent effect owners and honest outcomes

The [PC-09 owner map](../research/modular-participant-control/composition.md#pc-09--closed-effect-vocabulary-and-incumbent-owners)
remains authoritative. The closed target vocabulary is not a promise that every
kind is executable by every installed composition.

| Effect family | Owner to reuse and boundary to preserve |
| --- | --- |
| Permit, deny, withhold | `participant_control_orchestration.py`, API-423 crossing/action admission and final-sink owners. Parent decisions execute no subsequent callback; v2 deliberately excludes them from executable targets. |
| Transform, mask, route | Existing crossing derivation/egress, participant action binding and trusted-edit owners. Produce a fresh candidate with source lineage/markings and destination admission; retain SEM-234 gates for mixed routes. No implicit declassification or controller change. |
| Inject | `RuntimeControlPlane.submit_inject()`, `inject_execution.py`, `inject_claims.py`, `inject_outcomes.py` and `InjectExecutionResolver` own the fresh DSL-111 world occurrence and evidenced outcome. `deliver_participant_inject()` / `participant_inject_application.py` own the separate DSL-142 result delivery. Direction/intervention additionally joins the exact accepted API-409 application. |
| Handoff, interrupt, shutdown | `record_participant_control()`, mixed-control occurrence/episode owners and `participant_control_cancellation.py`; execution/workflow/run targets additionally use their actual lifecycle owners, `cancel_operation()` / `supervise_operation()`, `participant_execution_control_boundary.py` or `cancel_workflow()` as applicable. Resolve exact target revision and invocation first; these APIs are not interchangeable and do not all promise interruption. |
| Delay, request-review | Existing shared-time/scheduling/resumption and supervisory proposal/approval owners, with declared clock/order, expiry and fresh-cut resumption. A DTO alone is not an installed executor. Refuse required unsupported joins; introduce neither sleeps nor another workflow interpreter. |
| Audit | Existing bounded audit/evidence owner under the specified audience and retention policy. An incidental dispatch log or denial audit cannot answer for a requested governed audit artifact. |

The current inject resolver can supply an already projected status view or an
application referring to an existing world operation. Neither creates the
requested fresh world effect. `submit_inject_effect()` currently only delivers
that existing result. Bind new inject work to its admitted world request and
operation, then independently join delivery/control obligations where required.
Do not force participant/episode/audience dependencies onto general world
injects, or refire a world inject just to retry disclosure. Keep explicit
fan-out and one-use `(control occurrence, delivery binding)` consumption.
The current artifact-only inject owner refuses native residual snapshots and
distributed execution; do not advertise these combinations by installing an
effect resolver. Reuse native result admission if that capability is separately
extended. A failed/partial/indeterminate world result is not a successful
produced-result correlation.

For cancellation, retain the exact control occurrence, operation, target
operation/invocation/attempt/generations, control ID/digest, response and outcome
evidence. `ParticipantCancellationStatus`, `InvocationLedger`, backend response
validators and `OperationEvidenceResolver` already separate acceptance from
PREVENTED, PARTIAL_LIMITATION and TOO_LATE. Do not infer any from target kind,
timeout or callback presence. Native operations promise no remote interruption.
Serialize prevention against one-use dispatch; after consumption require owner
evidence of effects and cessation. Completion may win. Unknown effects/cessation
remain indeterminate with reservations retained; a local cancelled task, process
exit, stopped admission or workflow-status update proves no rollback or stop.

## Cross-cutting layers the implementation must pass

| Layer and canonical incumbents | Required fit |
| --- | --- |
| Authored intent and plan authorization | `raes/parser.py`, safe bounded YAML loader, reference-purpose validators, mixed-control/inject validators, compiler indexes and `control_plane_plan_authorization.py` own closed authored meaning and planner authorization. Revalidate direct/model inputs; resolve canonical addresses and original compiled policy/plan digests, not raw `spec` maps, suffix matches or provider claims. |
| Wire and contextual schemas | `ContractModel`, `OperationContractModel`, shared `ControlRef`/strict count coordinates, `json_ingress.py`, API-424 composition/evaluation/decision models and `participant_control_resolution.py` own shape and joins. Bound bytes/depth/collections; reject duplicate JSON keys, nonfinite values, unknown fields and coercible bool/string coordinates. Detach/revalidate nested callback inputs and outputs. Model acceptance, digest equality and `safe_references` membership do not replace independent authority/evidence resolution. |
| Auth and scope | `ControlPlaneSecurityConfig.strict_defaults()`, sealed API `_auth.py` route roles, `operation_admission_context()`, `ParticipantControlSubjectBinding`, `ParticipantAudienceSubjectBinding`, `require_drain_authority()`, `origin_principal()` and `authorize_supervisor()` own independent caller, effect, target and readback authorization. Bind target/run, participant/episode/controller/audience and the full effect commitment. The drain caller cannot lend privileges; `originating_principal_ref` is not authentication. Historical grants prove admission, not current dispatch permission. Current read authorization precedes retry/result disclosure. P0/P1 trust the embedder; `identity=None` must never replace a served caller. |
| Configuration and support | `ControlPlaneOptions` / `ControlPlaneConfiguration`, `ParticipantControlRuntimeBinding`, typed inject/mixed-control bindings, `OperationSupervisionConfiguration`, runtime profiles, registry shape checks and API-407 `resolve_participant_control_support()` own installation. Validate selected owner capabilities, target alternatives, supported contract pins and contextual willingness at admission and again before dispatch. Method presence or a manifest claim is insufficient. Keep unsupported mixed/distributed/profile paths refused; no silent upgrade. |
| Mutation and host responsiveness | `RuntimeMutationAuthority.supervision()` / `external_call()`, `detached_extension`, `SubordinateMutationGate`, `LocalExecutionAdapter` and API `_ControlPlaneCallExecutor.control()` own one writer and bounded separate effect/control/store capacity. Run extensions outside permits, locks and transactions; compare original history/snapshot/execution generations after callbacks. Do not copy the drain's old assumption that a held mutation protects an entire external call. Cancellation must pass both supervisory mutation admission and durable claim rules while effects stall; exempting every effect claim from exclusion is unsafe. |
| Durable identity, causal budget and recovery | `participant_control_receipts.py`, `participant_control_causal_state.py`, `participant_control_records.py`, crossing/control commit helpers, `RuntimeDurabilityMixin`, `ControlPlaneStore` atomic transitions, snapshot CAS, `InvocationLedger`, `operation_ledger_transactions.py`, strict record codecs/migrations and `control_plane_recovery.py` own publication and replay. Preserve actor-bound atomic state/history/audit/claim commits, original commitments, lost-ack readback and readiness poisoning across memory and admitted SQLite/PostgreSQL stores. New linkage must survive non-success records and reopen, not live in unchecked metadata or a side journal. |
| Backend execution, results and evidence | `require_operation_provider()`, backend input/admission/policy validators, `operation_provider_execution.py`, `operation_provider_control.py`, backend response/history validators, `backend_calls.py`, native result/snapshot validators and installed `OperationEvidenceResolver` own one-use invocation/control, request digest, sequence, generation and final release evidence. Preserve residual state and effect-owner scope. Reference presence or a provider's success boolean establishes no observation. Native participant scheduler work requires its own execution-owner join, not an assumed generic-provider binding. |
| Final disclosure, time and observation | `participant_crossing_boundary.py`, `participant_crossing_egress.py`, `participant_flow_sink.py`, API-424 orchestration, delivery-control validators, `TimeCoordinator` and observation admission/execution/results owners retain IFC, authority, exact audience, policy, marking, expiry and evidence gates at the actual sink. Distinguish store revision, state/order/time coordinates and execution generation. Withhold/denial existence, timing, correlation refs, errors and exports are disclosures too. Capture, emission and participant observation remain separately evidenced. |
| Secrets, environment and OS exposure | `SecretReferenceId`, runtime fact-binding policy, `raes/runtime_environment.py::RuntimeEnvironmentVariable`, generated-artifact resolution and `enforce_observed_value_redaction()` retain logical secret references, provenance/classification, valid names, literal/`value_from` exclusivity and raw-value omission. `Inject.environment` remains a list of environment references, not an arbitrary variable bag. This dispatch change needs no credential loader, shell, subprocess or new listener. Backend adapters retain validated argv/environment including NUL checks and protected secret channels; credentials/private payloads must not enter argv, URLs, shell interpolation, engine history, errors or environment dumps. Host TLS/proxy header stripping, process isolation, store path/sidecar permissions, owner leases and worker admission remain in force. |
| Error envelopes and observability | Reuse `Diagnostic`, `portable_diagnostic_payload()`, terminal diagnostics, existing exceptions, `AuditEvent`, `control_plane_audit.py` closed keys and API `_responses.py`/route handlers. Preserve stable redacted 401/403, disclosure-safe 404, conflict 409, validation 422 and internal/unavailable responses plus `no-store`, including retry/error paths. No raw exception chains, Pydantic inputs, model repr, native output or evidence bodies in logs/audit/errors. An ambiguous post-dispatch failure is not an ordinary known failed effect. ADR-066 separates telemetry, operational audit, participant disclosure and experiment evidence; no new error/log hierarchy. |
| Whole-snapshot and publication gates | `validate_realization_value()`, `RUNTIME_SNAPSHOT_VALUE_LIMITS`, `backend_snapshot_contracts.py` and `participant_control_evaluation_history.py` enforce aggregate bounds and exact runtime-owned append-only histories. Preserve original lineage readers, unknown-version refusal and provider-state chains. Necessary carrier changes evolve the owning published schema, embedded snapshot definitions, `schema_bundle()` parity, fixtures and `contracts/schema-publication/entries/` hashes under ADR-009/061/075; neither a private DTO nor generated OpenAPI is publication. |
| Repository and deployment workflow | `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/adr_policy.yaml`, ADR-015/036 ownership and size gates, canonical `noxfile.py` / `tools/nox_support/`, verification classification and CI remain authoritative. Runtime builds on contracts/protocols and public processor seams, not concrete backends or conformance imports. Use scoped policy/hygiene and explicit relevant tests locally; full/integration/fuzz/completion suites belong to CI. Keep this run issue-based: do not invent a requirement UID or copy a prerequisite's assignment. No release-owned version/changelog or accepted-ADR edits, new service or external data transfer. |

## Identity, extension seam and evidence bar

Retain the logical key `(run, trigger root, rule/revision, effect slot, firing
epoch)` independently of actor-scoped transport retry keys. Allocate fresh
effect/owner operation identities once per logical key; reuse them on recovery.
Changed canonical content conflicts. Preserve separate durable links for trigger
commit, effect admission/claim, dispatch consumption and owner-observed outcome.
World execution and participant delivery may require multiple owner operations;
one hardcoded owner-kind lookup cannot stand in for that causal chain.

Use the existing trusted `effect_operation(request, context)` binding seam with
closed owner inputs, parameterized by target kind/operation, exact compiled
artifact, originating principal, required guarantee, causal root and live cut.
Capabilities and reader pins belong to binding/configuration admission;
apparatus budgets/capacities stay in `OperationSupervisionConfiguration` and
semantic time stays with its owner. A next supported lifecycle target or backend
should extend its typed owner mapping and capability tests, not require a second
dispatcher, generic callback payload, policy language or service registry.

Maintain root-wide depth, attempts, effects, fan-out, firing and expiry limits
across participants, handoffs, transforms, episode resets and restarts. Duplicate
recovery spends no second effect budget; dispatch failure does not refund one.
A dispatch can resume only with durable proof it never began. In particular,
`never_dispatched()` relies on every selected owner claiming write-ahead in the
same serialized scope: missing in-memory state or an eventually visible remote
record cannot prove non-dispatch. A possibly consumed invocation/control is
observed/reconciled through its owner, never blindly repeated. Engine retries
do not grant authored retry permission; uncertain restart time grants no fresh
full apparatus budget. Failure diagnostics must not recursively trigger effects.

Implementation evidence must drive public `RuntimeControlPlane` boundaries
through installed providers, composition, committed records, real owner calls
and authorized outcome readback. Build on `test_issue_1069_*`,
`test_issue_1368_control_inject_owner.py`, `test_issue_1367_inject_execution.py`,
`test_issue_1364_cancellation*.py` and #1362 supervision/invocation/lost-ack
fixtures. Existing abstract phase tests and the private `_submit()` inject test
do not establish this end-to-end path. Demonstrate later-phase deny/withhold
with zero prohibited execution/disclosure; authorized independent consequences;
required owner refusal before parent execution; predecessor and admitted/applied
parent dependencies; real fresh world inject plus distinct delivery/control
outcomes; both cancellation/completion race orders and unproved cessation;
dispatch failure/timeout; exact duplicate, changed-content conflict and crash
reopen without redispatch or budget reset. Include stale/revoked authority,
wrong scope, blocked-effect supervisory responsiveness and redacted errors.
Use existing barrier/event fixtures, not timing sleeps. This preflight claims
none of those runtime tests or guarantees as achieved.

Non-goals: implementing every published effect kind, replacing orchestration or
execution machinery, adding authoring syntax or a universal effect DTO,
reinterpreting historical v1 records, universal rollback/external exactly-once,
new backend interruption guarantees or deployment profiles. Do not equate
policy acceptance, intent commit, dispatch, applied effects, cancellation,
delivery, capture and observation. Supported subsets are valid; admitting an
unrealizable required plan is not.
