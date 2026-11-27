# Issue #1069 — Applicable provider evaluation preflight

Date: 2026-10-15. Inspection baseline: `ec1cdce9`. Scope: RUN-320 and the
supplied #1069 applicable-provider evaluation acceptance criteria, with #1365
and #1362 as prerequisites. The issue narrows this delivery; it does not remove
RUN-320's effect, durability, causal-budget or recovery obligations. This
replaces the 2026-09-20 preflight's pre-amendment assumptions; it is architecture
guidance, not an implementation plan or runtime conformance claim.

[ADR-108](adrs/adr-108-modular-participant-control-and-governed-effects.md),
[ADR-111](adrs/adr-111-control-applicability-and-effect-decisions.md),
[CA-01–CA-09](../../specs/formal/participant-semantics/control-applicability-and-evaluation.md)
and the [migration contract](../migration/control-applicability-and-evaluation.md)
already decide the semantics. Reuse the #1365 contracts and #1362 supervision
([contract preflight](issue-1365-applicable-provider-contracts-preflight.md),
[supervision preflight](issue-1362-supervised-execution-preflight.md)); no new
ADR, policy algebra, provider registry or workflow engine is warranted.
Package paths below are relative to `implementations/python/packages/`.

Inspection confirms v2 contracts/protocol/composition and the supervised-call
adapter exist, while runtime binding, orchestration, evaluation-history
validation and causal folds still consume v1. Traceability and prior v1 tests
do not prove coordinated v2 adoption. The issue's historical
`docs/research/runtime-refactor/diagnosis.md` reference is absent at this cut;
the supplied acceptance criteria and current owners are the inspection basis.

## Decisions and adoption boundaries

**Retain B; derive A(B,K).** The exact admitted v2 selection is the apparatus B.
Compare that complete selection with the installed binding; never compare the
applicable subset's digest with B or filter B to manufacture equality. Resolve
total profile-owned obligation coverage independently of provider responses:
applies, proven inapplicable with exact-cut evidence, or unresolved. A missing
provider, resolver `None`, exception or absent result proves no inapplicability.
An empty A is valid only with complete proven coverage and incumbent gates;
explicitly absent modular requirements are a separate configuration case.
A provider serving another source/sink remains in B and is not called at this K.

**Schedule slots/stages, not providers.** Consume the admitted finite DAG from
`participant_control_applicability.py`; permit A.fact → B.assessment → A.rule.
Use `ParticipantControlProviderV2.resolve_stage(ControlInvocationV2Model)` from
`raes_backend_protocols/protocols.py`. A ready stage receives exact detached
predecessor identities/content digests and scoped committed/tentative state
through its authorized projection. The installed provider's scoped reference
resolution must actually supply that content; a digest or common K alone does
not prove predecessor consumption. No ambient result lookup or private-state
sharing. Never batch a producer and its consumer into one invocation.

The runtime checks readiness before each call and validates every output against
its requested slots, binding, invocation and complete input identity. Reuse
`validate_control_invocations_v2`; it validates a completed record and does not
schedule work or establish chronological execution. Missing mandatory input
produces an explicit unsatisfied consumer result without calling that consumer.
The complete record must still satisfy API-424's invocation/result accounting;
a blocked-stage descriptor is not evidence a provider ran. If an unsupported
blocked-input/state combination cannot be represented, close the seam at the
contract owner or refuse safely; never fabricate successful input or weaken
validation. Canonical serialization order is not execution order or conflict
resolution. Bound traversal, stages, result iteration and bytes before consuming
provider-controlled iterables, including generators and malformed duplicates.

**Closure determines availability, not advice authority.** Use admitted
`required_slot_ids` (M), coverage and support pins from the request. A nominally
optional fact/advice slot in M must be available; a negative advisory assessment
still cannot veto. Only an admitted decision interprets advice into deny or
withhold. Mandatory abstention/unresolved results never release the crossing;
explicit evaluated `not-triggered` is different from missing rule evaluation.
Use `ControlSupportAssessmentV2Model`, the API-407 manifest join in
`raes_backend_protocols/participant_control_admission.py`, and independently
resolved requirement-relative constraints. Neither all-exact checks nor a
numeric ordering of support labels implements the admitted relation.

Isolate optional failure outside M at its invocation boundary. Reuse
`normalize_optional_result_failure_v2` for its supported one-slot malformed
case; it is not an evaluation-wide exception handler. Other optional absence,
timeout, stale/support failure and conflict need the same safe typed lost-advice
accounting, with discarded payload, effects and state. Do not retain a discarded
optional state proposal as a tentative predecessor. Mixed-stage failure must
not relabel mandatory work as optional. Extend an owning contract helper if
needed rather than duplicate normalization/composition in runtime. Required
conflicts block; optional conflicts are omitted with evidence under CA-03.

