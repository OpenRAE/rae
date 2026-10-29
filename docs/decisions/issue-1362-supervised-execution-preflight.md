# Issue #1362 — Supervised execution outside state admission

Date: 2026-10-12. Architecture preflight for #1362 and the supplied API-404
requirement. Prerequisites: #1350 and #1360. This note adds no implementation,
implementation plan, published contract, profile guarantee or replacement
architecture. API-404's stable clauses and runtime-owned profile matrix remain
the claim boundary; the supplied traceability links are pointers to evidence,
not proof that supervised execution is already installed.

## Retained decisions and concrete gaps

Build on [ADR-104](adrs/adr-104-runtime-control-plane-architecture.md),
[ADR-113](adrs/adr-113-reusable-execution-machinery.md), the adopted
[execution protocol](../research/execution-architecture/execution-protocol.md),
[supervision semantics S1–S6](../../specs/formal/runtime-control-plane/supervision.md)
and the published
[backend operation protocol](../../specs/formal/runtime-contracts/backend-operation-supervision.md).
These already decide ownership, dispatch, settlement and recovery. No new ADR
or change to a pinned accepted ADR is needed.

Python paths below are relative to `implementations/python/packages/`.

Repository inspection identifies gaps that those contracts alone do not fix:

- `RuntimeMutationAuthority` releases its condition mutex, but retains its
  **logical permit** across external calls. `control_plane_execution.py` holds
  that permit over validation, apply and result processing. Unlocking the mutex
  again cannot make supervisory mutations responsive.
- `_ControlPlaneCallExecutor` uses `run_in_threadpool()` for reads, effects and
  admission probes. Separate methods are not separate AnyIO worker capacity.
  `_run_reserved()`/`_settle_worker()`, executor close and `RuntimeLifecycleMixin`
  drain can wait indefinitely. Authentication and redacted-error auditing can
  also depend on that saturated pool. `RejectionAuditExecutor` already shows
  the incumbent separate-limiter pattern, but its store call still needs a bound.
- `RuntimeTarget`/`RuntimeTargetComponents` have no operation provider binding.
  The published `BackendOperationProvider` shape checker and carriers are
  available, but publication does not install or execute them.
- `IdempotencyClaimIdentity`/`claim_record()` deduplicate operation submission;
  they are not one-use worker invocation grants. Current strict operation
  records do not retain the complete invocation, generation, control, budget,
  sequence and conflicting-effect reservation facts needed after reopening.
- `backend_calls.py` converts exceptions or rejected results to an unsuccessful
  `ApplyResult` with a trusted predecessor. `_commit_operation_result()` maps
  that to `FAILED`. This protects stored state but proves no external absence.
- Startup reconciliation calls observers under mutation authority. Legacy
  `RecoveryObservationResult` has no general cessation witness. A successful
  `accept-current-snapshot` child currently clears the unresolved-parent gate
  used by admission/readiness; it cannot discharge a new supervised invocation's
  effect reservation without the required cessation/effect evidence.

## Architecture and ownership guardrails

**One semantic owner, small execution adapters.** Preserve P0's in-process
composition and P1/P2's admitted local store/lease. Use Python/AnyIO concurrency
there. ADR-113 selects self-hosted Temporal/Python SDK with PostgreSQL for the
distributed composition; it does not require Temporal for local use or activate
P3. Both compositions use the same admission, policy, outcome and recovery
functions. Distributed integration must use the adopted ledger/engine protocol,
separate ledger database/role and control/effect capacity, rather than a custom
durable queue. Engine success, replay and task tokens carry no RAE authority.
Any partial delivery must describe its supported composition accurately.

