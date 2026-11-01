# Participant delivery invocation and tool actions

Requirements: DSL-142, API-423, ACT-614.

`participant-invocation-tool-actions/v2` composes an admitted participant
inject delivery with independently admitted participant tool actions. The
composition requires positive tool-affordance support and finite invocation
limits. It does not require an autonomous execution policy.

The runtime MUST admit an invocation against a retained successful delivery,
its installed compiler context, the caller's authority, an exact participant
implementation selection, a live episode, and the delivery's shared-time
window. It MUST assign the invocation its own execution scope and the current
runtime execution generation. A delivery is not an action contract. The
invocation MUST NOT invent an enclosing action contract or scheduler policy.

For every child, admission MUST resolve exactly one compiled affordance,
participant, action contract, observation boundary, target relation, and
execution offer. One offer MUST cover all required temporal-contract digests.
The child MUST retain its originating delivery and invocation coordinates.
Admission and dispatch use distinct, content-bound crossing references.
They retain one child action identity; dispatch includes the actual dwell evidence.

Admission and dispatch MUST each obtain a current authority cut and pass the
existing participant crossing, composed-control, and final-sink gates. A
controlled delivery MUST still refer to the exact accepted, current control
application. Revoked authority, stale control, changed bindings, or refusal
MUST produce no dispatch grant. The runtime MUST return the exact
canonical binding to the executor. A transformation that replaces the child identity MUST be refused.
Dispatch MUST refuse a binding changed since admission.

Each shared-time guarantee MUST use a child-specific context from the
existing authoritative clock. Dispatch MUST reject a changed clock segment,
an expired deadline, or a dwell condition without valid continuous evidence.
Terminal assessment MUST use the existing evidence and temporal-history
validators. Missing, foreign, stale, or invalid evidence MUST NOT establish
satisfaction. The action outcome and temporal assessment remain separate.

Dispatch MUST consume one durable grant before returning permission to act.
A repeated dispatch MUST NOT grant permission again. Exact admission and
completion retries MUST NOT duplicate the effect or history. Conflicting
reuse of an identity MUST be refused.

Each child MUST have its own operation record. Terminal settlement MUST
publish its typed outcome, three-event behavior history, and audit together
against the current snapshot. History MUST retain the child, invocation,
delivery, affordance, call, scope, generation, ordinal, and settlement. It MUST
survive failure or cancellation of the enclosing invocation.

Closure MUST withhold admitted children and classify dispatched children
without an outcome as indeterminate. Late calls MUST receive no authority to
publish. Recovery MUST use retained bindings to classify interrupted children
without replaying their effects. Uncertain effects MUST remain fenced until
the existing recovery authority resolves them.

The runtime MUST retain its single state writer, effect reservation,
interaction-conflict reservations, and bounded foreign-call supervision.
Child handlers MUST receive only a private invocation-scoped handoff to the
existing writer. The public mutation guard MUST continue to reject extension
callback reentry.