**Parent outcome and effect readiness have different authorities.** A resolved
mandatory deny/withhold is a complete decision, unlike an absent mandatory
result. Use `participant_control_decisions_v2.py` for unscheduled decisions,
typed outcome prerequisites and combined parent/effect cycle checks. Join its
provisional runnable effects through `admitted_control_effect_ids_v2`; neither
the runnable list alone nor a blanket eligible/non-eligible test defines the
admitted intents. Independent consequences may survive a complete refusal only
for their admitted disposition and authority, with no unrelated mandatory
blocker. An accepted parent receipt is not application: an `applied`
prerequisite needs the exact incumbent owner's application evidence. Required
predecessors keep the parent withheld until that outcome and fresh evaluation.
Preserve append-only outcome evidence rather than mutate the original plan to
create a parent receipt or dispatch opportunity. Do not reuse v1 phase rules
for these v2 decisions.

**Use supervision without transferring state authority.** Reuse
`OperationSupervisionConfiguration`, `LocalExecutionAdapter.call`,
`RuntimeMutationAuthority` and `external_control_plane_call()` for provider and
trusted-resolver callbacks. `operation_provider_execution.py::provider_call`
is a supervision precedent for backend-operation DTOs, not a callable adapter
for participant-control results. Keep these two provider protocols distinct.
Use the existing bounded lane/capacity and remaining deadline, not another
executor, per-provider thread pool or invented operation lifecycle. Graph and
attempt bounds complement wall-clock bounds; governed scenario time is separate.

External calls release the state permit while retaining effect exclusion;
supervisory actions may commit meanwhile. After reacquisition reload and verify
the pinned snapshot revision, generation, stop/cancel state, policy/support,
all relevant history heads and state versions before a dependent call, commit or
release. Do not submit an old prepared snapshot using a newly refreshed CAS
revision. Stale work requires fresh K and admitted retry consumption. Detach
inputs and returned projections; frozen wrappers are not deep immutability.
Timeout bounds the caller, not the physical worker. Late output may never commit;
retain adapter capacity/resource ownership until actual exit, keep control/store
capacity available and preserve drain/readiness behavior. An in-process provider
remains trusted installed code, not an OS sandbox or cancellable world effect.

**One atomic state authority.** Reuse `derive_control_composition_v2`,
`ParticipantControlEvaluationV2Model` and
`validate_participant_control_resolved_context_v2` from `raes_contracts/contracts/`.
Independently owner-resolved coverage, installed bindings, support, safe refs,
incumbent crossing records, authorized state writes and receipts populate
`ParticipantControlValidationContextV2`; copying provider assertions into that
context is not verification. Closed-model acceptance proves no owner authority.

State scope/version belongs to the admitted instance/configuration/authority
and sharing domain, not merely profile, participant memory or implementation
name. `ControlStateProposalV2Model` and `validate_state_proposals_v2` own writer
chains: pin committed versions, explicitly pass tentative predecessor versions,
reject forks/unordered writers, and enforce evaluation versus parent-release
commit timing. A refused parent can commit only independently authorized
evaluation-state updates, never action-success state.

Join accepted state changes, complete evaluation/coverage/results, decisions,
authorized effect intents/claims, consumed budgets, operation and audit in the
incumbent `commit_participant_transition()` transaction with expected heads and
snapshot revision. `ControlCommitBoundaryV2Model` is a wire claim, not a store
receipt: prepare before commit, bind the committed fact only to authoritative
store evidence, and do not rewrite an appended evaluation to mark success.
Use `control_plane_durability.py`, `BoundedControlPlaneStore`, store CAS/leases
and authoritative readback; failed or uncertain commit dispatches nothing.

`expected_participant_history_heads()` currently covers one participant;
shared run/participant scopes and shared causal roots need all affected versions
inside the same transaction/read set. The existing global snapshot CAS can
supply concurrency coverage only when every shared write is represented there
and the original revision stays pinned. A resolver-private state map or another
store does not participate. Unsupported cross-store atomicity stays unsupported.
Reuse existing history/folds for derived indexes; any necessary typed carrier
must pass the exhaustive snapshot/transition surfaces below, never metadata.

**Keep logical identity and consumption through re-evaluation.** Reuse
`ControlLogicalEffectKeyModel`, `ControlCausalBoundsModel` and the retained
consumption folds, selected by historical interpretation. The logical key is
`(run, trigger root, rule id/revision, slot, firing epoch)`; retry, cut and
transport identities never enter it. New transformed/injected occurrences
need fresh identities, causal links and ordinary downstream admission. Replays
retain the allocated effect identity and full intent digest; changed content
under the same key conflicts. Each evaluation consumes an attempt, including
refusal and no-effect evaluation; realization evidence does not consume it
again. Fresh cuts, episode/binding replacement, restart or history retention
must not restore root/depth/fan-out/firing/effect/retry budgets or forget an
uncertain dispatch. Finite traversal limits do not replace durable consumption.

