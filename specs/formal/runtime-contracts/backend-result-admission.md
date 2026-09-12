# Backend result admission

This is the normative execution-boundary contract for ASR-532. It applies to
direct-manager and authenticated control-plane backend invocation. Backend
results are proposals, not authority over accepted portable state.

## Trusted inputs and effects

The runtime MUST retain an isolated immediate predecessor and admitted request.
Input and result shapes, canonical addresses, recursive value bounds and total
work bounds MUST be checked before recursive isolation, hashing or publication.
Native service dependencies remain injected services, not copied state carriers.

A submitted plan owns resource address, authored identity, resource type,
runtime domain, dependencies and any admitted profile completion. A backend
MUST NOT rewrite these, change unrelated resources, or mutate runtime-owned
metadata or provenance. Plan identity cannot be inferred from a caller-supplied
digest or authenticated transport principal alone.

An additional portable node is permitted only under the explicit collection
and preparation contract in
[backend realization preparation](../../sdl/backend-realization-preparation.md).
Its omission from the author's operation list is neither a universal prohibition
nor permission to invent membership after apply.

Non-resource snapshot carriers retain their specialized domain owners. An
operation on one participant, execution service or clock does not grant access
to unrelated state in that domain. Execution-service effects may cover only its
trusted existing scheduler scope. Coordinated clock reset names the clock and
the admitted participant reset batch. Resource-target authority does not grant
authority over other carriers whose keys happen to coincide. Native participant
and shared-time history validators remain mandatory.

## Transition accounting

For a successful plan result:

| Operation | Required transition | Change claim |
| --- | --- | --- |
| CREATE | Absent predecessor to present admitted resource | Required |
| UPDATE | Present resource to present admitted resource; equal-payload dependency refresh is valid | Required |
| DELETE | Present predecessor to absent resource | Required |
| UNCHANGED | Preserve resource semantics and identity | Forbidden |

Status annotations alone are not resource-semantic changes. Actual addressed
carrier changes MUST also be reported, and every reported address MUST resolve
an authorized transition. Linked disclosure-record IDs are governed by their
native reference/history contract, not fabricated resource change addresses.
Honest partial failure cleanup remains subject to identity, ownership, and
accounting checks; it is not a successful conformance claim.

## Admission and publication

The runtime MUST compare actual declared values and collection coverage against
the original recursive constraints, independently of aggregate explicitness.
Prepared delivery also MUST match the admitted completion under its owning
canonical comparison. Typed JSON equality distinguishes `true` from `1`,
including inside profile bindings and unchanged resources.

Every applicable native semantic, capability, observation-scope and
observation-strength requirement remains binding. Selection is not observation.
Neither precise declarations nor preparation create experimental capture,
retention or export requirements. Those remain governed by selected demand.

Credential-bearing results MUST satisfy their closed egress contract against
the admitted operation values before native concern sanitization. Comparison
and publication MUST preserve the same permitted meaning; safe projected state
is revalidated before adding runtime-owned provenance and committing it. The
second validation may reuse admitted transient observations but MUST NOT collect
or retain new observations. Sanitization failure diagnostics MUST not be
overwritten by secondary comparisons against the rejected candidate.

A rejected successful claim MUST return `success=false`, the immediate trusted
predecessor, empty changed addresses and no candidate details or success
provenance. A structured diagnostic MUST identify the violated invariant without
exposing rejected secret values or backend exception text. Manager state,
control-plane durable state and subsequent recovery MUST agree on this outcome.

This contract does not provide backend certification, infrastructure rollback,
hostile-backend containment, universal capability truthfulness, or permission
to replay apply automatically.
