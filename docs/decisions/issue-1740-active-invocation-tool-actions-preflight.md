# Active invocation and participant tool actions

Architecture preflight for issue #1740. The supplied issue is the delivery
contract; there is no attached requirement UID. This note sets design guardrails,
not an implementation plan or a claim that the public API already exists.

## Decision and ownership

Keep one `RuntimeControlPlane` and its fixed `RuntimeRunContext` as the owner.
An autonomous harness invocation and each tool action have distinct identities
and outcomes. The invocation is the enclosing execution, not a grant for every
tool it can reach. A tool action needs independent admission before effects.
Its accepted records remain valid if the invocation later fails.

Add an explicitly versioned composition contract at the public runtime boundary.
It must connect an active, runtime-issued invocation binding to independently
admitted participant actions. Reuse existing action requests, typed native
outcomes, operation receipts and behavior events. Add only the relationship and
lifecycle coordinates those contracts cannot currently express. Ordinary
autonomous actions retain their exact ordered three-event protocol.

The public seam belongs to `raes_runtime`; neutral carriers belong to
`raes_contracts`, executable backend protocols to `raes_backend_protocols`, and
compiled semantic bindings to `raes_processor`. Respect ADR-036 and ADR-117;
consumers use public interfaces, never scheduler helpers or manager internals.
No new controller, store, general workflow engine or MCP-specific semantics is
needed. ADR-104, including its #1660 and #1629 amendments, already establishes
the ownership model. A new ADR would duplicate it; this note qualifies the
missing composition under that model.

## Trusted binding and admission

The runtime resolves the submitted installed binding against its installed
compiler context and selected apparatus. A caller-created request or compiled
object is not sufficient authority. Bind and recheck:

- Target and run, authenticated host actor, participant and live episode.
- Active invocation identity, enclosing operation, execution-service scope,
  generation and applicable shared-clock segment/cut.
- Selected implementation and configuration/exposure provenance, exact installed
  tool/affordance, action contract, observation boundary and permitted targets.
- Validated action arguments, current applicability, visibility, authority,
  mixed-control permission when applicable, temporal and resource constraints.

The existing `ParticipantToolAffordanceRuntime` contains participant selectors
and sets of action and observation addresses. Those sets do not choose an exact
call binding. Tool profiles describe support; neither a profile, tool name,
role label, native reachability nor implementation manifest alone grants
invocation authority. Select one exact supported relation, without inventing a
Cartesian product of independently supported actions, targets and implementations.
Missing, ambiguous, foreign, stale or unsupported joins refuse before effects.

The invocation binding is runtime-owned authority, not an ambient thread-local
current participant and not an arbitrary parent ID supplied by the backend.
Retain distinct operation-parent and invocation/action coordinates:
`OperationAdmissionContext.parent_operation_id` is existing operation lineage,
not by itself a participant action, affordance or generation authorization.
Do not repurpose `joint_action_set_id`, attribution edges, activity retry IDs,
or behavior-history indexes as invocation identity.

Admission must give a definite decision before dispatch. If execution remains
in the consumer's common handler, the runtime must claim the action first and
mediate a one-use dispatch authorization tied to that exact request. Completion
then submits a typed outcome against the claim. A lost admission acknowledgement
requires same-identity readback, never speculative execution. A successful
operation receipt alone is neither native success nor accepted behavior history.
Recheck live authority, generation and the finite execution budget when consuming
the dispatch authorization, and fence completion against current authority again.

## Progress, ordering and settlement

`RuntimeMutationAuthority.external_call()` releases the short state permit but
retains the enclosing effect reservation. It marks extension execution so that
`mutation()` rejects backend re-entry. `reserve()` and
`supervised_claim_conflicts()` also exclude competing effects. Calling ordinary
`admit_participant_action()` recursively from `_model_action`, or from another
thread that waits on that reservation, does not establish supported progress.

The composition seam must admit bounded child work through the same state owner
while the invocation waits outside its state permit. Any parent-reservation
compatibility must require the validated invocation binding and child effect
scope. Unrelated effects remain excluded. Do not disable extension guards, copy
mutation permits into workers, use `supervision()` to dispatch effects, or treat
any record with a parent ID as exempt from conflict checks.

