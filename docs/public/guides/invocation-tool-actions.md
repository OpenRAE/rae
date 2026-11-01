# Admit participant tool actions

RAES checks each tool call before it can have effects. Each child has its own
ID, a grant to act once, a typed result, and a saved history.

Choose one of two ways to host tool calls:

| Composition | Enclosing execution | Required method |
| --- | --- | --- |
| `participant-invocation-tool-actions/v1` | Autonomous action invocation | `attach_invocation_tool_actions(port)` |
| `participant-invocation-tool-actions/v2` | Runtime-owned delivery invocation | `invoke_delivery(invocation, tools)` |

V1 keeps its policy and outer action history. V2 starts from a saved delivery
and has its own scope. V2 needs no autonomous policy or outer action contract. [ADR-092 section 10](https://github.com/OpenRAE/rae/blob/main/docs/decisions/adrs/adr-092-autonomous-benign-participants-under-shared-time.md)
and the [delivery-tool contract](https://github.com/OpenRAE/rae/blob/main/specs/formal/participant-semantics/delivery-tool-actions.md)
define the rules.

## Declare the relation and capability

Declare `tool_affordances` under the behavior specification. Name the permitted
action contracts and observation boundaries, and classify each affordance in
its boundary. The compiler joins the specification's participants and each
action's authored targets.

Declare positive `tool_affordances` support, an exact execution-binding offer
for each action and implementation, and finite invocation limits:

```json
"invocation_tool_actions": {
  "semantic_versions": ["participant-invocation-tool-actions/v2"],
  "max_tool_actions_per_invocation": 16,
  "max_concurrent_tool_actions_per_invocation": 4
}
```

Each offer must cover all shared-time contract digests for its action.
RAES checks that the claimed method exists. V1 also needs support for
autonomous execution.

## Invoke a retained delivery

First use `deliver_participant_inject` to admit and retain the delivery. Then
call the runtime's public `invoke_participant_delivery(request, identity=...)`
with a `ParticipantDeliveryInvocationRequestModel`. The request names the
saved delivery, a stable request key, and the exact manifest and selection for
the participant.

Install the delivery resolver's `resolve_invocation_cut(invocation, request,
snapshot)` method. It returns a typed `ParticipantControlLiveCut` for the
child request and current order, grants, scopes, and evidence. RAES
checks the cut against its authority and control rules.

The participant runtime implements
`ParticipantDeliveryInvocationRuntime.invoke_delivery`. RAES passes a detached
typed context and a `ParticipantDeliveryToolActionPort`. Return a
`ParticipantDeliveryInvocationOutcomeModel`; the outer result cannot replace
runtime history or claim a child's success.

## Use the child port

1. Build a `ParticipantToolActionRequest` using the port's invocation,
   participant, episode, implementation, scope, and generation coordinates.
2. Call `admit(request, crossing_evidence=...)`. Evidence is a typed
   `ParticipantCrossingEvidence`. A refusal supplies no permission to act.
3. Call `dispatch(action_id, temporal_evidence=...)`. Continuous dwell evidence
   belongs here. Use the returned canonical `binding`, which includes any
   child-specific temporal contexts. A transformation that replaces the child
   identity is refused.
4. Execute the bound action once, only after an accepted dispatch receipt.
5. Call `complete(action_id, outcome)` with the exact typed action identity,
   observation point, and authorized evidence. Deadline event evidence belongs
   in the outcome. Call `report_unknown` when the effect cannot be established.

Both admission and dispatch recheck current authority, source control, crossing
policy, and the final sink. Dispatch also checks the clock segment, deadline,
and dwell coverage. Missing proof cannot show that a timing rule was met.

## Retries, closure, and history

| Event | Runtime result |
| --- | --- |
| Exact repeated admission | Original decision; no new child |
| Conflicting call identity | `request_conflict` |
| Repeated dispatch | Refused; no second grant |
| Exact repeated completion | Original receipt; no duplicate history |
| `cancel` before dispatch | Withheld child |
| Unknown dispatched effect | Indeterminate child and effect fence |
| Invocation closure | Withhold pending children; classify unresolved dispatched children as indeterminate |
| Call after closure | `invocation_closed` |

V2 saves each child result, its three history events, and its audit in one
write. The child's `invocation_tool_context` names its source call and delivery.
It needs no outer action. If the outer call fails or is cancelled, the child
history stays.

Read child state with `get_operation(action_id)` and history through the
existing participant history views. After a restart, RAES uses saved bindings to settle
children. It never repeats an effect. Use the existing recovery process to
resolve unknown effects.

V1 retains its original restrictions: no shared-time tool binding, no V3
resource policy, and no installed participant-crossing policy. Its child
history remains ordered before the enclosing autonomous action's history.
