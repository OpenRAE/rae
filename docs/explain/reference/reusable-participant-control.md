# Reusable participant control

Issue #1364 adds an explicitly installed RUN-310 control path for
`mixed-control-policy-occurrence/rev1`. It produces API-409 v2 occurrences;
legacy policies and v1 occurrence bytes retain their original interpretation.
The [normative relation](../../../specs/formal/participant-semantics/reusable-mixed-control.md)
and [ADR-110](../../decisions/adrs/adr-110-reusable-mixed-control-policies-and-occurrences.md)
remain the semantic authorities.

## Installation and live authority

Install `MixedControlRuntimeBinding(model=compiled_model, resolver=cut_owner)`
as the control plane's `mixed_control` option, alongside the same compiled
`behavior_specifications`. The model must retain its instantiated compiler
context. The compiler's `occurrence_policy_projection()` resolves canonical
controller, grant and scope identities; raw policy dictionaries are insufficient.

The installed owner implements `resolve_cut(policy, intent, snapshot)` and
returns `ParticipantControlLiveCut`: the request identity, independently admitted
effective order, active authority bases, authorized scopes and resolved evidence
references. `intent=None` requests initial episode authority. The owner must
establish those facts from its admitted ordering, grant and evidence authorities;
echoing caller input establishes no authority. Orders belong to the named
participant/episode/policy domain. They are not host timestamps or shared-time
ticks. Equal or ambiguous group coordinates have no winner.

Callbacks receive detached inputs through the existing bounded control lane,
outside the state writer. Callback re-entry cannot mutate the runtime. A changed
snapshot cut invalidates the evaluation. Source and destination authority, scope,
inclusive windows and occurrence-specific completion evidence must all hold.

The existing episode lifecycle validates initial authority before invoking the
episode owner and retains the original policy projection and admission evidence
with its atomic operation record. Reopening the store reconstructs state using
those original admissions and the shared API-409 fold. Missing or conflicting
historical context is an error. Initial authority, state revision zero and
episode initialization are distinct from a control occurrence.

## Applications, groups and retries

Each existing kind-specific caller intent carries an `application` object with
the semantic pin, `policy_ref`, `prior_state_ref`, `expected_history_head`,
`effective_order` and optional `script_step_ref`. The intent's existing
`expected_state_revision`, proposal/target coordinates and evidence still apply.
Counts are exact bounded integers: booleans, floats and numeric strings are
rejected. HTTP ingress additionally rejects duplicate members, excessive depth,
non-finite JSON and oversized bodies before conversion loses ambiguity.

`record_participant_control()` appends one application. For a competing group,
`record_participant_controls(participant, [(intent, retry_key), ...], identity=...)`
checks distinct coordinates and a common episode before applying the group in
admitted order. Each contender is evaluated against newly committed state;
stale input is rejected without rebasing. A group contains at most 256 requests.

Accepted same-state transitions and denials advance state revision once.
Rejected attempts preserve their attempted coordinates and the observed cut;
they advance append position, never accepted state, order or script cursor.
Finite scripts use the same relation and stop at exhaustion. Every handoff
requires fresh resolved completion evidence. New cycles use fresh proposal,
decision, occurrence and operation identities.

Current transport/subject authorization precedes exact receipt lookup. An
identical retained retry returns its receipt before evaluating today's episode,
grants or crossing policy. Changed semantic content or episode under the same
principal/operation-kind/client key conflicts. A process restart retains the
episode; reset or restart follows the existing lifecycle and admits a new pin,
revision zero and script cursor without deleting historical facts.

Selections linked to a control proposal recheck its current lifecycle and live
approval before native or governed action dispatch. The installed owner must
also supply `resolve_action_cut(policy, request, snapshot)` for such actions,
resolving the exact payload binding, current grants, scopes and order. Missing
support fails closed. An unrelated proposal reference does not gain approval
from a matching action contract or the most recent event.
References to controlled proposals from an ended episode are rejected before
any current-episode lookup; restarting requires a fresh proposal and approval.

## Cancellation acceptance and work outcome

A successful control operation records an accepted cancellation fact. It carries
no cancellation-effect claim inside the v2 occurrence. Its atomic operation
record retains the exact target, invocation binding and deterministic backend
control identity. An admitted-action or attempt target must join its actual
participant execution owner; generic operation-provider availability cannot
substitute for that join.

After recording, call
`dispatch_participant_cancellation(control_operation_id, identity=...)` or
`POST /operations/{id}/participant-cancellation/dispatch`. Delivery uses the
originating principal's recorded authority and independently authorizes the
supervised parent. The drain caller lends no authority. Inspect
`participant_cancellation_status()` or
`GET /operations/{id}/participant-cancellation` for separate control disposition,
backend disposition and evidenced effect. Readback requires current operation
and participant-subject access; HTTP responses are uncacheable.

| Effect | Required retained owner evidence |
| --- | --- |
| `prevented` | Durable invalidation before linked admission with no escaped/in-flight work, an unconsumed invocation durably cancelled before dispatch, or validated absent effects and cessation. |
| `partial-limitation` | Validated residual scope and native residual state, with established cessation/limitation and the target's release commitment. |
| `too-late` | Validated completion or complete effects at the exact target's terminal settlement. |
| No established effect | Missing/refused/unsupported acknowledgements, uncertain native interruption, unvalidated effects, or unproved cessation. |

Proposal/decision prevention is retained atomically at the cancellation cut,
bound to the exact target and occurrence. Later unrelated work cannot erase
that evidence. Missing proof at the original cut remains an unknown outcome.

A backend acknowledgement undertakes cancellation; it does not prove cessation.
One-use delivery claims and native terminal commits remain authoritative. A
retained control whose delivery was never claimed can resume within its original
remaining allowance. A consumed delivery identity is never resent to discover
its outcome. Expired or unverifiable clock continuity does not acquire a new
budget; subsequent observation/reconciliation uses its own authorized control.

Cancellation facts use the existing bounded supervisory writer and HTTP control
lane, including while effects stall or effect admission is stopped. The durable
claim exemption is limited to effect-free cancellation records without an
invocation grant. New effects remain excluded. A late native result cannot erase
an intervening control fact: stale effect knowledge becomes indeterminate and
requires resolution. A native participant batch without an exact supervised
invocation supplies no interruption guarantee.

## Adoption boundary

This installation enables the configured control owner, not a blanket backend
capability. Ordinary planner/manager, unsupported directed-delivery joins,
API-423/424 consumer versions and capability lists retain their refusals until
their complete selected path supports the semantic pin. API-409 occurrence v2
and API-424 evaluation v2 remain independent lineages. The snapshot envelope
preserves both occurrence versions; full reconstruction still requires each
episode's original context. Explicit legacy declarations can be supplied as
`MixedControlRuntimeBinding.legacy_declarations` for a mixed archive.

Construction admits reusable directed delivery only with a matching compiled
`ParticipantInjectRuntimeBinding`, crossing-policy owner, and `resolve_delivery_cut`.
The [inject guide](../../public/guides/external-injects.md#compose-an-explicit-participant-delivery)
describes the exact control/result join and its local delivery boundary.
Missing bindings or resolvers still refuse construction.
A combined reusable-control and mixed-runtime binding remains unsupported.
The [support table](revised-control-semantics.md#supported-arrangements) keeps these arrangements separate.

The implementation claims bounded, tested control/cancellation behavior. It
does not imply universal rollback, remote cessation from local fencing, or
exactly-once external effects. See the
[backend supervision reference](backend-operation-supervision.md) for operation
evidence, indeterminate exclusion and reconciliation.
