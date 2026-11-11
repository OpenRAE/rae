# Safe-state declarations

Status: normative.
The optional `safe_state` section declares a desired state and the observations that establish it.
It applies to nodes and eligible services.
It grants no execution or observation authority.
The backend supplies the mechanism.

## Fields

`safe_state` contains an optional complete `default` and up to 256 `scopes`.
Each scope contains `namespace`, `scope`, and a complete `state`.
The namespace defaults to the empty module path.
The scope defaults to the empty root pointer.
Scopes use canonical RFC 6901 semantic addresses, including keyed service identities.
Positional service indexes MUST NOT select a safe-state scope.

| State field | Meaning |
| --- | --- |
| `schema_version` | `safe-state/v1`; other versions are invalid. |
| `kind` | Required: `safe-hold`, `controlled-stop`, or `continue`. |
| `continuing_mode` | Required only for `continue`; a nonempty identity for the intended mode. |
| `assertion_refs` | One to 64 unique assertion references that establish the desired state. |

References and mode identities have at most 2048 characters and contain no whitespace.
Semantic pointers have at most 4096 characters.
Namespaces have at most 31 segments.
Unknown fields MUST be rejected.

## Resolution

The reference eligibility policy defines safe-state targets.
Targets are nodes, named node services, and top-level database, DNS, file, mail, and datastore services.
Runtime children and unnamed transport ports are not targets.
Service declarations identify transport bindings or logical services; they do not establish live processes.

The nearest defining module and semantic scope supply the complete state.
Fields from different declarations MUST NOT combine.
Duplicate namespace/scope pairs MUST be rejected.
A root default duplicates an explicit empty root scope.

Each scope MUST resolve to at least one eligible target in its namespace.
Fields below a target are not valid scopes.
Import and declaration order MUST NOT decide precedence.

Imported defaults remain local to their defining module.
Composition MUST preserve private and repeated imports and rewrite their proof references.
A more specific state affects only its descendants.
An omitted declaration supplies no state and MUST preserve existing scenario validation.
An IT/OT label, exception type, or device class MUST NOT select a state.

## Observed proof

Every selected assertion MUST be a positive postcondition.
Its proposition MUST use `observed_state` with the `all` subject quantifier.
Every assertion MUST include the exact affected target among its canonical subjects.
Each proposition's evidence requirements MUST cover that target through their source or scope references.
Evidence for one scope member MUST NOT prove another member's state.
An unresolved or ambiguous proof reference MUST be rejected.

The existing typed predicates define the observable conditions.
For a continuing mode, those conditions define the intended mode's observed state.
Existing proposition truth semantics govern missing, unsupported, and inconclusive observations.
A backend acknowledgement or declared-state predicate does not prove the state was reached.
Declaration admission validates the proof contract; it does not evaluate live state.

## Plan commitment

Each native phase plan carries `safe_states`, a collection of resolved declarations.
Each entry identifies `target_ref`, canonical `scope`, `governing_scope`, lexical `namespace`, and complete `state`.
Its `proofs` map retains the exact assertion, proposition, and resolved evidence requirements.
Proposition subjects and evidence source/scope references use canonical declaration addresses.
Targets MUST be unique.
The collection has at most 4096 entries.

Resolution MUST enforce `PLAN_VALUE_LIMITS` before it copies proofs.
Native plans MUST check this limit before they copy the collection.
Proof and evidence maps MUST reject whitespace keys and values outside their declared types.

Each admitted trial entry carries the same collection for its selected scenario.
Trial sealing and native plan commitments MUST include this collection.
Trial compilation MUST count the bytes in each entry.
It MUST check `max_plan_bytes` before it stores more entries or seals the plan.
Inspection, HTTP reconstruction, preparation, and authorization MUST preserve it.
Unchanged resources and services without native operations retain their declarations.

No-op plans retain the collection.
Deletion MUST NOT derive a state for an absent resource from current defaults.
Recovered plans MUST retain the admitted value instead of resolving new source defaults.

This declaration adds no safe-state execution procedure or automatic failure response.
Retry, cancellation, cleanup, physical safety, backend support, and operator authorization retain their separate admission rules.

## Example

This scenario declares an observed hold condition for one node.
The assertion and evidence requirement describe proof; no device operation occurs during validation.

```yaml
name: cooling-hold
nodes:
  pump: {type: compute, os: linux}
safe_state:
  scopes:
    - scope: /nodes/pump
      state:
        kind: safe-hold
        assertion_refs: [held]
assertions:
  held: {proposition: held, role: postcondition}
propositions:
  held:
    description: The pump reports the specified hold condition.
    subjects: [nodes.pump]
    basis: observed_state
    predicate:
      kind: boolean
      property: hold_confirmed
      semantic_ref: urn:example:cooling:hold-confirmed
      expected: true
    evidence_requirements: [hold-readback]
evidence_requirements:
  hold-readback:
    source_refs: [nodes.pump]
    scope_refs: [nodes.pump]
    window: safe-state-verification
    channel: api_response
    sensitivity: plain
    redaction: none
    integrity: checksum
    retention: run_lifetime
    loss_disclosure: required
```

The example property URI is illustrative.
An executable backend must support the selected property semantics and the separately admitted mechanism.
