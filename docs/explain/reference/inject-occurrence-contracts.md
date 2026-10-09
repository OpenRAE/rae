# Use the inject trigger, occurrence and readback contracts

[ADR-112](../../decisions/adrs/adr-112-external-inject-triggering-and-execution.md)
and [EI-01–EI-06](../../../specs/sdl/external-injects.md) define how an
authorized external request instantiates one authored inject. Four draft
contracts carry that path as portable data with pure validators:

| Contract | Carries |
| --- | --- |
| `inject-trigger-request-v1` | A caller's selection of one inject, its bindings, placement and input. |
| `inject-occurrence-v1` | The atomic claim of one occurrence under exact admitted pins. |
| `inject-occurrence-outcome-v1` | Per-binding readback for one claimed occurrence and its settlement. |
| `inject-occurrence-correlation-v1` | The exact applied occurrence, outcome and produced result that a participant consumer joins. |

They add no trigger route, store, scheduler, operation kind or backend call, and
the existing runtime does not accept them.

Import the models and helpers from `raes_contracts.contracts`, and
`require_inject_occurrence_provider` from
`raes_backend_protocols.operation_supervision`. The schemas are under
`contracts/schemas/control-plane/`, and the examples are under
`contracts/fixtures/control-plane/inject-*` and
`contracts/fixtures/control-plane/backend-operation-request-v1/valid/inject-*`.
The request names existing compiled `orchestration.inject`,
`orchestration.inject-binding`, `orchestration.event`, `orchestration.script`
and `orchestration.story` addresses, so no processor binding changes.

## Request

`InjectTriggerRequestModel` is a caller's selection within admitted intent.