**Short state cuts, retained effect exclusion.** Admission, confirmed one-use
dispatch claim, supervisory intent and terminal publication serialize through
the existing scoped state authority. No provider, backend, observer, resolver,
archive, final-sink or other extension callback runs while holding its logical
permit, cache mutex, lifecycle mutex or database transaction. Expensive native
validation/copying uses a bounded isolated predecessor outside the cut; commit
rechecks current ownership, binding and revision. Capture one coherent revision;
never pass a live mutable snapshot to a worker or mutate the retained predecessor.
Preserve the callback re-entry
prohibition across threads/tasks: a copied `ContextVar` reservation must never
grant an effect worker store authority. `SubordinateMutationGate` stays subordinate.

Releasing the state permit does not release the conflicting-effect reservation.
Use target/run-wide exclusion unless `OperationEffectScopeModel` carries admitted
independence. Supervision must be admitted despite an active reservation or
quarantine, while conflicting effects remain denied. Preserve authoritative
participant decision/control/history-head comparisons, workflow transitions and
mixed-backend stage ordering; adding capacity does not authorize parallel effects.
Direct `RuntimeManager` calls, another store path or a new control-plane instance
cannot bypass ownership of the same backend resources. Deployment must establish
that ownership; a process-local lock is not a cross-process resource fence.

The incumbent participant path already separates preparation, dispatch and
settlement in `participant_scheduler_concurrent_{dispatch,state,commit,settlement}.py`
and selects admitted independence/capacity in `participant_scheduler_concurrency.py`.
Keep those semantic owners and their native merge/history checks; do not copy
them into a generic operation scheduler. `ParticipantExecutionRuntimeMixin`
already checks participant generations, and `ParticipantClockDriver.stop()`
reports a failed bounded join. Neither a finite thread count nor that join
establishes backend cessation. Its exception-interpolating failure diagnostic
must not become a template for public supervision errors.

**Immutable dispatch and settlement bindings.** Bind original actor, exact
target/run, operation kind, admitted command/requirements and policy commitments,
backend identity, invocation/attempt, deployment/owner/execution generations,
trusted predecessor revision and effect scope. Consume invocation permission
atomically before effects; P1/P2 persist it, P0 orders it in memory. A lost grant
acknowledgement fails closed under the adopted conservative protocol. Finding a
consumed claim during recovery never grants permission again. Submission replay,
control duplication, engine delivery, effect invocation, authored workflow
attempt, trial/run and participant episode remain different identities.

A completion reacquires the same writer and compares binding, generation,
terminal state, snapshot revision and applicable history heads. Stale state
cannot be blindly merged or returned as successful publication. Commit the
validated residual/success snapshot, immutable terminal record and actor-bound
audit atomically through `RuntimeDurabilityMixin`/`ControlPlaneStoreCommitAdapter`.
Retain `TerminalCommitMode`, including operation-only results and existing no-op
revision rules. Lost commit acknowledgement invokes authoritative readback and
readiness poisoning; it is distinct from unknown backend effects. Publish only
after the complete cut is confirmed. Duplicate settlement returns that cut.

Persist enough admitted command identity and authorization provenance to resolve
the same native artifact after reopening. `RuntimePlanAuthorizationMixin`'s
process-local digest set is not durable worker authorization. A digest/reference
does not authorize loading arbitrary files or network locations; missing,
changed or inaccessible admitted artifacts close dispatch rather than trigger
replanning, renewed defaults or execution from an unverified worker payload.

**Protocol integration rather than another lifecycle.** Reuse
`BackendOperation{Binding,Request,Capabilities,Control,Response}Model`,
`require_operation_provider()`, `require_backend_operation_admission()`,
`require_backend_execution_policy_admission()`,
`validate_backend_operation_response()` and `validate_backend_operation_history()`.
They cover shape, commitments, contextual willingness and transcript joins; they
do not authenticate a producer, resolve artifacts, verify evidence or persist
runtime authority. Enforce each method's allowed message kinds as well as
cross-message validation. Sequence and duplicate commitments must survive
reopening; the helper's transient `_InvocationHistory` is not a durable ledger.
Same identity/content is idempotent; changed content is conflict. Progress does
not renew budgets or establish success; a start acknowledgement is neither an
`ApplyResult` nor a terminal outcome. Bounded retention must preserve claims
for the supported effect/replay/recovery window, rather than forget a fence when
the transcript reaches its size limit.

