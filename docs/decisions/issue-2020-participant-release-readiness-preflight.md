# Issue 2020: Release autonomous participants when the range is ready

Status: architecture guidance for issue #2020; no implementation or release claim.
Source revision: `06557f7f0ed33978f4afdc47454f4f051a092c5a`.
The supplied issue is the contract. There is no formal requirement UID.

## Decision

Reuse `agents.*.starting_assertions` as the SDL release precondition.
Reuse propositions, precondition assertions, and `proposition-truth-result/v1`
for backend reports about that precondition. Add a scoped runtime entry for reports.
Enforce the gate in the existing scheduler.
One shared assertion can release several participants.
Different assertions can release separate groups. All declared starting assertions must be true.

A readiness claim sent after handoff uses an observed-state proposition.
Its subjects must resolve in SDL. It needs a stable property semantic reference
and evidence requirements. The backend reports after its native setup is complete.
For LilRAE, that includes tool servers, SOC seeding, and participant configuration.
RAES does not perform or inspect those native steps.

The runtime accepts reports only for the installed producer and admitted
target, run, declaration, and release generation. A payload cannot grant itself
authority. A report and its references do not independently prove native truth.
Do not invent a synthetic SDL `range` subject: reuse canonical subject resolution.

This applies [ADR-079](adrs/adr-079-backend-neutral-proposition-and-truth-semantics.md)
and [ADR-092](adrs/adr-092-autonomous-benign-participants-under-shared-time.md).
No new authoring field is justified by this issue.
Empty starting assertions preserve the existing absence of an authored wait.
That compatibility case does not prove readiness or satisfy a declared observed precondition.

## Existing behavior and the missing boundary

Paths in this section are relative to `implementations/python/packages/`.

- `raes/agents.py` already declares `starting_assertions`.
  `raes/validator/_propositions.py` requires references to precondition assertions.
  `raes/_reference_targetability.py` owns eligible proposition subjects.
- `raes_processor/compiler/participant_behaviors.py` already resolves
  `starting_assertion_addresses` on `ParticipantBehaviorRuntime`.
  Those references currently create dependencies, not runtime release enforcement.
- `raes_runtime/runtime_run_driver.py::APPLICATION_PHASES` is shared by synchronous
  apply and durable run progress. New episodes initialize before evaluation.
  Actions start after orchestration. A guard on only the final phase is too late.
- `participant_scheduler_initialization.py::_ensure_participant_episode` invokes
  the backend's native `initialize`. `participant_execution_control.py` also
  runs due actions and starts `ParticipantClockDriver` during apply.
- `participant_execution_scheduler_state.py` currently constructs ready,
  running service state. Reset and clock resume can also restore admission.
  These are service lifecycle facts, not proof of range readiness.
- `proposition_truth_contracts.py` validates truth results against admitted
  proposition/assertion entries. It does not establish trusted reporter identity,
  run freshness, or the release transition by itself.

The first authority trap is in `backend_snapshot_contracts.py`:
`proposition_truth_results` belongs to evaluation; snapshot `metadata` belongs
to runtime. `backend_effect_transitions.py` checks each call's owner, targets, and operations.
It also rejects writes against unchanged plan entries.
A provisioner cannot report readiness by changing either dictionary in its
ordinary `ApplyResult`. Do not weaken those checks to make a report fit.

`raes_processor/planner/manifest_validation.py::_validate_evaluation_support`
also requires an evaluator whenever propositions or assertions exist.
`EvaluatorCapabilities` validates predicate families, quantifiers, all truth
outcomes, evidence channels, time domains, and binding provenance.
It currently requires scoring or objective support as well.
Keep that installed, truthful capability path.
Never invent a scoring claim or bypass this gate for a backend that only reports readiness.
A report-only backend without an evaluator needs an explicit capability-contract
extension, rather than a local runtime exception to this gate.
Boolean predicate support alone does not prove support for the ready property.
Resolve its exact installed probe binding and evidence channels.

## Release and lifecycle invariants

Check release before native episode setup or execution-service start.
Check it before action binding, action admission, and tool effects from participants.
Inert policy setup can occur earlier.
The same boundary must govern apply, direct lifecycle calls, scheduler passes,
clock advance/resume/reset, durable continuation, and recovery.
One runtime helper decides release from the store's current state.
Routes, workers, and backend adapters must not each interpret the condition.