| Field | Meaning |
| --- | --- |
| `request_key` | Client retry key. The ADR-104 store scopes it by actor and operation kind in one target/run store (EI-02). |
| `occurrence_id` | Fresh logical occurrence. A repeat needs a fresh occurrence and a fresh key. |
| `target_scope`, `run_scope` | The exact target and run. |
| `plan` | Content-bound pin of the compiled `orchestration-plan-v1`. |
| `inject` | Canonical `orchestration.inject.*` address. A request names one inject, not a whole event. |
| `bindings` | One or more selected compiled node bindings. Each names its `orchestration.inject-binding.*` address, the compiled `provision.node.*` node it binds, a realization instance and its revision. Each binding/instance pair appears once; nothing selects every host or the first matching name. |
| `placement` | `independent`, `event` (the event's assertions stay binding) or `schedule` (event, script, optional story and a slot that can be claimed once). |
| `input_ref` | Optional content-bound reference to an input document that the realization's input contract checks. There are no inline values, and absence means no runtime parameters. |
| `expected_head` | The ordering head the caller observed. A stale head is refused, never rebased. |

### Binding addresses

The compiler renders a node binding as
`orchestration.inject-binding.<node>.<inject>`, and module namespaces put dots
inside both names. When a scenario imports a module under namespace `mod`,
`orchestration.inject-binding.mod.host.mod.release` binds node `mod.host` to
inject `mod.release`, yet it also ends in `.release`. The end of an address
therefore doesn't show which inject it binds.

Local validation requires each binding address to equal the rendering of its
`node` and the requested inject. Carrying node `provision.node.mod.host`, that
binding can't serve a request for `release`. Local validation can't see the
plan, so it doesn't show that the node exists or that the plan records this node
for the binding. A consumer resolves both against the pinned plan's
`inject-binding` operations.

This revision selects only `Node.injects` bindings. Under EI-01, a top-level
inject without `Node.injects` runs only through its realization's explicit target
contract, which this revision doesn't carry.

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
| A reused retry key, occurrence, operation, schedule slot, order position or order predecessor in one store | `validate_inject_occurrence_claims` rejects the claim set. |
| A fresh key and fresh occurrence for the same inject | Valid; admission checks every current constraint again. |

Two claims that follow the same head would fork the run's order, so each
predecessor is claimed once. Head tokens are opaque, so the claim set can't
check that a predecessor is the head that the preceding claim produced. That
chain belongs to the ordering authority (EI-03).

`inject_trigger_request_digest` and `inject_occurrence_digest` return RFC 8785
commitments.

## Invocation

An admitted occurrence executes through one invocation of the optional
[backend operation protocol](backend-operation-supervision.md). The invocation
is a `backend-operation-request-v1` whose `command` is
`inject_occurrence_reference(occurrence)`: the `inject-occurrence-v1` contract
ID, the occurrence ID and the occurrence's RFC 8785 digest.
`require_inject_occurrence_invocation` requires that:

- the invocation binding keeps the occurrence's operation ID and exact
  admission context;
- `requirement_refs` carry every evidence requirement of the occurrence;
- the attempt and invocation IDs differ from the request key, occurrence,
  operation and schedule slot;
- a narrowed `resources` effect scope covers every selected binding.

The check grants no dispatch. A runtime that adopts these contracts (issue
#1367) must still confirm the claim, current authority, preconditions and
backend willingness before it starts the work.

## Readback and settlement

`InjectOccurrenceOutcomeModel` carries one backend response and the facts for
every selected binding, in request order. The `effect` field must aggregate the
per-binding facts (EI-04):

| Per-binding facts | `effect` |
| --- | --- |
| Every binding applied, with cessation established | `effect-applied` |
| Every binding proven absent, with cessation established | `effect-absent` |
| A fully known mixture, or a binding with known partial effects | `known-partial` |
| Any unknown binding, or one whose cessation is not established | `indeterminate` |

An applied or partial binding needs a `readback` reference, and every known
effect needs evidence. Only a backend `outcome` or a refused start settles an
occurrence. Acceptance, willingness, progress and control dispositions do not.
A refused start is the `acknowledgement` refusal from `start_operation`, which
proves that the invocation never began. It settles only as `effect-absent`,
with no-effect evidence for every binding. A backend outcome's own effect must
agree with the aggregate, and it counts as `indeterminate` until cessation is
established. A `succeeded` proposal requires `effect-applied`, so no successful
no-op settles an inject.

An `admission` refusal from `check_operation` comes before dispatch, so it is
not readback, and an outcome that carries one is invalid. EI-03 withdraws that
occurrence with zero dispatch and a retained claim. Under the ADR-104
[supervision contract](../../../specs/formal/runtime-control-plane/supervision.md)
(S3), a contextual refusal after the claim but before dispatch withdraws the
acceptance through `CANCELLED` with a refusal diagnostic.

`validate_inject_occurrence_outcome` joins the readback to the exact occurrence
and invocation, including the response binding and request digest. When the
invocation narrows its effect scope to `resources`, each binding's
`residual_scope` must stay inside those addresses, as
`validate_backend_operation_response` requires of the backend's own residual
effects. A runtime that adopts these contracts must still validate native
results and commit the terminal operation, snapshot and audit records.

## Participant correlation

`inject_occurrence_correlation` returns an `InjectOccurrenceCorrelationModel`
only for a validated outcome whose backend proposal is `succeeded` with a
produced result. It names the occurrence, the outcome digest and the result.
A participant-directed consumer, such as a DSL-142 delivery or an API-424
inject effect, joins those exact identities instead of an inject declaration
or the latest narrative event (EI-05). A refused, failed, partial or
indeterminate outcome yields no join. A correlation grants no disclosure,
delivery or observation, so build it only from an outcome that an adopting
runtime has validated and committed.

A consumer that receives a correlation checks it with
`validate_inject_occurrence_correlation`. The check recomputes the join from
the occurrence, invocation and outcome, and requires the received correlation
to equal it, so a changed occurrence, outcome digest or result is refused.

## Backend declaration

A backend that executes inject occurrences declares `inject-occurrence-v1` and
`inject-occurrence-outcome-v1` in its manifest, together with the four
`backend-operation-*-v1` contracts, and installs `BackendOperationProvider`.
`require_inject_occurrence_provider` checks both declarations and the
installed call shapes without invoking anything. Inject-binding support and a
successful plan start are not this declaration (EI-06). The stub and
reference backends do not declare these contracts.

## Migration and compatibility

| Existing surface | Migration rule |
| --- | --- |
| Inject, event, script and story authoring | Unchanged. No SDL field is added; live triggering still needs an admitted realization (EI-01). |
| Bound or queued orchestration snapshots and plan-start receipts | Keep their original status meaning. They never become an applied effect, delivery or observation. |
| DSL-142 deliveries and API-424 inject effects | Unchanged. Legacy fixed anchors keep their required fields; a consumer that adopts these contracts joins a correlation explicitly. |
| Backend manifests and profiles | The allowlist gains the two backend-facing IDs. Existing manifests and profiles stay valid; old closed readers can reject the new IDs. |
| `operation-receipt-v1`, `operation-status-v1` and stored operations | Unchanged. This publication adds no operation kind, store record or HTTP route. |

No lossless conversion produces these carriers from legacy records. Do not
fabricate occurrence IDs, order tokens, readback evidence or results. The four
contracts are draft v1 publications under ADR-009 and ADR-061, and each
publication entry records its content hash and contract-facing change.

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
`orchestration.inject-binding.host.release` on node `provision.node.host`,
anchored to `gate`. The caller is an authenticated operator, not a participant
or controller. `test_issue_1423_inject_occurrence_contracts.py` compiles this
environment and checks that the fixture names only its compiled identities. It
also imports the same environment under namespace `mod` and checks that each
compiled binding serves only its own inject. The `namespaced-binding.json`
fixture is the refused case. The `inject-release` invocation commands that
occurrence, the outcome fixture reports an applied effect with readback, and
the correlation fixture joins its result.

The `scheduled-fan-out` occurrence selects two workstation instances of one
compiled binding. Its `inject-handover` invocation narrows the effect scope to
that binding address. The `known-partial` and `indeterminate` outcome fixtures
show a fully known mixture and an unknown binding. On the participant-free
occurrence, the `refused` fixture shows a refused start with proven absence,
and the `unceased-effect` fixture shows an applied effect whose cessation is not
established, which stays indeterminate.
`test_issue_1366_inject_occurrence_outcomes.py` validates each outcome against
its occurrence and invocation.

## Limits

Fixture digests, scopes and evidence references are synthetic. Structural and
local validation grant no trigger authority and prove no effect, delivery or
observation. Authentication, admission, binding resolution against the pinned
plan, ordering, claims, dispatch, outcome validation and terminal commits
belong to the runtime and backend adoption that the
[compatibility contract](../sdl/external-inject-compatibility.md) describes.