**Responsive control, honest outcomes.** Stop closes new effect admission and
prevents undispatched work from invoking, while authorized status, control and
reconciliation remain available through drain. A control request binds its own
trusted actor and scoped idempotency identity without replacing the original
actor. Record it before delivery and retain its disposition. Reserve bounded
capacity for authentication, HTTP admission/probes, workers, control callbacks,
store connections, rejection auditing and shutdown; an effect queue cannot be
the path to stop. Overload/unavailable responses are bounded and explicit, and
an acknowledged request cannot be silently discarded. Liveness remains
conditional when the state store or control provider itself fails.
Provider-owned locks, connections and job-control channels must also leave
control serviceable: separate runtime pools cannot make a cancellation method
responsive if it waits behind the same stalled backend invocation. Admit only
the demonstrated capability; refuse an incompatible required bound.

Keep the six portable `OperationState` values. Pre-claim refusal is audit only;
post-claim, pre-dispatch refusal withdraws acceptance through `CANCELLED` with a
refusal diagnostic. A consumed grant or write-ahead `RUNNING` record needs
evidence accounting for that grant, even if a caller believes no call occurred.
After dispatch, timeout, exception, disconnect, cancelled future, backend cancel
acceptance or local process death proves no remote cessation. Independently
validate effect knowledge, cessation, satisfaction and release gates. Known
quiescent nonconforming/partial effects can fail, or cancel when the cancellation
contract is established; unknown residual effects or unproved cessation remain
`INDETERMINATE` with exclusion. A validated completion can win a cancellation
race. Late evidence cannot rewrite a terminal parent; admissible new evidence
uses the existing separately authorized linked-resolution boundary.

**Budgets and recovery are authority boundaries.** Apparatus admission/queue,
execution, interruption/observation, commit/readback and drain budgets are strict,
positive, finite, stage-bound and have explicit origins. Nested work consumes
remaining budget; repeats/progress do not refresh it. Thread cancellation does
not interrupt a blocking synchronous call: retain its reservation and bound
abandoned workers/resources. Stronger interruption needs an admitted backend
guarantee or pre-effect refusal. Store busy waits, lease acquisition and close
must fit their budget, not just backend execution. Existing workflow timeout
helpers do not supply these apparatus bounds. Semantic clocks/domain/segments
remain under the existing time authority; scenario pause cannot pause supervision.
Persist portable UTC/origin evidence and budget consumption, never raw monotonic
deadlines; uncertain restart continuity cannot award a fresh full budget.

Startup acquires the incumbent owner lease before inspection and remains closed
to conflicting effects while it recovers retained grants/reservations. Bound
observation outside state cuts; reread authoritative terminal state before
classification. Missing historical evidence remains unknown. Legacy
absent/applied reports cannot be upgraded to cessation, full satisfaction or
safe continuation. An administrative snapshot acceptance records a choice,
not an external fence. A replaced owner/generation, restored database or expired
lease does not stop old work. Restore follows ADR-113's closed-admission inventory
and reconciliation rules, including effects missing from an older backup.
Close the store provider before releasing the owner lease; unconfirmed store
close retains the lease while the process lives. Effect/control adapter drain
expiry reports unresolved work to the embedder without inventing cancellation
or successful shutdown.

## Cross-cutting layers and canonical incumbents

These are obligations on the intended implementation, not claims of current
enforcement. All affected direct, served and recovered paths must pass them.