| State or input | Required behavior |
| --- | --- |
| Missing result, false, or unknown | Keep the participant waiting; perform no native participant start. A negative assertion does not turn missing evidence into true. |
| Unsupported observation capability | Refuse execution admission with a diagnostic. Do not wait forever for an unavailable producer. |
| Malformed, foreign, stale, or contradictory report | Refuse the report without changing the admitted state or launching work. |
| All starting assertions true at the admitted start boundary | Claim the release transition once, then use the existing supervised participant lifecycle. |
| Duplicate report or progress delivery | Return the retained disposition under the original actor and scope. Do not initialize another episode or repeat native work. |
| Stop, teardown, run retirement, or an unresolved native start | Keep ordinary lifecycle and uncertain-effect fences effective. A late ready report cannot resume a stopped run. |
| New provisioning incarnation, changed precondition meaning, or new episode/reset generation | Revalidate the release basis. An old report must not release the new incarnation. |

Readiness is a start precondition, not a continuous invariant or a new pause signal.
After release, native failure, health, drain, cancellation, and teardown retain
their existing owners. Do not add automatic rollback or restart on readiness loss.
At a later episode start, check its current admitted basis again.

Bind the release basis to the target and run.
Include compiled participant and assertion addresses and declaration content.
Also bind it to the provisioning incarnation and the relevant lifecycle generation.
Use existing operation commitments, policy digests, generations, and shared-time
segments where they carry those identities. A timestamp or assertion name alone
cannot prove freshness. Unrelated snapshot changes need not make a report stale.
Compare the store revision on each commit to prevent races.

Extend the canonical digest if the scheduler retains the release basis.
`_policy_digest` currently hashes a selected field set.
A new dataclass member alone will not change that digest.
Changed proposition content under the same address must not preserve an old release.

## Reporting, progress, and persistence

Expose a small typed runtime operation for reports after provisioning returns.
It takes the existing truth-result carriers.
Its trusted context supplies producer authority and the release basis.
Those facts are absent from the truth-result envelope.
It admits only the addressed assertions and their result updates.
It cannot replace the snapshot, grant general evaluation authority, or rewrite history.
Use existing manifest/capability admission and target shape checks for any
installed reporter binding. Reuse the existing evaluator role and its admitted
truth capabilities; add no separate readiness service.

Keep native report production separate from participant dispatch.
Commit the report before release. A failed or conflicting report commit must not start participants.
Re-read and claim the release against the
current state before dispatch. Persist the start claim before native work.
Use the existing invocation ledger and uncertain-effect recovery if a start
completion or acknowledgement is lost. A successful report is not successful startup.

Waiting must leave the backend free to finish preparation and submit its report.
Do not block the provisioning call, hold a runtime mutation lock while waiting,
or require the backend to call back into an unfinished apply transaction.
Retain early valid reports without dispatch until prerequisite phases commit.
Their proposition and assertion entries must already be admitted.
Unknown declarations still fail the existing truth-result checks.
Expose the wait through progress and readback.
Keep it distinct from failed provisioning and a successful start phase.
Durable progress must not record that start phase as complete while it is waiting.
Synchronous resource handoff must expose the wait without claiming participants are running.
A readiness producer must work before release.
Do not depend on actions or observations that require the waiting participant to start.
Reject known dependency cycles through the existing compiler graph checks.
Do not hold worker capacity or native in-flight reservations during the wait.

Use `RuntimeRunContext`, `runtime_run_driver`, `control_plane_mutation`,
`ControlPlaneStore`, snapshot revision CAS, owner leases, actor-scoped idempotency,
and atomic operation/snapshot/audit commits. P0 retains its in-process guarantee.
Durable guarantees depend on the selected store profile.
Reuse local/PostgreSQL codecs and recovery admission. Do not add another store,
queue, event bus, polling thread, or Temporal workflow.
Temporal may drive existing progress. It must not interpret assertions or retry effects.

