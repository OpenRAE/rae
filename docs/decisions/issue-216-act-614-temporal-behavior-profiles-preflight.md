# Issue #216 — ACT-614 Temporal Behavior Profiles Preflight

Date: 2026-09-21

Scope: ACT-614 and the simulated-user authoring cases consolidated from #659.
`DSL-009` is historical issue context, not a requirement to create. This is
architecture guidance, not an implementation plan or a claim of completion.

## Decision and authority

Reuse [ADR-092](adrs/adr-092-autonomous-benign-participants-under-shared-time.md),
the [autonomous execution specification](../../specs/formal/participant-semantics/autonomous-execution.md),
SEM-213, and the shared-time authorities in ADR-090/091. No new ADR, participant
kind, temporal-profile root, scheduler, or clock is justified. The
[ACT-605 preflight](issue-213-act-605-baseline-behavior-profiles-preflight.md)
supplies the common execution/security boundaries; its ACT-605 completion
finding is not evidence that ACT-614's additional cases work together.

| Requirement / #659 case | Existing owner and boundary |
| --- | --- |
| User role and activity | Ordinary participant declarations, action contracts, observation boundaries, and `ParticipantBehaviorSpecification.autonomous_execution`. Non-evaluated policies require `green`; business personas do not create authorization roles or evaluator authority. |
| Fixed cadence | `ParticipantAutonomousExecutionPolicyV1`: exactly one shared-clock cadence and `ordered_cycle`; preserve v1 defaults and digests. |
| Work/pause schedules, bounded intervals, dependencies, retries, cooldowns | V2 activity policy and `raes_runtime.participant_activity`: finite shared-time windows, keyed candidates, integer weights, and bounded attempts/occurrences/bursts. |
| Resource-governed activity | V3 adds scoped resource accounting to v2; it does not add a new time model or imply all older profiles require v3. |
| Dwell, deadlines, latency, reset/replay semantics | Action-level `raes.participant_temporal_semantics`, compiled temporal contracts, backend timing disclosures, and temporal history/state validation. These are distinct from occurrence spacing and native execution timeouts. |
| Application/protocol | Existing action effects/preconditions, node/service refs, implementation selection, and exact `participant-execution-binding/v1` relations. An application label is neither executable action nor proof of protocol fidelity. |
| Scenario parameterization and reuse | `parse_sdl_file`, `raes.composition`, `instantiate_scenario`, admitted instantiated artifacts, and canonical compilation. Within-run `agent-policy` randomness is separate from scenario-family variation. |

Behavior classification, when needed, stays in the existing concept-authority
binding surface described by ACT-611; it must not become another behavior enum
or participant ontology.

Scenario syntax and semantic validity are independent of backend support.
RAES owns those semantics, portable contracts, admission and conformance;
backends own native realization and operations. An adapter is needed only at
a distinct translation boundary. An insufficient manifest rejects the selected
scenario/backend pairing, not the scenario or the backend. This applies to all
authored semantics, not only timing. No temporal feature set, scheduler design,
or control-plane architecture is mandatory for every backend; profile-specific
obligations apply only when that profile is claimed. Examples are workloads,
not ceilings on backend capability.

## Concrete integration risks

The source findings below are not new execution evidence. The supplied issue
also confirms that a policy with a deadline at tick 5 executes again at tick 10
and reports success. Preserve that exact regression as required implementation
evidence; this preflight has not independently reproduced it. Documentation
reconciliation alone cannot complete ACT-614.

- **Temporal identity and enforcement.**
  `participant_scheduler_operations._bound_action_request` constructs contexts
  from shared-time constraint addresses with fixed submit/start/end/observed
  event points. `raes_processor.models.behavior_anchor_checks` instead checks
  contexts against action-local `temporal_id`, clock/domain, exact event points,
  disclosure refs, and reset/replay boundaries. A shared `time.constraint.*`
  address and an action-local temporal id are not interchangeable. Demonstrate
  their intended relationship through execution and conformance before claiming
  dwell/deadline support. Do not suppress history validation or fabricate
  matching declarations to hide a mismatch.