| Layer / incumbents | Required treatment |
| --- | --- |
| Source and admitted policy: `raes/{parser,_source_validation,_yaml_loader}.py`, `validator/_execution_policy.py`, `composition/_execution_policy.py`; `raes_contracts/execution_policy.py`; compiler/planner `execution_policy.py`; `planning.py` | Consume exact admitted native policy, including the existing #1361 representation; do not resolve today's defaults again or introduce a runtime policy interpreter. Preserve safe parsing, bounded expansion, closed phase models and native plan authorization. No repeat without authored permission and current evidence/authority. Reuse workflow retry, `ExecutionRetryPolicyModel`, trial allocation/cleanup and participant lifecycle owners. |
| Configuration/installation: `control_plane_configuration.py`, `ControlPlaneOptions`, `registry.py`, `registry_target_validation.py`; `raes_backend_protocols/{capabilities,manifest,backend_manifest,operation_supervision}.py` | Integrate the optional provider into the canonical target/configuration shapes and all component construction/conversion paths, including `RuntimeManager`'s target reconstruction. Match declared contract IDs to installed signatures without effect probes; check operation kind, exact requirements and current willingness again after waiting. New capacity/budget options belong in these typed apparatus settings: reject booleans as integers, coercible strings, nonfinite/zero/negative or excessive quantities before allocating resources. Do not use authored metadata, environment dictionaries or backend-name switches. |
| Contract/profile admission: `raes_contracts/{manifest_authority,versions,backend_profiles,corpus}.py`, `contracts/profiles/backend/`; `control_plane_profiles.py`, `control_plane_composition.py` | Negotiate existing carrier versions/allowlists. Backend operation support and runtime P0–P3 guarantees are different axes. Missing support cannot become best effort for a required guarantee. P1/P2's optional legacy observation may still fall back to indeterminacy; it cannot satisfy required provable cessation/recovery. P3 remains unavailable. Load packaged artifacts through `corpus`, not arbitrary paths. |
| Auth and served composition: `ControlPlaneSecurityConfig.strict_defaults()`, `control_plane_api/_auth.py`, `ControlPlaneIdentity`, `control_plane_plan_authorization.py`, `control_plane_operation_context.py` | Derive actors from trusted identity and reauthorize exact target/run/subject/disclosure scope at control, status and resolution boundaries. Bind worker service authority separately from IDs/task tokens. Preserve invalid-bearer hard refusal and explicit proxy trust. Any served route must declare `ControlPlaneRouteAuthority` and pass route/method inventory and composition sealing; no mutating GET or public supervisory shortcut. Direct calls retain the trusted embedder boundary. |
| Size/value/commitment gates: `RequestSizeLimitMiddleware`, `ContractModel`, `runtime_value_limits.py`, `backend_input_contracts.py`, `backend_call_contracts.py`, `canonical.py`, `control_plane_api_models.py` | Bound bytes, depth, numbers, collections, progress and evidence before copying/hashing/decoding domain artifacts. Validate in-process values too. Reuse strict protocol primitives and RFC 8785 request/control commitments; retain native plan/store digest conventions. DTO round trips must preserve meaning. No `repr()`, pickle, callback/future serialization or coercion to make a malformed carrier valid. |
| Secrets and environment shapes: `SecretReferenceId`, `runtime_fact_dispatch.py`, `runtime_fact_binding_policy.py`, `raes/runtime_environment.py`, `_stateful_resource_references.py`, planner `stateful_admission.py`, `backend_account_credentials.py`, `control_plane_admission.py` | Resolve authorized references only at execution and recheck visibility/freshness/sink policy on rebinding. Preserve closed environment-delivery projections: `value_from` excludes literals and `operator_secret`; redacted/operator-secret values contain no raw material. Credentials stay out of requests/history/audit/progress and durable retry proof. Credential-sensitive submission retry retains exact ephemeral proof; after restart use authorized status when that proof is unavailable. |
| Native effect/result/release gates: `backend_calls.py`, `_validated_backend_result()`, `backend_apply_results.py`, `backend_result_diagnostics.py`, realization/preparation/materialization helpers, participant flow/final-sink and native workflow/time/evaluation validators | Preserve ASR-532 predecessor isolation, changed-address accounting, plan/domain ownership, credential egress and final disclosure/release checks for normal, partial, late and recovered evidence. Resolve typed artifact references under their actual contract/digest and authorized scope. A syntactically valid backend assertion or result reference proves no physical effect or satisfaction. Unsafe results preserve trusted state and require honest effect classification. |
| Persistence/OS ownership: `RuntimeMutationAuthority`, `RuntimeDurabilityMixin`, `ControlPlaneStoreCommitAdapter`, store memory/local implementations, `control_plane_store_{records,record_migration,local_codec,paths,lease}.py` | Extend existing atomic store boundaries for durable dispatch/control/reservation facts; reuse codecs, integrity checks, CAS and scope admission. No second supervisor store or callback-owned writes. Preserve private database/WAL/sidecar paths, symlink/descriptor checks and lease-before-inspection. P1/P2 keep the single-worker/no-reload topology; P0 cannot claim restart durability. |
| Errors/audit/observability: `Diagnostic`/`DiagnosticModel`, `portable_diagnostic_payload()`, `operation_terminal_diagnostics()`, `AuditEvent`, `control_plane_audit.py`, `control_plane_api/{_responses,_operation_routes}.py`, `NoStoreResponseMiddleware`, `control_plane_health.py`, `operational_apparatus.py` | Reuse stable value-free refusal/terminal/error envelopes and module loggers; do not create another exception hierarchy. Preserve redacted 422/500, non-revealing unknown/unauthorized-operation responses, conflict labels, best-effort secondary denial audit and uncacheable responses. Never expose raw exceptions/chains, validator input/error dictionaries, provider type names, tokens or backend locators. Bounded text is not redaction. Durable accepted controls need authoritative audit, not best-effort success. Readiness reflects retained reservations/uncertainty, including after administrative resolution. Keep operational progress, participant observation and archival evidence distinct under ADR-066. |
| Host and execution delivery: existing reference/libvirt backend drivers, `RuntimeManager`, embedders; Python package/tooling locks and artifact policy | Use backend-owned process/job control when needed. No request-supplied commands/endpoints/executable paths, shell wrapper, token in argv, broad environment inheritance/dump or store credentials in hostile workloads. Killing a local worker proves no remote cancellation. Distributed workers require configured authenticated endpoints and scoped credentials; Temporal replay code excludes nondeterministic store/clock/secret/backend calls. Dependency changes use existing locks, license/provenance and supported-platform policy; architecture selection is no approval to provision services or transfer data. |