Keep a waiting participant's attempts, random draws, reservations, and action
history untouched. Reuse service readback with `not_ready` and
`accepting_new_work=False` where its contextual invariants permit it.
Do not publish synthetic ready evidence or refer to nonexistent scheduler states.
Keep any retained release state consistent across public snapshots and durable codecs.
Concurrent snapshot merging and conformance must use the same state.
Scheduler loops currently expect initialized state for every policy member.
Waiting members must be represented or skipped consistently in serial and
concurrent paths, without withholding released members of the same policy.

Shared-time cadence is a design constraint, not a polling detail.
`participant_scheduler_time.py` rejects missed cadence points.
The clock driver selects due ticks from scheduler state. A delayed release must not create stale
tick-zero work, consume random draws while waiting, or spin on an overdue tick.
Keep authored cadence/window semantics and shared-clock authority.
Use admitted future boundaries or explicit existing lifecycle controls; do not
silently rebase time, reset a shared clock, or catch up missed native actions.
Do not freeze unrelated participants that share a clock.
If the start boundary has expired, report that disposition explicitly.

## Cross-cutting gates

These are required boundaries for the intended implementation, not optional checks.
Python owners below remain the behavior reference until the Go cutover.

| Layer | Canonical incumbent and required treatment |
| --- | --- |
| SDL parsing and configuration shape | `raes.parser`, `SDLModel`, `Scenario`/`InstantiatedScenario`, `_propositions`, named-reference resolution, and `ReferencePurpose.OBSERVATION_SUBJECT`. Reuse closed models, variable instantiation, precondition-role checks, and compiled addresses. No strings evaluated as code, shell probes as truth, or route-local semantic parser. |
| Truth and evidence | `raes.propositions`, `raes.semantics.propositions`, `PropositionTruthResultModel`, and `proposition_truth_contracts`. Preserve polarity, false/unknown/unsupported distinctions, evidence requirements, probe identity/digest, temporal context, and loss limits. Only admitted true assertion outcomes release participants. Observed preparation cannot be replaced with declared-state truth or `evaluation_results.passed`. |
| Contract ingress | `raes_contracts.json_ingress`, `ContractModel`, portable value limits, canonical JSON/digests, published schema validation and contextual admission. Bound report size, depth, member counts, identifiers, and duplicate input. A valid DTO alone establishes neither producer authority nor current truth. |
| Backend attachment and invocation | `RuntimeTarget`, `BackendRegistry`, `registry_target_validation`, manifest/profile admission, `backend_calls`, `backend_input_contracts`, and backend result/transition validators. Validate any changed callable shape at registration and revalidate detached arguments/results at invocation. Preserve carrier ownership, exact effect targets, and changed-address accounting. |
| Authentication and authorization | `control_plane_security`, `control_plane_api/_auth.py`, and `control_plane_operation_context`. SDK possession remains privileged host authority. A served report uses administrative mutation admission, exact target/run and reporter scope, followed by core authorization. Participant credentials cannot report readiness. Keep actor/scope checks on replay and readback. |
| HTTP, if exposed | Existing route-authority inventory/composition seal, `control_plane_api_guards`, `_offload`, and `_responses`. Preserve body/capacity limits, strict request shape, redacted 422/500 responses, fixed refusal details, and `Cache-Control: no-store`. Keep `/health/ready` a value-free control-plane probe. A new HTTP route is not required to meet SDK reporting acceptance. |
| Secrets and environment binding | `SecretReferenceId`, `ConfigurationTargetRegistryModel`, `RuntimeEnvironmentVariable`, runtime configuration validation, `backend_account_credentials`, and `runtime_fact_binding_policy`/`RuntimeFactDispatchCommand`. Readiness carries identities and protected evidence references, never tool configuration, tokens, prompts, or credential values. Any new apparatus option belongs in typed `ControlPlaneConfiguration`, not an arbitrary environment map. |
| Host and OS | ADR-115 leaves native servers, SOC seeding, files, credentials, and atomic configuration publication with the backend. Add no native subprocess, file sentinel, daemon discovery, remote callback locator, or RAES credential loader. Keep tokens out of argv, URLs, environment dumps, exception text, access logs, and fixtures. Readiness reporting introduces no new listener or external data transfer by default. |
| Errors and observability | ADR-116, `raes_contracts.errors`, `Diagnostic`, `portable_diagnostic_payload`, `backend_result_diagnostics`, `get_logger` and `foreign_failure_record`. Use existing categories and bounded reason codes. Audit report admission and release separately; distinguish waiting, accepted report, claimed start, and observed running. Do not log full reports, foreign exceptions, payload validation values, paths, or secret material. No new error hierarchy or telemetry framework. |
| Persistence and recovery | Existing `ControlPlaneStore`, strict codecs, `SnapshotState`, revision CAS, leases, invocation claims, and atomic terminal audit. Reconcile reports and native-start claims after restart; never infer ready from process memory or blindly repeat an uncertain start. Keep selected profile guarantees explicit. |
| Disclosure | Participant observation boundaries and crossing/flow-control owners remain authoritative. A readiness report is apparatus information, not an automatic participant observation, reward, or permission to reveal backend configuration. |