Bound queued calls, child count and in-flight native work. Account explicitly
for the enclosing invocation versus executing children: a waiting invocation
must not consume the only capacity needed by its child. Control/cancellation
capacity must remain available even when effect workers are full. Reuse existing
service/resource ledgers and bounded offload/dispatch machinery; a private
executor or unbounded queue would introduce another lifecycle owner.

Commit each validated child through runtime-owned, revision-checked history
updates. Retain the admitted predecessor and all previously accepted peer and
child events. The enclosing worker's stale returned snapshot cannot overwrite
those commits or re-submit child history as its own append. Validate the outer
action's own three events separately under the negotiated composition contract;
do not filter arbitrary extra events and silently accept the remainder.

`participant_scheduler_concurrent_state` currently merges whole mapping entries
and rejects a second write to the same key, even an equal write. Therefore two
updates to one participant's history need an explicit runtime-owned append
composition rule. Never weaken generic map conflict checks, concatenate arbitrary
backend lists, or use last-writer-wins. Preserve conflict checks for actual state
effects, protected scheduler fields, and declared semantic footprints. A child
must not mutate its enclosing invocation's scheduler counters.

Give each action an ordered local history and a runtime-assigned accepted-history
position. Preserve invocation/child causal links independently of wall timestamps
and native completion order. The existing scheduler commits concurrent peers in
request order; reverse completion must retain both histories without claiming
that this serialized order proves physical effect order. Overlapping shared
targets still require the existing commutativity or governed merge-rule support.
Same-participant parallel calls need explicit support; otherwise refuse or
serialize them without blocking the owner needed for progress.

## Failure contract

| Condition | Required disposition |
| --- | --- |
| Binding or policy refusal | No dispatch grant and no effects. Use existing bounded denial/audit records; never fabricate successful action history. |
| Exact replay | Reauthorize disclosure in the original actor/scope and return the retained decision/outcome. Do not dispatch again or append duplicate events. |
| Conflicting request identity | Refuse changes to binding, arguments, parent, targets or generation under the same identity. Use canonical commitments and existing sensitive-retry rules. |
| Cancellation, timeout or disconnect before dispatch | Close unused authorization atomically against dispatch; record that effects did not start only when established. A transport disconnect alone does not cancel accepted work. |
| Cancellation, timeout or disconnect after dispatch | Retain the action and its effect reservation until validated cessation/outcome or indeterminate reconciliation. Cancellation acceptance is not cessation or rollback. |
| Missing/malformed completion or unknown native effects | Retain the claim and classify uncertainty through the existing operation supervision/recovery contract. Never replay effects to reconstruct history or coerce `unknown` into `failed`/`succeeded`. |
| Reset, episode replacement, retired run or stale generation | Reject new dispatch and stale completion against current authoritative state. Keep the original claim/outcome or uncertainty in its original scope; never attach it to the new episode. |
| Outer failure, protocol failure or cancellation | Stop new child admission, settle every already admitted child, and preserve accepted child/peer histories. Unknown child work prevents a clean drain/reuse claim. |

Outer settlement closes child admission under the same serialized authority so
it cannot race a new call. It may finish only after child work is terminal or
explicitly retained under the existing indeterminate/reservation contract.
The outer result cannot substitute for any child's outcome. Recovery observes
and reconciles the original identity; it does not re-run the tool. Preserve
`CancelledError` propagation after cleanup under ADR-116.

P0 makes in-process guarantees only. Durable profiles must retain claims,
invocation relationships, consumed grants and uncertainty across restart using
the selected store. Child terminal state, accepted snapshot/history and actor
audit commit atomically; outer settlement is a later transaction that preserves
them. A process restart cannot reconstruct authority from a consumer log.

## Cross-cutting layers and canonical incumbents

Paths below are under `implementations/python/packages/` unless specified.
Unqualified runtime module names refer to `raes_runtime/`.
These are design obligations, not claims that each existing path already
supports active-invocation composition.