The extensibility seam is the **versioned native requirements/effective policy
plus contextual operation-provider admission**, with separately configurable
effect/control capacity and stage budgets in the owning runtime composition.
This permits a future backend interruption/observation guarantee or execution
adapter without another lifecycle or backend-specific policy branch. Required
continuation remains refused until an actual compatible contract, boundary and
provider exist; method presence or a durable snapshot supplies none.

## Compatibility, assurance and boundaries

Whole-repository consumers include the contract corpus and schemas/manifests,
registry/manager and control-plane compositions, backend stubs/reference/libvirt
drivers, workflow/participant/mixed-runtime controllers, operation receipt/status
DTOs, store reopening/maintenance, served route/security inventory, and CLI/MCP
operation readers. Preserve facade exports and old closed receipt/status readers.
Persist new facts through a versioned strict migration in the incumbent store;
do not hide them in free-form `result_payload`, drop them on reopening, fabricate
historical generations or rewrite terminal history. Published schema changes
follow ADR-009/061: keep `schema_bundle()` identical and update the current v2
`contracts/schema-publication/entries/` hashes/`last_change` records (independent
tombstones for removals), not the historical monolithic publication ledger.

Reuse the existing Event/barrier and real-store/crash fixtures rather than
sleep-based race demonstrations: tests for #1181 unified mutation, #1180 CAS,
#1184 claims, #1183 leases, #1179 startup recovery, #1186 linked resolution,
#1187 durable/security/process-loss/profile conformance, and #1092 crash
consistency; `control_plane_{conformance,crash}_fixtures.py`; #1360 protocol and
#1361 policy tests. The #1348 finite model is a semantic oracle, not evidence
that installed workers or backends can stop.