## Ownership, extension seam, and repository gates

[ADR-115](adrs/adr-115-concrete-backends-owned-outside-raes.md) and the
[runtime boundary](issue-1891-runtime-repository-boundary.md) keep native
preparation in external backends, normative contracts in `rae`, and live
enforcement with runtime. Python currently supplies the startup behavior
inspected here. Go already has participant compilation, backend roles, bindings,
and admission; planned runtime API declarations are not shipped runtime support.
Do not turn this issue into another runtime port or repository extraction.
This note authorizes no work or data transfer outside this checkout.

For Go, build on `processor`, `backend`, `contract/binding`,
`contract/validation`, `contract/admission`, `base/ingress`, `base/digest`,
`base/fault`, and the existing value-free logging owner.
Model changed packages, imports, entry points, and exported identifiers in
`implementations/architecture.json` before coding, then pass `archcheck -design`.
Respect the public API declarations and dependency direction in issue #1825.

The extension seam is the admitted producer plus the finite assertion/subject
set, release basis, and existing truth outcome. Another backend or another
participant group supplies different bindings and assertions through that seam.
Do not introduce backend-name branches, a LilRAE profile, a global target-ready
Boolean, or a new release-expression/plugin system.

`contracts/schemas/` remains normative. Existing authoring and truth schemas
already cover the proposed vocabulary; add no duplicate readiness-truth schema.
If a missing scoped request or retained-state contract requires a schema change,
use `contracts/schema-publication-manifest.json`, publication entries, fixtures,
invariant rules, and the existing generator compatibility check.
Regenerate Go bindings and embedded corpus with `contractgen`; never hand-edit them.
Keep snapshot projections, packaging, profile/version admission, and migration
rules aligned. Do not silently change v1/v2/v3 autonomous profile meanings.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`,
`tools/check_generated_schemas.py`, and the existing verification lanes.
This issue has no requirement UID; use the requirement-free tooling route,
without fabricating a UID. Preserve accepted ADR pins and historical evidence.
Release-please owns versions and the changelog.

## Verification boundary and non-goals

Required behavioral evidence includes no native initialization/action/tool call
before release, successful release after a post-handoff report, independent
participant groups, and all autonomous profiles.
Cover polarity and missing/false/unknown/unsupported results, invalid evidence,
wrong producer/run/target, changed declarations, stale generations, report replay,
reports racing apply/stop/reset, report-commit failure, and restart around native start.
Cover direct lifecycle and clock paths, durable phase completion, cadence/window
expiry, no extra random draws/attempts, and value-free errors/audit/readback.
Use explicit native-call counters and meaningful state assertions.
Mutation checks must show that removing the gate or weakening scope/freshness
checks fails the tests. Run only targeted cases locally; full mutation,
integration, fuzz, completion, and repository suites belong in CI.

Extend incumbent coverage such as `test_dsl_437_benign_participant_execution.py`,
`test_runtime_proposition_truth.py`, `test_issue_898_participant_execution_control.py`,
`test_issue_1629_run_driver.py`, `test_issue_1359_runtime_api_trust_boundary.py`,
and `test_issue_1740_invocation_tool_actions.py`, or their Go owner equivalents.
Inert stubs prove portable ordering and refusal; LilRAE owns live preparation evidence.

Non-goals: implement LilRAE setup, add a general workflow engine, change action
preconditions or human-participant launch, create continuous readiness monitoring,
add automatic retries/rollback, change clocks, migrate live stores, or publish a release.
This preflight changes guidance only and is not an implementation plan.