- **Abstract transitions are not runtime enforcement.**
  `iter_participant_temporal_state_machine_violations` checks transition
  sequences; the inspected package has its definition/export but no runtime
  caller. `participant_scheduler_time.cadence` selects cadence; carrying other
  constraint refs into history does not prove their enforcement. Existing
  SEM-213 tests validate contracts and synthetic transitions, while DSL-437
  tests exercise autonomous scheduling. Their separate success would not prove
  a dwell/deadline spanning multiple shared ticks, a missed deadline, or
  terminal-state isolation across reset. Attribute a demonstrated gap to the
  owning temporal/admission/execution boundary, not a second scheduler.
- **Support lists do not establish a supported combination.**
  `capability_admission._autonomous_execution_binding_gaps` currently matches
  action, implementation, targets and attempt/in-flight limits;
  `time_model_capability_gaps` checks time-kind and lifecycle support. Neither
  alone establishes a particular action/event deadline or dwell guarantee.
  Reuse `participant_feature_admission.resolve_participant_feature_support`
  for support strength, required contracts and evidence, with existing planner
  diagnostics in `planner/core.py`. Extend the existing typed admission seam
  to check the requested combination of bindings, limits and evidence strength;
  do not infer it from independent lists or a generic `temporal_contracts`
  claim. A limitation disclosure is not permission to weaken the scenario.
- **Imports must preserve references.**
  `composition/_behavior.py::_rewrite_behavior_specification` rewrites parent
  refs and the autonomous resource budget, but does not visibly rewrite the
  nested clock/progression, action/candidate, observation, window, stochastic,
  and evaluation refs. Verify namespaced imports, repeated module instances,
  exported/private names, and bare/section-qualified refs. Use the existing
  symbol maps and reference helpers through `_rewrite_payload_with_symbols`,
  shared by composition and semantic transformations. Preserve local candidate
  ids and external implementation identities rather than prefixing every string.
- **Parameters must survive source admission.** Autonomous interval, weight,
  cooldown, and limit fields currently use bounded `int` fields. Generic
  substitution in `instantiate.py` does not establish that `${...}` reaches
  that phase. Check actual source-model acceptance, typed whole-field binding,
  unknown/missing variables, and post-binding semantic validation. Reuse
  `_base.py::WholeFieldVariableReference`, `parse_int_or_var`, the schema marker and
  instantiation provenance for supported numeric fields. Defer only checks
  depending on unresolved operands; rerun interval ordering, retry consistency,
  occurrence/burst limits and v3 concurrency equality after binding. Reject
  booleans, fractional/non-finite values, out-of-range integers and partial
  numeric interpolation. No text templater, `eval`, unchecked coercion, or
  runtime parameter bag. Schema parity remains mandatory.

## Bounded temporal guarantee boundary

Bindings belong to existing action temporal contracts and shared-time
declarations. Keep action-local temporal ids, compiled constraint addresses,
action-instance identity and observation evidence distinct. The shared-time
specification explicitly forbids inferring a binding from matching legacy
`clock_authority` strings. Resolve clock/domain, subject, event and constraint
kind explicitly; use existing exact integer/rational coordinates and mappings.

- **Deadline:** declare whether the constrained event is start, completion,
  observed effect or effective effect, its reference event/absolute bound and
  equality rule. Check admission for an expired start bound, and evidence at
  outcome acceptance for completion/effect bounds. The current SEM-213 shape
  requires `deadline` plus `end`, `observed` or `effective`; a start-only
  deadline therefore needs explicit governed contract evolution, not invented
  end evidence. Dispatch time cannot stand in for completion/effect time.
- **Dwell:** bind a condition using existing action/precondition and observation
  authorities, an interval, and the evidence strength required over that
  interval. Waiting, cooldown, or two successful endpoint observations does not
  establish continuous satisfaction. Sampled evidence proves only its declared
  sampled guarantee. Interruptions, missing coverage or untrusted observations
  cannot yield success; reject a continuous guarantee when the selected backend
  cannot supply adequate evidence. A bounded interval needs no monitoring service.
