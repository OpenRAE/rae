# Issue 2009 workflow transition preflight

Issue: #2009. The initial scope was requirement-free documentation maintenance.
Sources inspected at `1cb8f78946214fa20da0d185335bffed256debdf`.

The user expanded the scope to include a library review and static graph checks.
The [library assessment](issue-2009-workflow-library-assessment.md) and [design](issue-2009-workflow-transition-design.md) give the current code boundary.
The semantic guardrails below still apply.

This note sets design limits for the workflow specification.
It supplies no missing transition rules or code plan.

## Architecture decision

Keep the abstract model in
[`state-machine.md`](../../specs/formal/workflows/state-machine.md).
Its existing control locations, lifecycle, outcomes, and attempt counts cover
the issue. Separate control movement from observable step state.
The workflow README's six-kind scope also needs to remain consistent with the
eight-kind specification.

No new ADR, scheduler, schema, validator, or exception type is needed.
ADR-009 gives the specification authority apart from Python code.
ADR-007 permits the existing Markdown abstract model.
This prose change needs no new solver and proves no code behavior.
Keep accepted ADR-006's historical six-kind decision intact under ADR-059.
ADR-115 leaves native effects with external backends.

## Canonical contracts to reuse

Paths below are relative to `implementations/python/packages/` unless stated otherwise.

| Layer | Canonical incumbent and boundary |
| --- | --- |
| Authoring and parsing | `raes/orchestration/_steps.py`: `WorkflowStepType`, `WorkflowStep`, `WorkflowPredicate`, and `WorkflowSwitchCase`. Preserve required targets, field aliases, typed predicates, and positive retry bounds. |
| Graph validation | `raes/validator/_workflows_verify.py` and `_workflows_analysis.py`: target resolution, reachability, acyclicity, join ownership, convergence, compensation edges, and guaranteed predicate visibility. Reuse `branch_closure` from `raes_contracts/workflow/semantics.py`. |
| Observable state | `workflow_step_semantic_contract()` and `validate_workflow_step_result()` in `raes_contracts/workflow/semantics.py`. Observable kinds are `objective`, `retry`, `parallel`, and `call`. |
| Compilation | `raes_processor/compiler/workflow_steps.py` and `workflows.py`: ordered cases, explicit control edges, callee addresses, join owners, `result_contract`, and `execution_contract`. Preserve structured contracts rather than interpreting raw SDL again. |
| Capability admission | `raes_processor/planner/manifest_validation.py` and `raes_contracts/vocabulary.py`: declared switch, call, barrier, retry, assertion, and state-predicate support. Unsupported semantics fail admission. |
| Portable results | `raes_contracts/workflow/contracts.py`, `state.py`, and `enums.py`; `raes_runtime/workflow_result_contract_checks/`. Validate plain data against compiled contracts before accepting backend observations. |
| Schema authority | Repository-root `contracts/schemas/control-plane/workflow-result-envelope-v1.json` and `workflow-history-event-stream-v1.json`. No shape or version change follows from this issue. |
| History and storage | `raes_contracts/immutable_history.py`, `snapshot_histories.py`, and `raes_runtime/control_plane_store_history_rows.py`. Keep ordered history and snapshot storage rules. Abstract control locations need no new stored form. |

## Guardrails and semantic traps

- `switch` preserves authored case order and selects one successor.
  Its existing contract includes a required default and no observable step result.
  Do not translate it into unordered matching or a new expression language.
- `call` has observable success/failure and one attempt.
  Its attempt count does not count the callee's internal attempts.
  Keep caller and callee step namespaces separate.
  A callee's `end` must not terminate unrelated caller branches.
  Preserve acyclicity of both call edges and combined call/compensation edges.
- Interleaving needs branch identity and an owning barrier, beyond a set of
  current step names. Different branches can occupy the same control location.
  Any branch coordinates used to explain this belong to the abstract model, not a new
  wire schema or runtime abstraction.
- Keep each branch's order. Leave the choice between enabled branches to the backend.
  Do not promise round-robin scheduling, fairness, simultaneous physical effects,
  bounded completion, or a fixed branch completion order.
