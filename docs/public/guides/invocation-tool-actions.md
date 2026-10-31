# Admit tool actions inside an autonomous invocation

An autonomous participant invocation can call tools while it runs. RAES admits
each tool call as a separate participant action before the tool has effects.
Each tool action gets its own action identity, typed outcome and three-event
behavior history. The composition is `participant-invocation-tool-actions/v1`.
[ADR-092](https://github.com/OpenRAE/rae/blob/main/docs/decisions/adrs/adr-092-autonomous-benign-participants-under-shared-time.md)
section 10 records the decision.

## Author the tool affordance

Declare an authored tool affordance under the behavior specification that owns
the autonomous policy. The affordance names the action contracts and
observation boundaries that a tool call can use. Classify the affordance
reference in that observation boundary.

```yaml
behavior_specifications:
  participant-behavior:
    tool_affordances:
      portal-client:
        action_contract_refs: [probe-customer-portal-login]
        observation_boundary_refs: [participant-view]
```

The compiler joins each affordance with the policy participants. It also joins
the targets that each action contract authors. An unscoped affordance uses the
participants of its behavior specification.

## Claim the composition

Declare the claim in the participant-runtime capabilities. The claim requires
autonomous execution and positive `tool_affordances` support. Declare one
execution-binding offer for each tool action contract and implementation.

```json
"invocation_tool_actions": {
  "semantic_versions": ["participant-invocation-tool-actions/v1"],
  "max_tool_actions_per_invocation": 16,
  "max_concurrent_tool_actions_per_invocation": 4
}
```

Registration refuses the claim when the participant runtime has no
`attach_invocation_tool_actions` method. Without the claim, the runtime attaches
no port, and ordinary autonomous execution does not change.

## Use the port

The runtime calls `attach_invocation_tool_actions(port)` before each matching
`admit_action` call. The port is inactive until that dispatch begins, so calls
made during attachment return `invocation_inactive`. Give the port only to the
harness that runs that invocation. The port never calls the runtime manager, so the harness can use it
from any thread while `admit_action` waits.

```python
from raes_contracts.contracts import ParticipantActionResultModel
from raes_contracts.participant_tool_actions import ParticipantToolActionRequest


class HarnessRuntime(MyAutonomousParticipantRuntime):
    def attach_invocation_tool_actions(self, port) -> None:
        self._ports[port.invocation_action_instance_id] = port

    def _model_action(self, request, snapshot, *, episode_id):
        port = self._ports.pop(request.action_instance_id, None)
        outcome = self._harness.run(request, tool_port=port)
        return self._native_execution(request, snapshot, episode_id, outcome)


def call_tool(port, mcp_request_id: str, run_tool) -> None:
    decision = port.admit(
        ParticipantToolActionRequest(
            tool_call_id=mcp_request_id,
            invocation_action_instance_id=port.invocation_action_instance_id,
            participant_address=port.participant_address,
            episode_id=port.episode_id,
            participant_implementation_ref=port.participant_implementation_ref,
            tool_affordance_address="participant.behavior-specification.participant-behavior.tool-affordance.portal-client",
            action_contract_address="participant.action-contract.probe-customer-portal-login",
            observation_boundary_address="participant.observation-boundary.participant-view",
            target_addresses=("provision.node.customer-portal.service.http",),
            execution_scope_ref=port.execution_scope_ref,
            execution_generation=port.execution_generation,
        )
    )
    if not decision.admitted:
        return  # decision.refusal is a fixed code; do not run the tool.
    if not port.dispatch(decision.action_instance_id).accepted:
        return
    try:
        succeeded = run_tool()
    except TimeoutError:
        port.report_unknown(decision.action_instance_id, "timeout")
        return
    port.complete(
        decision.action_instance_id,
        ParticipantActionResultModel(
            status="succeeded" if succeeded else "failed",
            participant_address=port.participant_address,
            episode_id=port.episode_id,
            action_instance_id=decision.action_instance_id,
            action_contract_address="participant.action-contract.probe-customer-portal-login",
            observation_point=port.observation_point,
        ),
    )
```

Start tool effects only after `dispatch` returns an accepted receipt. The
consumer keeps its own MCP handler, argument validation, transport
authentication, credentials, redaction and process cleanup. RAES does not
receive or store tool arguments or results.

## Admission rules

The port admits a request only when all of these conditions are true:

- The invocation is still open.
- Participant, episode, implementation, invocation, scope and generation equal
  the port values.
- Exactly one compiled affordance binding matches the affordance, action and
  participant.
- The observation boundary and every target belong to that binding.
- The action has no shared-time binding.
- Exactly one manifest execution-binding offer covers the action, the
  implementation and the targets.
- The policy is not `participant-autonomous-execution/v3`, and no
  participant-crossing policy is installed.
- The control-plane store retains the claim. A failed write refuses with
  `ledger_unavailable`.
- The declared limits are not exhausted.

A refusal returns a `ParticipantToolActionRefusal` code. It causes no native
call and adds no history.

## Failure behavior

| Event | Result |
| --- | --- |
| Same `tool_call_id` and same request | The port returns the original decision. |
| Same `tool_call_id` and a different request | `request_conflict`. The original record stays. |
| `cancel` before dispatch | The action settles as `withheld`. |
| `cancel` after dispatch | `state_conflict`. Complete the action or report unknown effects. |
| `report_unknown` after dispatch | The action settles as `indeterminate`. |
| An outcome with withheld or undeclared evidence, or a foreign observation point | `outcome_invalid`. Report unknown effects instead. |
| The invocation returns with undispatched actions | They settle as `withheld`. |
| The invocation returns with dispatched actions and no outcome | They settle as `indeterminate`. |
| A call after the invocation returns | `invocation_closed`. |
| The invocation raises or returns an invalid result | Tool history commits. The outer attempt is consumed. |

An `indeterminate` action records status `unknown` and observation status
`orphaned_action`. It also stops the participant scheduler. RAES never repeats
a tool effect to recover history.

## Read the history

Each settled tool action appends `action_attempted`,
`state_transition_recorded` and `observation_emitted`. The triples follow
admission order, immediately before the triple of the outer invocation. Every
tool-action event carries `invocation_tool_context`. That context names the
outer action instance and contract, the affordance, the tool call identity, the
admission ordinal, the settlement, the scope and the generation. Participant
history views project the same field.

Tool history commits with the enclosing scheduler operation. Each tool action
is also a child operation with its own id. Read its state with
`get_operation(action_instance_id)`. After a restart, an admitted action that
was never dispatched is `cancelled`. A dispatched action without an outcome is
`indeterminate` and needs explicit resolution.