- **Lifecycle:** specify how pause affects elapsed time and condition coverage;
  a frozen logical clock does not freeze a native service. Reset/replay cannot
  carry terminal state or accumulated dwell into a new episode/segment without
  the declared semantics and lineage. Evidence and any bounded continuation
  must bind the action instance, episode, clock segment, execution generation
  and policy/contract identity. Check serial and concurrent completion paths;
  late or stale work cannot update the current generation.
- **Outcome:** a missed guarantee, native failure, cancellation and rollback are
  distinct. Rejecting a late portable result does not undo native effects;
  cancellation requires its own declared support and evidence. Do not invent
  compensation or retry indeterminate effects automatically. Retain the native
  outcome/missed guarantee distinction in governed evidence without accepting
  invalid or stale success into current history.

These are contract obligations for the bounded reference path. They do not
prescribe backend worker architecture or introduce resumable, general-purpose
long-running actions. Preserve old meanings and digests; version a changed
meaning and its admission/history contracts rather than silently reinterpreting
v1/v2/v3 or tightening all legacy descriptive SEM-213 contracts in place.

## Cross-cutting layers the design must pass

Paths below are relative to `implementations/python/packages/` unless stated
otherwise. Each existing gate remains authoritative at its own boundary;
do not copy its rules into an ACT-614 validator.

| Layer / canonical incumbent | Required treatment |
| --- | --- |
| Source ingress: `raes/parser.py`, `_yaml_loader.py`, `_source_validation.py`, `SDLParserLimits`, `SDLModel` | Retain safe YAML construction, duplicate/merge-key policy, byte/node/depth/alias limits, and closed fields. Imported examples use file-backed parsing and existing path, lock/trust, cycle, and composition-budget checks. No new URL loader or arbitrary file reader. |
| Composition and instantiation: `raes/composition`, `raes/instantiate.py`, `admit_instantiated_scenario` | Preserve namespace ownership, parameter types/constraints, provenance, and final revalidation. Compile the admitted instantiated artifact; unresolved placeholders cannot reach scheduling. |
| Semantic authority: `raes/semantics/participant_behavior`, `raes/validator/_participant_execution_renderers.py`, `_time_model.py`, resource-owner validation | Resolve participant/action/observation/clock/progression/constraint/implementation refs; reject widening of parent authority, wrong clock/subject, duplicate scheduler owners, dependency cycles, unreachable ticks, and incompatible evaluation/resource ownership. |
| Compilation: `raes_processor/compiler/participant_behaviors.py`, `participant_contracts.py`, `participant_autonomous_execution.py`, `time_model.py` | Reuse canonical address helpers, runtime models and contract digests. Preserve resolved semantics, not just reference strings; policy/time changes cannot resume an old continuation silently. |
| Configuration and secrets: `ConfigurationTargetRegistryModel`, `raes_contracts/participant_configuration.py`, `secret_references.py` | Preserve typed literal versus secret-reference disposition, registry constraints, owner normalization, selected implementation/configuration identity and digests. A portable profile carries no resolved credentials or raw entropy. Binding an application does not authorize secret access. |
| Node environment, if an example needs it: `raes/runtime_configuration.py`, `runtime_environment.py`, `runtime_generated_value.py`, `_stateful_resource_references.py` | Retain unique env names, literal/value-from exclusivity, source/output resolution, and classification/redaction checks. Generated secrets require `redacted`, cannot claim `operator_secret`, and cannot consume `producer_private` output. Env-file names use `PortableIdentifier`; profiles must not introduce an env-based timing override. |
| Backend admission: `raes_backend_protocols.capability_admission`, `participant_feature_admission`, manifest models/adapters, `raes_processor/planner/core.py`, `RuntimeTarget` / `BackendRegistry` | Require the authored combination of profile, feature, action-target-implementation relation, strategy, clock/event binding, evidence strength, time/random/resource support and finite limits. Keep semantic errors separate from admission diagnostics. Reject insufficient pairings before native effects. Reset and execution-service claims require their capability-specific protocols; unrelated workloads remain admissible. |
| Evidence and native-effect authority: `raes_runtime/observation_admission.py`, `participant_effect_authority.py`, `participant_crossing_policy.py`, `participant_action_validation.py`, `backend_snapshot_contracts.py` | Dwell/effect evidence must remain within authorized observation boundaries and participant flow policy. Reuse required-demand, exact selector, retention/durable-owner checks where observation demand is used; do not synthesize coverage from a selector. Bind effects to the submitted participant/targets; retain typed result, history/provenance and bounded snapshot-shape checks before accepting backend state. |
| Runtime and host: `ParticipantScheduler`, `participant_activity`, `ParticipantClockDriver`, native participant protocols | The shared clock owns admission and lifecycle. Native adapters remain impure leaves with existing target/configuration boundaries. No cron, private timer, host calendar/timezone, daemon, or new process surface is needed. If an existing adapter invokes a process, retain bounded execution and controlled environment/cwd, fixed argument structure without shell interpolation, and keep credentials/entropy out of argv and output. A rejected portable commit cannot undo a native side effect. |
| API security: `create_control_plane_app`, `ControlPlaneSecurityConfig.strict_defaults`, `control_plane_api/_auth.py`, API guards | Retain bearer/verified-proxy identity, role/target and participant-subject/audience authorization, request limits, idempotency/fingerprints, and audit. Profile presence grants no control/evaluation/observation authority. No new endpoint or controller is implied. |
| Error envelopes and observability: `SDLParseError`, `SDLInstantiationError`, `SDLValidationError`, `Diagnostic`, `portable_diagnostic_payload`, `AuditEvent`, API `_operation_routes.py` / `_responses.py` | Reuse bounded diagnostics and typed receipts/history. Preserve redacted 422, 409 and 500 responses; do not leak Pydantic inputs, raw adapter/store exceptions, tokens, entropy, command output, paths or tracebacks. Logs/audit report safe ids, codes, counts and durations; they are not temporal evidence. No new exception hierarchy or logger. |
| Persistence: `RuntimeSnapshot`, `raes_contracts/participant_autonomous_state.py`, `require_participant_autonomous_runtime_snapshot`, `ControlPlaneStore` and its local/memory implementations | Use typed scheduler, execution-service, resource and shared-time carriers plus append-only behavior history. Retain generation/episode/segment, policy digest, revision/conflict, save/load/API/conformance checks. `control_plane_store_snapshots.py` has an exhaustive field codec; `control_plane_store_local_snapshot.py` uses transactional revision compare-and-swap and digest-checked payloads. Any continuation must survive these boundaries and reject inconsistent durable state. No continuation in metadata, new store, or success inferred from persistence alone. |