- The current graph checks do not impose branch disjointness or prohibit nested
  fanout. Do not silently add either restriction to simplify the notation.
  Distinguish convergence at an inner barrier from convergence at its owner's barrier.
- A handled objective or call failure does not necessarily fail its workflow.
  Likewise, a failed branch-local step does not by itself prove fanout failure.
  Distinguish successful convergence from the parallel failure bypass.
- Preserve guaranteed-state visibility. Sibling branch results remain unavailable
  before their barrier. The failure bypass does not expose abandoned branch state.
  Unselected or abandoned observable steps can remain pending.
- Preserve the existing compensation contract in
  [`compensation.md`](../../specs/formal/workflows/compensation.md).
  Registration follows successful compensable completion, and rollback order
  follows actual completion order across branches, not declaration order.
- Keep step outcomes separate from workflow terminal reasons and compensation status.
  Cancellation and timeout do not become new step outcomes.
  Do not imply a new cancellation cascade, timeout inheritance, or rollback policy
  through call or interleaving notation.
- The state-machine page calls workflow status backend-local.
  The [result contract](../../specs/formal/runtime-contracts/workflow-results.md)
  requires portable workflow status. Align that description with the portable
  envelope. Do not add a new field or merge status with step outcome.
- Older explanatory prose mentions predicate `conditions`.
  Current `WorkflowPredicate` rejects that field and accepts precondition
  `assertions`, objectives, and guaranteed step state. Do not copy the stale example.

## Security and operational boundaries

The change includes specification prose and static graph validation.
It adds no new input form, route or backend call.

| Cross-cutting layer | Required treatment |
| --- | --- |
| Parser, shape checks, and semantic policy | Describe only admitted step fields and existing graph invariants. Do not relax `WorkflowStep` validation or introduce different predicate rules. |
| Backend trust and capability gates | Retain planner admission and manager result/history checks. A documented transition does not authorize an unsupported backend or certify an observed trace. |
| Authentication and authorization | No new route or identity transfer. Keep `raes_runtime/control_plane_api/_auth.py` and authenticated workflow control. A call target grants no new authority. |
| Secrets, environment bindings, and host exposure | No new credentials, environment variables, binding shapes, commands, subprocess arguments, or listeners. Declarative references remain references; do not embed native payloads. |
| Errors and logging | Retain `raes_contracts/errors.py`, `diagnostics.py`, and `operational_logging.py`; `raes_runtime/backend_result_diagnostics.py`; and `raes_runtime/control_plane_api/_responses.py`. Keep stable diagnostics and redacted error envelopes. Do not expose raw exception text. |
| History and storage | Retain existing result/history carriers, immutable prefixes, and durable store ownership. Interleaving does not authorize rewriting history or adding a second event stream. |
| Repository and host tooling | Use `.ground-control.yaml`, `.gc/plan-rules.md`, `tools/check_repo_policy.py`, and the existing `docs-prose` lane. Documentation tools use the reviewed artifact lock and local checks. No upload or external analyzer is needed. |

## Extension seam and verification limits

Use symbolic case lists, branch roots, join owners, and callee references from
the existing contracts. Rules must cover arbitrary admitted list lengths and
workflow names without adding scheduler configuration or enumerating examples
as separate rules. Keep realization mode separate from control kind, as defined
in [`goal-oriented-steps.md`](../../specs/formal/workflows/goal-oriented-steps.md).

Existing checks include `test_workflow_semantics_properties.py`, workflow cases
in `test_sdl_validator.py`, and the switch/call and barrier cases in
`test_runtime_models.py`. `test_runtime_manager.py` covers result/history refusal.

Use `WorkflowStepType` for the eight-kind list, not property-test samples.
The property generator omits `switch` and includes synthetic non-observable kinds.

These tests check contract and validation behavior.
They do not prove all parallel schedules or real backend execution.
Current history checks cover event kinds, targets, and some ordering rules.
They do not prove first-match selection or complete interleaving causality.
Keep local checks targeted.

Non-goals are runtime changes, scheduler implementation, new step kinds,
recursive calls, new result fields, schema publication changes, and backend
qualification. Do not add duplicate transition engines, validation hierarchies,
or formal-tool dependencies to close a specification coverage gap.
