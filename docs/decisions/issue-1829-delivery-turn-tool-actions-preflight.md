# Tool actions in governed participant delivery turns

Architecture preflight for issue #1829. The supplied GitHub issue is the
contract; no requirement UID is attached. This note adds guidance, not runtime
support or an implementation plan. Paths in tables start at
`implementations/python/packages/` unless stated otherwise.

## Decision and boundaries

Extend the existing invocation tool-action composition to a runtime-owned
participant delivery turn. Keep `RuntimeControlPlane` and `RuntimeRunContext`
as the owners under ADR-104. Reuse the port, child operation ledger, action
results, crossing records and behavior history. No new controller, tool journal,
MCP transport, workflow engine or exception family is needed. ADR-095, ADR-108,
ADR-110 and ADR-112 already establish the semantic boundaries. Extending the
autonomous-only composition in ADR-092 section 10 needs an in-band amendment
and matching `adr-index.yaml` pin under ADR-059 when that support ships; it
does not require a new ADR or changing the accepted decision during preflight.
Read this alongside the [#1740 preflight](issue-1740-active-invocation-tool-actions-preflight.md)
and [delivery preflight](issue-1368-directed-inject-occurrence-preflight.md).

Keep world inject execution, accepted participant control, content release,
active participant invocation and each tool action distinct. In particular,
`deliver_participant_inject()` commits a governed content release; it does not
run a harness or establish an active invocation. Its receipt cannot become an
ambient grant to call tools. Projection/policy resolvers must remain free of
native effects. A delivery permission is not a child action permission, and a
proposal or external direction is not execution success.

The public seam must bind the active turn to its retained delivery, participant,
episode, selected implementation, execution scope/generation, enclosing live
operation and authenticated actor/target/run. Resolve these through installed
compiler context and owner records, not caller-supplied parent IDs or role names.
Open the port before the matching invocation, activate only during its dispatch,
and close on every terminal path. Each child still needs separate admission,
durable one-use dispatch and typed settlement before its history is accepted.

The existing `ParticipantInvocationToolContextModel` requires an enclosing
**action** instance and contract. A delivery invocation must not invent an
action contract or label a delivery address as one to fit that carrier. Reuse
the owning contracts and history-view projection, evolving their explicit
invocation reference only where necessary. Preserve the existing autonomous
action variant and its three-event rule. Bind delivery execution scope and
generation to retained runtime lifecycle state; the current execution-service
carrier's policy fields do not justify a synthetic autonomous policy.

## Concrete gaps and guardrails

| Current constraint | Required design boundary |
| --- | --- |
| `raes_runtime/participant_invocation_tool_settlement.py` opens sessions only from scheduler contexts; indeterminate settlement writes an autonomous scheduler state. | Share the existing lifecycle/settlement owner with delivery turns. A delivery turn must have a real lifecycle owner and failure disposition; never fabricate a scheduler state or autonomous policy merely to satisfy a constructor. Preserve the ordinary outer action's exact three-event protocol. |
| `raes_processor/compiler/participant_autonomous_execution.py::compile_invocation_tool_bindings` joins tools only to autonomous policies. | Reuse its exact affordance/action/observation/participant/target/interaction relation for the installed behavior specification of the turn. Keep compiled authority in `raes_processor`; do not reinterpret raw `spec` maps, invent Cartesian products or copy the compiler into the runtime. |
| `raes_runtime/manager_plan_admission.py` counts autonomous policy actions as driven; `participant_submission_options.py` rejects manually submitted shared-time actions. | Recognize only the exact compiled actions covered by an installed delivery driver, with positive executable support and all temporal checks. Preserve refusal for unhosted/manual actions. Admission of a scenario without an autonomous policy must be demonstrated before port-level tests can establish this feature. |
| `raes_contracts/contracts/participant_invocation_tools.py::validate_invocation_tool_action_claim` requires autonomous support; `raes_backend_protocols/participant_invocation_tools.py` inherits the autonomous protocol. | Admit the delivery-hosted composition explicitly through the same capability and protocol owners. Installation, manifest round trip, registration method-shape checks and actual executable support must agree. Delivery-only support must not require a false autonomous capability claim. Preserve old autonomous callers and historical records. |
| The port rejects installed crossing and temporal bindings, filters shared-time contexts, and refuses temporal evidence in outcomes. Event construction filters those contexts again. | Replace unsupported guards only where complete per-child crossing and temporal admission/settlement exists. Removing flags or retaining an outer timestamp does not establish composition support. Keep unsupported combinations closed. |
| `raes_runtime/participant_invocation_tool_claims.py::invocation_tool_child_of` admits reservation compatibility only for a running `COMPOSITION_PHASE` parent. | Any additional admitted parent kind needs the same exact actor/scope/run, child commitment, binding and live-parent proof. Never permit every child of a crossing operation or exempt any record merely because it has a parent ID. |

## Security, validation and configuration layers

| Layer and canonical incumbents | How the composed path must satisfy it |
| --- | --- |
| Authoring and compilation: `raes/validator/_participant_tool_affordances.py`, `_participant_inject_deliveries.py`, `_participant_inject_delivery_control.py`; `raes_processor/compiler/participant_inject_deliveries.py`, `participant_temporal.py` and `participant_autonomous_execution.py` | Retain scoped references, authored argument constraints, exact tool/action/target joins, policy pins and delivery/control variant checks. Missing or ambiguous bindings refuse before native dispatch. A tool name, red/blue role or implementation offer alone grants nothing. |
| Installed configuration: `raes_runtime/control_plane_configuration.py`, `participant_inject_delivery.py::ParticipantInjectRuntimeBinding`, `participant_control_runtime.py`, `raes_backend_protocols/participant_capabilities.py`, `participant_execution_manifest.py`, `raes_runtime/registry.py` | Preserve closed option shapes, original compiler-context equality, installed resolver/provider call shapes, positive tool support, exact execution offers and finite admission/concurrency limits. Use one owning capability model through both manifest forms. An installed crossing resolver is neither proof of per-tool mediation nor a reason to disable crossing. |
| Caller authority: `raes_runtime/control_plane_security.py`, `control_plane_api/_auth.py`, `control_plane_operation_context.py`, `participant_inject_application.py`, `participant_inject_control.py` | Preserve authenticated target/run, actor-bound retry/readback, audience and controller subject checks, live episode, accepted control occurrence/digest, policy edge, authority scope and validity. Keep controller order separate from shared time. Do not substitute `identity=None`, a backend service identity or the delivery audience for the originating action authority. |
| Request/result shapes: `raes_contracts/participant_tool_actions.py`, `contracts/participant_action_admission.py`, `contracts/participant_runtime.py`, `json_ingress.py` | Revalidate detached requests and results, including direct calls and constructed models. Retain strict identities, unique non-empty targets, generation checks, exposure/evidence checks and closed result variants. The existing tool request is a binding carrier, not an arbitrary MCP arguments envelope. Where arguments affect permission, bind the canonical validated selection and the exact dispatched subject; add no parallel JSON argument validator. Any served surface retains existing byte/depth/duplicate-key limits and route authority. A new HTTP route is not required. |
| Per-child ingress and final sink: `raes_runtime/participant_crossing_intents.py`, `participant_crossing_mediation.py`, `participant_crossing_records.py`, `participant_crossing_boundary.py`, `participant_crossing_transform.py`, `participant_flow_sink.py`, `participant_opacity_enforcement.py` | Use API-423 subjects, evidence, semantic/backend gates and history-head validation for each exact child. Conjoin incumbent participant authority, current control and IFC/marking/exposure rules. Commit authorization before effects. Delivery egress evidence is not reusable blanket action evidence. Deny/withhold must block dispatch; a transform creates a freshly validated governed subject and cannot authorize execution of the original request. |
| Modular control: `raes_runtime/participant_control_orchestration.py`, `participant_control_binding.py`, `participant_control_evaluation_v2.py`; `raes_contracts/contracts/participant_control_*` | Reuse the installed API-424 sink evaluation, applicability/support checks, composition and retained consumption at the child's exact cut. API-424 eligibility and API-423 permission are separate gates. Provider failure cannot become an absent optional selection, and a tool child cannot independently re-spend a parent control budget or logical claim. |
| Linked control and result release: `raes_runtime/participant_control_action_admission.py`, `participant_crossing_egress.py`, `participant_retrieval.py` | Recheck live proposal approval where applicable; cancelled, superseded, revoked, expired or foreign-episode control cannot authorize children. Expose only the admitted participant projection. A typed child result or successful tool call does not authorize revealing raw native output, peer state, hidden truth or evaluator data. Revalidate at the applicable final sink after external callbacks. |
| Secrets, environment and host: `raes_contracts/secret_references.py`, `runtime_values.py`; `raes/runtime_environment.py`, `runtime_generated_value.py`, `runtime_configuration.py` | No new secret loader or process launcher is needed. Retain logical secret references, redacted/operator-secret omission, provenance, valid environment names, literal/`value_from` exclusions and generated-secret classification. Keep credentials, port handles and sensitive tool arguments/results out of argv, URLs, shell tracing, environment dumps, portable metadata and logs. The existing value-free request serialization is not a generic tool-payload redactor. Runtime protocol inputs convey declared action bindings and typed outcomes; credentials and native transport payloads are not portable authority. |
| Failure envelopes and observability: `raes_contracts/errors.py`, `diagnostics.py`, `operational_logging.py`; `raes_runtime/control_plane_audit.py`, `control_plane_api/_responses.py` | Use fixed refusal codes and existing diagnostic/error categories. Isolate foreign failures once with `get_logger` and `foreign_failure_record`; never return validator inputs, exception values/chains or native output in errors. Propagate `CancelledError` after cleanup. Follow ADR-116 and `docs/develop/exceptions-and-logging.md`. Operator logs and traces do not substitute for crossing/action/audit history. |

Calling `require_live_control_proposal()` alone does not establish current
control permission: it returns without a check when `validated_selection` is
absent. Delivery admission uses `participant_inject_control.py` to establish
its accepted occurrence, policy and live authority; each child must carry the
applicable linkage and recheck its own permission through those incumbent
owners. Admission and dispatch can be separated by revocation, cancellation,
or a clock transition: consume no grant from a stale prepared cut.
The executor must receive the exact governed selection after a transform.
The current decision/receipt carries an action identity, not transformed
arguments; if the approved subject cannot be conveyed and executed faithfully,
refuse dispatch rather than record a transform and execute the original call.

## Shared time, progress and durable history

Use `participant_scheduler_binding.py` and the compiled temporal binding owner
to build **child-specific** contexts: child action/contract, participant/episode,
execution generation, shared clock/segment/sequence and submission coordinate.
Never copy the outer action's shared-time identity onto a child. A delivery
window (`participant_inject_temporal.py::require_delivery_time`) and an action's
deadline/dwell guarantee are different constraints; satisfy both where applicable.
Logical control order, store revision, generation, history position and wall
time are not interchangeable clock coordinates.

Compile the child's actual temporal contracts, not merely its existing
`shared_time_bound` flag or the outer policy's action list. One manifest offer
must cover the complete bound combination of `temporal_contract_digests`;
do not assemble partial offers into an unsupported guarantee. Recheck the
shared clock at dispatch, including reset/segment, pause and deadline changes
since admission. Dwell coverage must exist before effects.

Reuse `raes_runtime/participant_temporal.py` pre-dispatch checks and
`raes_contracts/contracts/participant_temporal_history.py::assess_temporal_guarantee`.
Temporal evidence must match the child's exact boundary and declared evidence
set. Every bound terminal history needs a runtime-owned assessment against the
retained clock history; `require_participant_temporal_history` checks context
identity, immutable context across events, bounds, evidence and assessment
replay. Cover withheld, rejected, interrupted and indeterminate settlements too.
`assess_temporal_result` currently edits the last history event: preserve exact
child ownership when reusing it across outer/peer settlement.
The history validator also derives `native_execution` from the attempt's
admission disposition. An admitted child withheld before dispatch and a child
whose dispatched effects are unknown are distinct facts. Keep that distinction
in the owning assessment/history contracts; do not forge a rejected admission,
reported native work or temporal evidence to satisfy the validator. Snapshot
serialization and reload invoke this validator through
`raes_contracts/participant_autonomous_state.py` even without scheduler state.
Neither wall elapsed time nor native success proves a logical guarantee. A missed
or unknown guarantee never implies rollback, cessation or permission to retry.
Use the injected `WallClock` only for wall timestamps (ADR-118).

The port currently has a leaf lock and promises no callback into the manager or
control plane while the outer invocation waits. Crossing/control resolvers need
an authoritative cut and may call installed external code. This is a real
progress boundary: do not call ordinary `admit_participant_action()` recursively
from the port, disable extension guards, hold its lock over foreign callbacks,
or dispatch through supervisory authority. Compose through the incumbent
`RuntimeMutationAuthority`, bounded `LocalExecutionAdapter` and operation
reservation owners. Preserve an explicit owner handoff and exact-cut recheck;
the waiting invocation must not occupy the only capacity its children need.
Keep cancellation/control capacity available and bound calls and native work.

Reuse `HostedActionRegistry`, `participant_interaction_conflicts.py` and the
existing concurrent scheduler's conflict/commit rules. Same-participant child
calls serialize unless exact overlap is supported; peer/shared-target conflicts
remain governed. Unknown effects retain their reservation and fence later
grants across the run. No unbounded queue, private executor or native retry to
repair missing evidence.

`InvocationToolActionLedger`, `ControlPlaneStore`,
`participant_crossing_commit.py`, `control_plane_store_transitions.py`,
`control_plane_store_snapshots.py` and `control_plane_recovery.py` remain the
durable owners. Preserve admission before decision, consumed dispatch before
grant, terminal outcome/audit before acknowledgement, history-head CAS and
revision fencing. Coordinate crossing authorization with the child claim under
those owners; a crossing record alone is not a consumed dispatch grant. The
cut must advance with accepted child history; do not reuse the delivery's
effective order or stale history heads for every child. Exact replays return
retained facts without effects or duplicate history; changed
binding/content under an identity conflicts. Sensitive retry identity must use
the existing proof policy, not raw payload retention or guessable secret hashes.

A store error or timeout can follow a successful write. Resolve an ambiguous
acknowledgement through authoritative readback under the same identity and
revision rules; it cannot free a consumed grant or conflicting-effect
reservation, or authorize another dispatch.

Use `participant_tool_action_events` and existing behavior/temporal/crossing
validators through `participant_result_contracts.py` on commit, reload and
projection. Preserve local three-event order and causal invocation linkage;
admission/history order does not prove physical effect order. Child history
must survive invalid, raised or cancelled outer results and must not be
overwritten by their stale snapshots. Keep existing atomic history publication
with the enclosing operation; account explicitly for earlier durable child
settlements if the enclosing commit fails or the process crashes. Do not claim
that a terminal ledger row alone proves behavior history committed. Keep stale
episode/generation work in its original scope, never attach it to a new episode.
Recovery retains uncertainty and never replays native calls. Cover all admitted
memory/SQLite/PostgreSQL profiles and their existing lease/private-path rules.

## Extension, compatibility and delivery evidence

The extension seam is the existing invocation port bound to a trusted active
turn, with installed behavior/tool relations, per-child crossing/temporal
context and finite limits. Separate that context from autonomous cadence and
scheduler counters. This admits another delivery trigger or tool adapter without
hardcoding MCP methods, participant colors or a second action lifecycle. Keep
composition support explicit; change a version/claim only when needed to express
new support, and never reinterpret retained v1 evidence or infer new support
from an old autonomous-only claim. Resource-governed v3 remains unsupported
unless its complete budget accounting is separately admitted.

Respect ADR-121: neutral data/validators in `raes_contracts`, executable protocols
in `raes_backend_protocols`, compiled intent in `raes_processor`, orchestration
in `raes_runtime`. Runtime code reaches authored facts through public processor
interfaces, never reverse imports, private compiler helpers or duplicate models.
Keep public support documentation and
`specs/formal/participant-semantics/autonomous-execution.md` consistent with the
newly supported composition and retained restrictions. If published shapes
change, update fixtures and the publication change ledger under `contracts/`
and keep `raes_schemas.schema_bundle()` identical to publication under
`tools/check_generated_schemas.py` and `tools/check_schema_publication.py`.

Required qualification builds on `test_issue_1740_invocation_tool_actions.py`,
`test_issue_1368_inject_delivery.py`, `test_api_423_participant_crossing_contracts.py`
and `test_act_614_temporal_*` under `implementations/python/tests/`. Exercise the
public runtime owner with a non-base-class backend: real governed delivery turn,
per-child permit/deny/transform, zero calls on refusal, time evidence and expiry,
stale/revoked control, same-identity replay/conflict, concurrent/unknown effects,
outer failure/cancellation, store-write failures and reopen/recovery. Include
temporal/crossing validator replay and disclosure/error leakage checks; a port
unit test alone does not establish the composed behavior.
Include a delivery-only manifest/scenario with no autonomous policy, control
without `validated_selection`, a cut change between admission and dispatch,
and retained completed children after a crash before the enclosing history
commit. Update `docs/public/guides/invocation-tool-actions.md` and its public
index alongside the formal support description; the existing guide promises
an autonomous-only port with no manager callback.

Use `.ground-control.yaml`, `.gc/plan-rules.md`, `.pre-commit-config.yaml`,
`tools/policy/import_contracts.toml` and the canonical nox graph. Local checks
remain targeted; full, integration and fuzz suites belong to CI. Do not invent
a requirement UID. Release Please owns version/changelog edits; the eventual
runtime-feature PR needs a release-producing `feat:`/`fix:` title. Issue #1829
also requires the released Python distribution, not merely a merged change:
retain the published version/artifact evidence from the existing
`.github/workflows/release-please.yml` and its exact-commit verification gates.
This preflight neither merges nor publishes anything.

Non-goals: Go work, a new transport service or credential scheme,
new authoring language, generic policy interpreter, arbitrary nested invocation
trees, universal v3/distributed support, backend-native execution semantics,
external hosting and exactly-once claims about native effects. Do not bypass
manual shared-time submission guards or weaken generic snapshot/history
conflict checks to make this composition pass.