Keep the runtime plan bound to the admitted manifest, target and predecessor
snapshot through `manager_plan_admission.runtime_plan_precondition_diagnostics`.
Do not let a restored plan or backend switch reuse obsolete admission. Existing
control-plane leases, operation idempotency and indeterminate-operation recovery
remain the workflow owners; a temporal receipt must not become a second job
queue. Bound pending evidence/continuation and retained history through existing
resource and payload limits, including at restart, not only per-action timeouts.

Timing units and boundaries are semantic, not presentation details. V2 windows
are half-open; positive interval bounds are inclusive. Preserve the existing
microstep handling, stepped reachability, explicit outside-window and
empty-eligibility dispositions. Missed cadence must not silently catch up;
pause/reset races and stale native completions must remain generation fenced.
Runtime-owned real-time/dilated pacing uses the existing driver; externally
paced autonomous policies remain unsupported until their transition contract
exists. Backend pacing/latency limitations need typed disclosures.

Retries use the existing portable `ParticipantFailureClass` (including
`TIMEOUT`), finite bounds and predecessor identity. Protocol-invalid or
indeterminate native work is not automatically retried. Dwell is not cooldown,
a logical deadline is not a host wait timeout, timestamp order is not causality,
and replay is not service rollback. Preserve SEM-211/212 boundaries.

## Evidence, extensibility, and repository workflow

