# Runtime result admission

This contract defines the result boundary for ASR-532. It applies when a manager or an authenticated control plane calls a backend.
The backend proposes a result. The runtime decides which portable state it can accept.

## Trusted inputs and effects

The runtime MUST retain an isolated immediate predecessor and admitted request.
The runtime MUST check input and result shapes and canonical addresses.
It MUST also check nested value bounds and total work bounds before it copies, hashes or publishes the result.
Native service dependencies remain injected services, not copied state carriers.

The submitted plan defines each resource address, authored identity and type.
It also defines its runtime domain, dependencies and admitted profile completion. A backend
MUST NOT rewrite these, change unrelated resources, or mutate runtime-owned
metadata or provenance. A digest supplied by the caller does not prove plan identity.
The identity of the caller on the transport does not prove it either.

An additional portable node requires the explicit enclosing collection relation.
Initial selection can use the preparation contract in
[backend realization preparation](../../sdl/backend-realization-preparation.md).
Runtime discovery and later refresh can use the negotiated
[descendant inventory extension](../../sdl/materialization-attestation.md#runtime-descendant-inventory).
The runtime projects those admitted resources from descriptive SDL after the legacy proposal checks.
The backend cannot add unplanned entries or write runtime-owned provenance directly.
A resource absent from the author's operation list is not thereby allowed to join the collection or be removed.

Other snapshot carriers keep their own domain rules.
An operation on one participant, execution service or clock does not grant access to other state in that domain. Execution-service effects may cover only the scope of its trusted existing scheduler. Coordinated clock reset names the clock and
the admitted participant reset batch. Rights over a resource target do not grant rights over other carriers with the same key. Native participant
and shared-time history validators remain mandatory.

## Transition accounting

For a successful plan result:

| Operation | Required transition | Change claim |
| --- | --- | --- |
| CREATE | Absent predecessor to present admitted resource | Required |
| UPDATE | Present resource to present admitted resource; equal-payload dependency refresh is valid | Required |
| DELETE | Present predecessor to absent resource | Required |
| UNCHANGED | Preserve resource semantics and identity | Forbidden |

Status annotations alone are not resource-semantic changes. The result MUST also report actual changes to addressed carriers.
Each reported address MUST resolve to a permitted transition. Linked disclosure-record IDs keep their own reference and history rules.
They MUST NOT be reported as invented resource change addresses.
Cleanup after partial failure still needs identity, ownership and accounting checks.
It cannot claim successful conformance.

## Admission and publication

The runtime MUST check actual declared values and the members of each collection against the original nested constraints.
The overall explicitness level does not replace these checks.
Prepared delivery MUST also match the admitted completion.
Its own canonical comparison defines a match. Typed JSON equality distinguishes `true` from `1`,
including inside profile bindings and unchanged resources.

The runtime MUST still check native meaning and required capabilities.
It MUST also check the scope and strength of each observation.
A choice is not an observation.
A precise declaration or a prepared result does not require study data to be captured, kept or exported.
Selected demand still governs those actions.

Results with credentials MUST satisfy their closed egress contract.
It checks them against the admitted operation values. Admitted realization concerns MAY contain
observed values that differ from those operation values, including OPEN choices.
This permission applies only to registered concern paths.
Each path must have an admitted requirement that applies and a safe observation projection. All other payload values MUST keep typed exact equality with the admitted operation.
Separately permitted evidence, such as `artifact_satisfaction`, is an exception.

The owning concern validator MUST check observed values before projection.
Credential closure MUST preserve their safe observation projection.
It MUST NOT restore plan values over those observations.
Canonical account material remains presence-only.
Comparison and publication MUST preserve the same permitted meaning.
The runtime MUST check safe projected state again before it adds provenance and commits the state.
This second check may reuse admitted transient observations.
It MUST NOT collect or retain new ones. If sanitization fails, later comparisons against the rejected candidate MUST NOT replace its diagnostics.

If a success claim fails these checks, the runtime MUST return `success=false` and the immediate trusted predecessor.
It MUST return empty changed addresses and no candidate details or success provenance. A structured diagnostic MUST name the rule that failed.
It MUST NOT expose rejected secret values or backend exception text. Manager state,
control-plane durable state and subsequent recovery MUST agree on this outcome.

This contract does not certify backends or roll back infrastructure.
It does not contain hostile backends or prove that every claimed capability is true.
It does not allow apply to be replayed on its own.

Inventory refresh is an explicit provisioning mutation with read-only backend behavior.
Its committed discriminator selects inventory reporting rather than apply.
The planner must still authorize the plan.
Target and run identities remain bound. Each new request gets a fresh operation attempt.
Saved retries, supervision and the terminal snapshot commit still apply.
The collector returns an unchanged predecessor and a separate SDL report.
Incomplete or invalid reports preserve the trusted predecessor.
The native artifact digest binds the original backend proposal before and after the checks.
The terminal accepted-state commitment separately binds the runtime-derived snapshot.