Required witnesses cover blocked admission/check/apply/control/observer/release
callbacks; saturated effect capacity with authorized and unauthorized control;
stop-versus-dispatch and cancellation-versus-completion races; duplicate/changed
requests, late/stale generations and revision/history conflicts; exceptions
after partial effects; malformed/leaking evidence; failed/uncertain store
acknowledgements; and crash on both sides of grant, dispatch and terminal commit.
Reopen the actual store and establish that consumed grants are not reissued,
control actors/budget origins/sequence/exclusion survive, legacy/admin-resolution
paths cannot invent cessation, and no recovered path repeats uncertain effects.
Bound blocked tests and release their workers reliably. Exercise each supported
composition against real adapters; distributed machinery requires CI integration
evidence, not claims extrapolated from local/model tests.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `noxfile.py`,
`tools/verification_plan.py`, `tools/check_repo_policy.py`, ADR pin and
`tools/check_{generated_schemas,schema_publication,schema_coverage}.py`.
Preserve ADR-015/036 package import boundaries and source caps; publish semantic
schema obligations through `raes_contracts/contracts/schema_invariants.py`.
Dependency/configuration consumers include `implementations/python/{pyproject.toml,uv.lock}`,
`implementations/tooling/profiles/development-profiles.json`,
`implementations/tooling/artifacts.lock.json`, their owning closure/artifact
generators and checks, and `.github/workflows/canonical-verification.yml`.
Set `RAES_REQUIREMENT_UID=API-404` on this branch, whose name has no UID; retain
the existing requirement status and keep implementation/test traceability
accurate. Run relevant targeted checks locally; full, integration, fuzz and
completion suites remain CI/CD responsibilities. Source-bound research evidence,
if needed, follows
`tools.research_capture` and `docs/develop/research-captures.md`, not hand-edited
numbered publication history.

Non-goals are a second scenario/workflow interpreter, generic supervisor/broker
or checkpoint framework, duplicate schema/validation/error/audit systems,
automatic replay/rollback/compensation/new-trial allocation, new SDL policy
syntax, active/active or offline multi-writer operation, P3 activation, universal
backend interruption, hard-real-time/physical safety certification, and service
provisioning. Avoid timer-only cancellation, dropping a logical permit without
effect exclusion, daemon-thread disposal as shutdown, queue labels as
authorization, and accepting a snapshot as proof of external cessation.
Implementation is confined to enforcing the accepted execution/public operation
protocol through the existing runtime and adapter boundaries, with the necessary
configuration, persistence, compatibility, truthful reporting and evidence.

The additional implementation review identified a privacy constraint at command
publication: an exact unkeyed native-plan digest can depend on account credential
material. The adapter therefore binds the exact native plan with standard
HMAC-SHA256 and a random process-private owner key. Its artifact authority
recomputes that commitment before granting dispatch and accepting finalization.
The pure policy helper preserves canonical native-plan validation by default;
the protected owner supplies its freshly resolved commitment explicitly.
Keys and unkeyed credential-dependent plan identities are never ledger or
engine-history facts. Reopening retains opaque identity and uncertainty, and
cannot regenerate private command authority. Canonical request/control and
native plan/snapshot projection rules remain intact.

Finite invocation history partitions automatic and operator controls, reserving
cancellation and reconciliation capacity independently of observation traffic.
Automatic polling uses the admitted execution budget to choose a cadence within
its retained allowance. Separate ordinary-response limits reserve recovery and
terminal facts. Category exhaustion refuses new intent; retained controls,
responses and consumed delivery identities remain append-only across reopening.