The existing evidence families are
`test_sem_213_temporal_participant_semantics.py`,
`test_dsl_437_benign_participant_execution.py`,
`test_dsl_437_evaluation_authority.py`,
`test_dsl_437_snapshot_durability_conformance.py`,
`test_issue_898_participant_execution_control.py`, and
`test_issue_899_participant_resource_budgets.py`, plus parser, instantiation,
module composition, API security, and generated-environment consumer tests.
Reuse their fixtures and conditional native conformance probes. Evidence for
#216 must distinguish source acceptance, compilation, admission, actual native
outcome, temporal history, and durable round-trip; a happy-path parser or mock
receipt does not prove all of them. This preflight has not run those suites.

The extension seam is existing data: typed scenario variables/module arguments
for timing bounds and references, keyed action candidates for another activity,
and exact backend execution bindings for another application. Event/constraint
bindings and required evidence strength belong in governed portable contract
data so another bounded guarantee does not require backend-name branches or
editing a canonical example. Keep timing in portable policy and native
realization in its owning backend. Reuse governed
`agent-policy` random controls, addressed draws and bounded-integer transforms;
no mutable RNG, retry-dependent draw address, or new seed field. A genuinely
new temporal meaning requires governed contract evolution with exact admission
and durable evidence, not optional fields that reinterpret v1/v2/v3.

Admission evidence must include the same valid scenario with insufficient and
sufficient manifests, absent/partial/rich support, unsupported combinations and
insufficient evidence. Exercise the actual tick-5/tick-10 path, equality and
microstep boundaries, interrupted dwell, pause/reset races, stale completions
and corrupt continuation across compilation, execution, history and persistence.
Conformance exercises claimed capabilities; its fixture manifest must not make
every backend implement the richest profile. Reuse existing API-421/shared-time,
feature-admission and observation-admission tests alongside the families above.

Whole-repository surfaces include `specs/formal/participant-semantics/`, shared
time specifications, `contracts/schemas/`, publication entries/manifest and
fixtures, the packages above, `examples/library/` and `examples/scenarios/`,
backend protocols/conformance, tests, and workflow tooling. Portable examples
should reuse the participant evidence-loop/action-contract and timed-run
examples, clearly disclose reference-versus-native support and bounded logical
schedules, and pass `tools/check_example_library.py` where applicable. Do not
turn test-only manifest construction into a production capability claim.

Follow `.ground-control.yaml` and `.gc/plan-rules.md`, with
`RAES_REQUIREMENT_UID=ACT-614`. Use existing targeted checks and canonical nox
lanes; CI owns full verification. `tools/check_repo_policy.py`,
`tools/check_public_docs.py`, `tools/check_schema_publication.py`,
`tools/check_generated_schemas.py`, publication entries/manifest and
ADR immutability checks remain the incumbents. The old SEM-213 preflight's
generator-first schema advice is superseded by current policy: published
schemas are authoritative, changes require the publication ledger/content
hash (and tombstones for removals), and `schema_bundle()` must match. An
accepted ADR amendment requires its amendment row, index entry and content
pin under ADR-059; no such amendment is needed for this note.

Reconcile ACT-614 `DOCUMENTS`, `IMPLEMENTS`, and `TESTS` links separately from
actual evidence. Do not infer completion from closed #213, an accepted ADR,
the requirement's `SHOULD` priority, or a backend capability flag. This note
does not alter requirement status or external traceability.

## Non-goals

No implementation in this preflight. The issue includes authoring and admission
repairs plus bounded bindings, enforcement/evidence, lifecycle validation and
conformance in existing owners; it is not documentation-only reconciliation.
Changes may cross contracts, compilation, runtime checks and history/persistence
consumers. No feature implementation is mandated in LilRAE, BigRAE or any other
backend. A second time authority and a general long-running action engine are
explicitly outside the delivery boundary.
Backend-native user activity (historically `Brad-Edwards/aptl#436`), browser or
protocol automation engines, human realism, recurring calendar/DST semantics,
new service daemons, experiment allocation, scoring, and cross-backend
exactly-once/rollback guarantees are outside this issue's portable boundary.
Do not duplicate schemas, DTOs, validation, scheduler/workflow logic, stores,
error handling, observability or conformance machinery to obtain ACT-614-named
artifacts.