## Whole-repository layers to preserve

| Layer and canonical incumbents | Required satisfaction |
| --- | --- |
| Portable ingress: `raes_contracts/_base.py`, `json_ingress.py`, `contracts/participant_control_{applicability,invocation,evaluation_v2}.py` | Reconstruct detached portable projections, reject unknown fields/IDs/duplicates/cycles, bind exact revisions and bound nested/aggregate material. Use `parse_participant_control_evaluation_v2` for serialized ingress (1 MiB/depth 32). Direct Python callbacks require equivalent finite validation; model construction/subclasses and lazy iteration cannot bypass it. |
| Configuration/admission: `raes_runtime/control_plane_configuration.py`, `control_plane_composition.py`, `participant_control_binding.py`, `registry_target_validation.py`; API-407 manifests | Extend the typed immutable binding/resolver seam with explicitly negotiated v2 selection/protocol/interpretation. Current binding admits v1 only. Preserve exact installed B and run/target/policy/support checks; method presence proves no support. No scenario code locator, import path, URL, command or untyped option bag. |
| Authentication and policy: `control_plane_api/_auth.py`, `ControlPlaneSecurityConfig.strict_defaults()`, `RequestSizeLimitMiddleware`, `AppCompositionSealMiddleware`, crossing/control/final-sink owners | Existing HTTP authentication (constant-time bearer comparison or explicitly configured trusted proxy), actor/role/target/controller/participant/audience checks and API-409/API-423/SEM-233 gates still apply. Preserve the served composition seal, route-authority declarations and authentication before validation-error responses; add no route or dependency override. Preserve originating `OperationAdmissionContext` and parent-operation lineage through effects; absent identity must not invoke the trusted-embedder fallback. Eligibility cannot grant disclosure or effect authority. |
| Secrets/environment: `raes_contracts/secret_references.py`, `raes/runtime_environment.py::RuntimeEnvironmentVariable`, `raes/runtime_values.py::enforce_observed_value_redaction` | Provider projections/state/evidence contain only owner-approved bounded values/refs, with no prompts, private memory, credentials or rejected payloads. This change needs no environment binding. Any existing downstream binding retains name validation, literal/`value_from` exclusivity, source classification and redaction; hashing a secret does not redact it. |
| Host/process and persistence: existing execution adapter/resource ownership; `control_plane_store_paths.py`; memory/local/PostgreSQL store implementations | No new subprocess, shell, dynamic loader, file transport, service or deployment topology. Never put inputs/secrets in argv, broad inherited environment, temporary names or stdout/stderr. Keep local-store ownership/type/link checks and private modes; preserve selected store/provider capabilities. PostgreSQL/distributed support is not implied by local tests or permission to provision services. |
| Snapshot/readers: `RuntimeSnapshot`, `_snapshot_updates.py`, `participant_control_evaluation_history.py`, `participant_control_causal_state.py`, `participant_control_records.py`, `participant_control_effects.py`, store codecs/migrations/history, `backend_snapshot_contracts.py`, `participant_result_contracts.py`, API snapshot DTOs | These consumers still include v1-only readers. Route by recorded contract ID before admitting v2 history; preserve v1 meaning, append-only identities, claims, attempts, budgets and realizations. Cover snapshot serialization/reopening, backend preservation and operation readers. Legacy absence is not an authoritative empty history. Unknown interpretation refuses safely; pending unsafe legacy work needs owner reconciliation. No replay resampling or automatic v1-to-v2 conversion. |
| Effects/recovery: `participant_control_receipts.py`, `participant_effect_authority.py`, `participant_crossing_boundary.py`, `participant_crossing_egress.py`, `control_plane_recovery.py` | Keep commit-before-effect/serialization, ordinary owner admission, final generation/policy checks, logical-key idempotency and uncertain-outcome reconciliation. Parent decisions are unscheduled; prerequisite effects cannot be confused with provider-input dependencies. v1 effect drain must not parse v2 as v1 or infer executable work. Unsupported effect-owner paths remain refused; no external exactly-once claim. |
| Errors/audit/observability: `Diagnostic`, `portable_diagnostic_payload`, `participant_control_diagnostics.py`, `control_plane_audit.py`, API `_responses.py`/`_operation_routes.py`, `NoStoreResponseMiddleware`, `control_plane_health.py` | Use stable value-independent reasons and existing error/receipt/audit envelopes and module logging conventions. Shape validation and bounded text are not redaction. Do not expose raw exceptions/chains, validator inputs/unknown keys, repr, provider names or private references. Preserve coarse conflicts, redacted 422/500, audit field allowlists and uncacheable responses. Apply audience projection and ADR-066 plane separation to coverage, reasons, loss, withhold existence and timing; readiness must reflect lingering workers/uncertainty. |
| Governance/package/CI: `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/policy/{adr_policy,requirement_order}.yaml`, `docs/governance/requirement-scopes/1069.json`, `noxfile.py`, `tools/verification_plan.py`, `.github/workflows/canonical-verification.yml` | Keep contracts neutral, protocol imports limited to contracts, and runtime independent of concrete backend/conformance packages (ADR-015/036). Reuse existing ownership, policy and targeted verification lanes; set `RAES_REQUIREMENT_UID=RUN-320` when the branch does not carry it. RUN-320 owns orchestration; any prerequisite contract change retains its API-424 owner and traceability. Schema changes, only if necessary, retain `schema_bundle()` parity, schema invariants, explicit generator routing, manifest-v2 per-contract publication entries and packaged corpus. Preserve ADR pins; no changelog/version edits or new dependency/runner. |

