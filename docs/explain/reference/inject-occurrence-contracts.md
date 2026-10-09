# Use the inject trigger and occurrence contracts

[ADR-112](../../decisions/adrs/adr-112-external-inject-triggering-and-execution.md)
and [EI-01–EI-06](../../../specs/sdl/external-injects.md) define how an
authorized external request instantiates one authored inject. The draft
`inject-trigger-request-v1` and `inject-occurrence-v1` contracts carry those
identities as portable data with pure validators. They add no trigger route,
store, scheduler or backend call, and the existing runtime does not accept them.

Import the models and helpers from `raes_contracts.contracts`. The schemas are
under `contracts/schemas/control-plane/` and the examples under
`contracts/fixtures/control-plane/inject-*`.

## Request

`InjectTriggerRequestModel` is a caller's selection within admitted intent.

| Field | Meaning |
| --- | --- |
| `request_key` | Client retry key. The ADR-104 store scopes it by actor and operation kind in one target/run store (EI-02). |
| `occurrence_id` | Fresh logical occurrence. A repeat needs a fresh occurrence and a fresh key. |
| `target_scope`, `run_scope` | The exact target and run. |
| `plan` | Content-bound pin of the compiled `orchestration-plan-v1`. |
| `inject` | Canonical `orchestration.inject.*` address. A request names one inject, not a whole event. |
| `bindings` | One or more selected concrete bindings: compiled binding address, realization instance and revision. An `orchestration.inject-binding.*` address must name the requested inject. Each instance appears once; nothing selects every host or the first matching name. |
| `placement` | `independent`, `event` (the event's assertions stay binding) or `schedule` (event, script, optional story and a slot that can be claimed once). |
| `input_ref` | Optional content-bound reference to an input document that the realization's input contract checks. There are no inline values, and absence means no runtime parameters. |
| `expected_head` | The ordering head the caller observed. A stale head is refused, never rebased. |

## Occurrence

`InjectOccurrenceModel` records the atomic claim (EI-03). It holds the exact
request, the runtime `operation_id`, the actor-bound `OperationAdmissionContext`,
admission evidence, the expected store revision, the trusted order token, and
the scenario, source, realization and required-evidence pins. Local validation
requires that:

- the admission context is an `orchestration` operation for the requested
  target and run;
- the order token's scope is the requested run and its predecessor is the
  requested head;
- the request key, occurrence, operation and slot are distinct values.

This revision admits inject occurrences only as orchestration operations.
Another operation kind needs a new contract revision with lifecycle, audit,
store and recovery agreement.

## Retries and duplicate claims

| Situation | Helper and result |
| --- | --- |
| Same actor, key and request commitment | `require_inject_trigger_retry` returns the original claim. Nothing is admitted or dispatched again. |
| Changed content, another actor, or another key for the same claim | `require_inject_trigger_retry` raises a conflict. Authorize receipt access before the lookup, so a conflict reveals no other actor's claim. |
| A reused retry key, occurrence, operation, schedule slot or order position in one store | `validate_inject_occurrence_claims` rejects the claim set. |
| A fresh key and fresh occurrence for the same inject | Valid; admission checks every current constraint again. |

`inject_trigger_request_digest` and `inject_occurrence_digest` return RFC 8785
commitments.

## Participant-free example

This environment declares no agents, behaviors, scripts or stories, and the
existing parser and compiler accept it:

```yaml
name: external-trigger-environment
nodes:
  host:
    type: compute
    resources: {ram: 1 gib, cpu: 1}
    roles:
      operator: ops
    injects:
      release: operator
injects:
  release:
    description: Release the staged maintenance notice.
events:
  gate:
    injects: [release]
```

Each `participant-free-environment.json` fixture triggers `release` against
`orchestration.inject-binding.host.release`, anchored to `gate`. The caller is
an authenticated operator, not a participant or controller.
`test_issue_1423_inject_occurrence_contracts.py` compiles this environment and
checks that the fixture names only its compiled identities.

## Limits

Fixture digests, scopes and evidence references are synthetic. Structural and
local validation grant no trigger authority and prove no effect.
Authentication, admission, ordering, claims, dispatch and outcome evidence
belong to the runtime and backend adoption that the
[compatibility contract](../sdl/external-inject-compatibility.md) describes.