| Layer | Reuse and required boundary |
| --- | --- |
| SDL and semantic validation | `raes/participant_behavior_specification.py`, `raes/validator/_participant_tool_affordances.py`, `raes/semantics/participant_behavior/`, and `raes_processor/compiler/participant_behaviors.py` own authored affordances and their compiled selectors. Retain reference, scope and argument-shape validation; add no parallel tool schema. |
| Installed configuration and capability admission | `control_plane_configuration.py`, `raes_processor/participant_tool_support.py`, `raes_backend_protocols/participant_capabilities.py`, `raes_backend_protocols/participant_execution_manifest.py`, and `raes_backend_protocols/participant_feature_admission.py` own typed installation, exact offers, strengths and limits. Negotiate composition explicitly and require an executable protocol at registration. Tool-profile support or autonomous v1/v2/v3 support alone cannot imply it. Unsupported pairs fail before dispatch. |
| Caller and transport authority | `control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_operation_context.py`, and the host boundary in the [#1356 decision](issue-1356-control-plane-participant-access-preflight.md) own principal/run/subject checks. Keep SDK objects and privileged P2 credentials inside the trusted host. A scoped invocation reference cannot confer full control-plane or peer-read authority. |
| Ingress shapes | `raes_contracts/json_ingress.py`, contract `ContractModel`, `control_plane_api_models.py`, `control_plane_api_guards.py`, and `control_plane_api/_responses.py` own closed shapes, bounded bytes/depth and fixed refusals. Revalidate detached requests/results, including constructed model instances. An optional served route must declare existing route authority and bounded offload; a new HTTP endpoint is not required by this issue. |
| Participant admission | `raes_contracts/participant_binding.py`, `participant_control.py`, `participant_scheduler_binding.py`, `participant_control_action_admission.py`, and `participant_temporal.py` own selection, current proposal approval, exact runtime coordinates and temporal assessment. Reuse their checks without treating a typed DTO as an authority check or routing bound actions around the autonomous temporal driver. |
| Information flow | `participant_submission_options.py`, `participant_crossing_action.py`, `participant_crossing_boundary.py`, `participant_flow_sink.py`, and `participant_opacity_enforcement.py` own ingress/egress and permitted projections. Tool arguments and results still cross these boundaries where applicable. Release only permitted result projections; do not expose backend-native objects, peer history, hidden truth or evaluator data through a reply or error. |
| Native effect and snapshot admission | `control_plane_participant_apply.py`, `participant_effect_authority.py`, `backend_calls.py`, and `backend_snapshot_contracts.py` own isolated calls, allowed effect owners/targets and bounded snapshot shapes. Combine them with `participant_action_validation.py` and authoritative generation checks in `participant_scheduler_concurrent_commit.py`; reuse three-event construction from `raes_contracts/participant_binding_history.py`. Accepted child ownership must not excuse unrelated snapshot changes. |
| History and public projection | `participant_result_contracts.py` delegates to shared `raes_contracts/participant_behavior.py`, episode, outcome, shared-state, concurrency, crossing and information-state validators. Reuse these snapshot and append-only transition checks on admission, reload and conformance paths. `snapshot_contract.py` and `participant_retrieval.py` must expose the same accepted composition under the existing projection rules; an SDK-only object is insufficient. |
| State, persistence and recovery | `control_plane_mutation.py`, `control_plane_admission.py`, `operation_invocation_ledger.py`, `control_plane_supervised_execution.py`, `control_plane_recovery.py`, `control_plane_store_transitions.py`, and `control_plane_store_snapshots.py` own claims, one-use grants, revisions, codecs, terminal commits and reconciliation. Retain the selected memory/local/PostgreSQL store's guarantees, lease and private-path checks. Reuse `raes_contracts/immutable_history.py` and existing history rows/readback rather than creating a tool journal. |
| Secrets, environment and OS exposure | `raes_contracts/secret_references.py`, `raes/runtime_environment.py`, `raes/runtime_generated_value.py`, `raes/runtime_configuration.py`, and `raes/runtime_values.py` retain logical secret references, sensitivity/provenance, redaction, literal/`value_from` exclusions and generated-reference checks. This design needs no new credential or env loader. Keep native credentials, raw MCP arguments/results and authority-bearing handles out of process argv, URLs, shell tracing, environment dumps, logs and portable metadata. LilRAE retains authenticated transport, credentials and process cleanup. |
| Errors and observability | `raes_contracts/errors.py`, `raes_contracts/diagnostics.py`, `raes_contracts/operational_logging.py`, `backend_result_diagnostics.py`, `control_plane_audit.py`, and `control_plane_api/_responses.py` remain canonical. Follow [ADR-116 policy](../develop/exceptions-and-logging.md): expected findings use diagnostics, domain failures use existing categories, foreign failures log once through `foreign_failure_record`, and public envelopes omit raw validator input and exception chains. Do not add a tool exception hierarchy or logging setup. Logs/OTel never replace accepted history. |

Canonical request serialization is not a generic redactor:
`control_plane_operation_context._value_free_request_payload()` currently has
specific credential handling, not a promise to remove arbitrary tool arguments.
Keep portable records to approved safe coordinates and protected evidence
references. If sensitive input is needed for replay identity, reuse the existing
exact-retry proof policy; do not persist a raw payload or an unapproved digest of
low-entropy secrets. Lost sensitive retry proof must fail closed.

## Compatibility, extension and evidence

Parameterize the installed relation by participant, tool/affordance, action,
observation, targets and selected implementation; parameterize composition
support and finite limits. Do not hardcode red/blue roles, MCP method names or a
particular harness. Invocation-scoped action admission is the extension seam for
another installed tool adapter. Arbitrarily nested invocation trees and new
execution topologies need their own explicit support, not an implicit recursion
rule. Composition support remains distinct from v3 resource budgeting.

The published contract must define correlation, dispatch consumption, per-action
ordering, outer closure and failure dispositions before consumers rely on it.
Keep `specs/formal/participant-semantics/autonomous-execution.md`, backend runtime
contracts, conformance projections and history readback consistent. Published
schema changes require fixtures, the change ledger in
`contracts/schema-publication-manifest.json` and its entry records, and identical
`schema_bundle()` output under `tools/check_generated_schemas.py` and
`tools/check_schema_publication.py`. New snapshot fields also need exhaustive
ownership, codec, projection and migration coverage; prefer extending the owning
typed contract over an opaque metadata map.

Qualification must exercise the real public owner, scheduler admission and
settlement, not only `BaseParticipantRuntime.admit_action()` against a local
snapshot. Existing patterns include `test_participant_concurrent_batch_reservations.py`,
`test_dsl_437_benign_participant_execution.py`, `test_issue_1660_runtime_lifetime.py`,
`test_issue_1629_run_contexts.py`, `test_issue_1362_runtime_supervision.py`, and
`test_issue_1187_control_plane_security_conformance.py` under
`implementations/python/tests/`. Require bounded synchronization tests for these
cases:

- waiting outer invocations, reverse red/blue completion and same-participant overlap;
- preserved predecessors/peers and authority refusals with zero native calls;
- duplicate and conflicting identities, cancellation races and stale completion; and
- outer failure and durable reload/reconciliation.

Use non-base-class backends as well as the
reference base; safety cannot depend on inheritance. Include disclosure and
resource-accounting failure cases. No model requests or native lab effects are
needed to establish this protocol.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
`tools/policy/import_contracts.toml`, and the canonical nox graph for delivery.
Local checks stay file-targeted; CI owns full, integration and fuzz suites.
Do not manufacture a requirement UID for this issue-only contract. Release Please
owns versions and changelog; the consumer-visible implementation needs a
release-producing `feat:`/`fix:` title and a public API/example in
`docs/public/guides/python.md` or its maintained guide surface. State the released
capability/version needed; neither the consumer's 9.1.0 pin nor the reported
9.2.0 behavior establishes composition support.

## Non-goals and anti-patterns

No issue implementation is delivered by this note. No new MCP handler, argument
validator, transport authentication scheme, credential broker, process sandbox,
archive owner, service or deployment is selected. LilRAE retains those owners.
No backend-owned participant semantics, manual snapshot merging, best-effort
post-call recording, role-only authority, recursive manager calls, whole-snapshot
replacement, generic conflict relaxation, or automatic replay after uncertain
effects is acceptable. Do not conflate invocation failure, operation failure,
native action outcome, temporal assessment, information release and cleanup
evidence. This change promises neither rollback of native effects nor distributed
exactly-once execution, new tenant isolation or stronger durability than the
selected control-plane profile.