Serialized ingress bounds and per-record schema limits do not bound the complete
snapshot. Any added state/history representation must also pass
`raes_contracts.realization_structure.validate_realization_value` (public
package export),
`raes_contracts/runtime_value_limits.py::RUNTIME_SNAPSHOT_VALUE_LIMITS` and
`backend_snapshot_contracts.py`'s exhaustive carrier/aggregate checks. Reuse
these bounded-value primitives for portable material rather than a second
recursive validator; account for collection growth without pruning away replay
or recovery authority. Confirm a committed v2 cut reopens under its exact reader
before enabling it at a live sink.

## Extensibility, evidence and limits

The seam is the existing immutable runtime binding plus trusted scoped resolver,
parameterized by admitted v2 slots/dependencies, projection, state scope/commit
condition, support requirements and finite bounds; apparatus execution budgets
and capacities remain in `OperationSupervisionConfiguration`. Another provider,
source/sink or A → B → A variation should need a different admitted graph and
binding, not branches on names or a new scheduler. Contract interpretation
selects the reader/composer explicitly; v1 is retained without amended guarantees.

Reuse `participant_control_runtime_fixtures.py`, `participant_crossing_fixtures.py`,
the `test_issue_1069_*` orchestration/durability/authority/carrier patterns,
`test_issue_1365_applicable_contracts.py`, and #1362 supervision/state-authority/
resource-ownership/lost-ack fixtures. Required evidence drives public
`RuntimeControlPlane` ingress, control and egress paths through actual binding,
provider, composed record and store, with backend-call/serialization counters.
Include disjoint source/sink providers under unchanged B; complete empty A
versus unresolved/missing coverage; A → B → A with content-sensitive results;
missing installation and mandatory input; stale predecessor/cut/state/support;
optional exception/malformed/unsupported/timeout/conflict with no veto or state;
required advice with no direct veto; bounded support acceptance/refusal; false
triggers; state-chain/fork conflicts; supervision races, late results and failed
or uncertain commits; complete deny/withhold with authorized independent
consequences versus unrelated mandatory failure; parent-admitted versus
parent-applied prerequisites and combined parent/effect cycles; direct callback
and aggregate snapshot limits; redacted error/audit/log projections. Verify both
zero prohibited dispatch/disclosure on required failure
and permitted release after isolated optional loss. Reopen a real durable store
with mixed v1/v2 records and retained budgets/claims; reinterpretation cannot
generate new dispatch from old records. Positive operating-profile evidence
names an explicitly selected API-404 profile and its demonstrated store/backend
capabilities; `profile=None`, an HTTP endpoint or an API-424 profile supplies
no operating-profile guarantee. Use Event/barrier fixtures, not sleeps. Run
only relevant modules and scoped policy/schema checks locally;
full/integration/fuzz suites belong to CI.

Non-goals: implementing providers or policy products; a general DAG/workflow
engine, plugin discovery, second store/lock/error hierarchy/schema family;
redesigning effect scheduling beyond safe v2 consumer integration; provisioning
services, changing operating profiles or claiming distributed atomicity, hard
cancellation, backend parity or universal liveness. API-404 transport/durability
profiles, API-424 mechanism profiles, RUN-310 supervisory history, mixed-runtime
allocation and SDL orchestration remain distinct. No lexical/registration-order
winner, permissive missing-result default, optional-wide catch, in-place history
rewrite, hidden mutable shared state or metadata-based authority is acceptable.
