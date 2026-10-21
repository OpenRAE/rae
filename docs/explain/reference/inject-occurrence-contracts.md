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

The shared runtime accepts these carriers through `submit_inject` and the P2
trigger route when a trusted realization resolver and an explicitly declared
executing provider are installed. The reference OCI realization is opt-in;
see the [operator guide](../../public/guides/external-injects.md). The contracts
add no scheduler or operation kind.

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

Every placement requires an explicit `kind` discriminator, including independent
placement. Both the published schemas and the Python models refuse an omitted
discriminator.

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

The check grants no dispatch. The runtime confirms the durable claim, current
authority, preconditions and backend willingness before its existing one-use
dispatch grant starts the work.

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
occurrence. Acceptance, willingness, progress, control dispositions and
reconciliation records do not. Under EI-04, reconciliation appends linked
evidence and never refires the inject or rewrites the outcome.
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
`inject_occurrence_outcome_digest` returns that RFC 8785 outcome digest.
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
successful plan start are not this declaration (EI-06). The stub test double
does not declare these contracts. RAES ships no executing provider; a backend
distribution supplies one (see
[ADR-115](../../decisions/adrs/adr-115-concrete-backends-owned-outside-raes.md)).

## Migration and compatibility

| Existing surface | Migration rule |
| --- | --- |
| Inject, event, script and story authoring | Unchanged. No SDL field is added; live triggering still needs an admitted realization (EI-01). |
| Bound or queued orchestration snapshots and plan-start receipts | Keep their original status meaning. They never become an applied effect, delivery or observation. |
| DSL-142 deliveries and API-424 inject effects | Unchanged. Legacy fixed anchors keep their required fields; a consumer that adopts these contracts joins a correlation explicitly. |
| Backend manifests and profiles | The allowlist gains the two backend-facing IDs. Existing manifests and profiles stay valid; old closed readers can reject the new IDs. |
| SDL participant behavior specifications | `evidence_contract_refs` may cite `inject-occurrence-v1` and `inject-occurrence-outcome-v1`, which previously raised `participant.behavior-spec-evidence-contract-unbound`. The compiler copies them through, and no runtime path reads them. `inject-occurrence-correlation-v1` still raises that diagnostic. |
| `operation-receipt-v1` and `operation-status-v1` | Unchanged status meaning and no new operation kind. Typed occurrence/outcome/evidence fields extend the internal record codec; local schema 9 and PostgreSQL schema 2 retain historical records without inventing evidence. |

No lossless conversion produces these carriers from legacy records. Do not
fabricate occurrence IDs, order tokens, readback evidence or results. The four
contracts are draft v1 publications under ADR-009 and ADR-061, and each
publication entry records its content hash and contract-facing change.

## Adoption boundaries

ADR-112 defines the semantics; #1367 implements the selected runtime slice. Reuse
ADR-104's operation authority, ADR-110's participant composition and ADR-113's
execution machinery. The following owners apply to consumers of these carriers;
Python paths are relative to `implementations/python/packages/`.

The [#1367 execution preflight](../../decisions/issue-1367-external-inject-execution-preflight.md)
identifies the current native-plan/policy and typed-result assumptions,
missing durable occurrence/order claims, operation-only settlement, API-404
profile limits, restart/ingress trust boundaries, and configuration-bound
executing-adapter evidence requirements.
It records the constraints applied by the implementation. The operator guide
separates supported realization behavior from the broader portable carriers.

| Boundary | Existing owner and adoption rule |
| --- | --- |
| Input | `raes_contracts/json_ingress.py::parse_bounded_json_object` rejects duplicate members and nonfinite numbers; select explicit byte/depth bounds before decoding. Reuse `OperationContractModel`, scalar bounds and contextual validators for direct calls and restored records too. Schema validation alone cannot check cross-message joins. |
| Authority and configuration | Reuse `ControlPlaneSecurityConfig`, `control_plane_api/_auth.py`, `ControlPlaneConfiguration` and `OperationSupervisionConfiguration`. Mutation requires target-bound administrative authority; carried admission context authenticates nobody. Authorize actor/scope readback through `RuntimeControlPlane._operation_read_allowed` before disclosure, with indistinguishable unknown/unauthorized claims. Preserve typed scope/profile/budget checks and bounded HTTP offload. P0 remains a trusted embedder boundary. |
| Intent and targets | Reuse the authoring validators, compiler/address helpers and `control_plane_plan_authorization.py`. Resolve the exact authorized plan, binding/node/instance revisions, source, realization and placement. Intrinsic/event/schedule assertions and shared-time validity remain independent admission checks; unknown truth refuses. |
| Artifacts and secrets | Artifact references supply identity/integrity, not authenticity or fetch permission. Use admitted artifact owners and ADR-071/077 provenance, a closed realization input contract and `SecretReferenceId` for operator-secret references. Omitted input permits no parameters. Keep credentials and guessable secret digests out of identifiers and carriers. |
| Provider | Reuse `manifest_authority.py`, `require_inject_occurrence_provider`, `require_backend_operation_admission` and `validate_backend_operation_response`. Allowlisting, declaration, installed call shapes and current willingness remain separate checks. Unsupported guarantees refuse explicitly. |
| Claims and recovery | Existing admission, supervised execution, invocation ledger and `ControlPlaneStore` owners retain atomic claims, running intent, generation fences, effect reservations and terminal state/audit. `validate_inject_occurrence_claims` supplies neither concurrent persistence nor complete head-chain verification. Adoption must extend versioned codecs and occurrence/slot/order uniqueness across restart; truncated lists or process-local sets cannot provide it. Uncertainty retains claims and exclusion without redispatch. |
| Results and participants | Reuse the outcome/correlation validators, `OperationEvidenceResolver`, result finalization and backend diagnostics to verify evidence content, native integrity, predecessor isolation and every binding. Resource narrowing needs admitted independence. Existing participant delivery/control/crossing owners additionally enforce audience, policy, control-occurrence, episode/time/flow and delivery reservations. Correlation grants none of that authority; legacy anchors and ADR-066 evidence ownership remain intact. |
| Errors and release | Reuse existing validation errors, diagnostics, redacted HTTP handlers and action-specific audit fields. Preserve bounded denial audit, fixed log labels and `Cache-Control: no-store`. Arbitrary payloads are not valid audit details; raw exceptions, validation inputs, credentials and provider locators must not escape. |

Two existing execution boundaries require deliberate integration:

- `require_backend_execution_policy_admission` accepts native plan commands.
  `operation_provider_execution.py` checks native commitments and
  `operation_result_finalization.py` checks native snapshot results. An
  occurrence reference cannot replace a plan reference unchanged. Extend the
  owning resolution boundary while preserving its policy and result checks.
- `control_plane_operation_context.py` and `control_plane_store_payloads.py`
  redact account credentials, not arbitrary inject inputs. RFC 8785 commits
  the actual carrier, including references. Sensitive adoption must cover
  commitments, ephemeral exact-retry proof, snapshots, audit and restore;
  loss of retry proof never permits redispatch.

`Inject.environment` remains a string list, with no assignment or shell grammar.
Runtime environment bindings use `RuntimeEnvironmentVariable` and
`runtime_generated_value.py`, retaining name validation, literal/`value_from`
exclusivity and `redacted`/`operator_secret` omission. ADR-057 separates scenario
fixture values from operator secrets. Backend owners retain native execution
and secret resolution; portable IDs never become paths or callbacks. Keep
operator credentials out of argv, URLs, shell strings, dumps and artifacts.
P2 adoption preserves the existing [host/service boundary](../../public/guides/control-plane.md),
including TLS/proxy and connection limits, counted request bytes, bounded
offload, worker/profile checks, private storage and service credentials.

Extensions belong in versioned realization/input/target contracts and admitted
backend guarantees. V1 selects compiled `Node.injects` bindings; non-node targets
need an explicit versioned interpretation. Preserve omission/null/default and
ordering commitments, historical readers and ADR-061/075 publication rules.
Accepted ADRs retain ADR-059 amendment/pin protection. Keep the schema bundle,
per-contract publication entries, facade exports, versions, backend allowlists
and installed `raes_contracts.corpus` aligned through existing generation and
packaging tools. Allowlist changes also affect SDL behavior evidence references
without advertising backend support.

JSON Schema does not execute `x-raes-invariants`, and the current
`raes_conformance/conformance/validators.py` registry does not register these
contracts. Direct helper tests and publication are not conformance-CLI adoption.
Existing fixture tests establish structural/contextual joins and participant-free
parser/compiler agreement. Executable consumers additionally need evidence at
authentication, ingress, store, provider and final-sink boundaries, including
competing claims, failed commits and crash/late outcomes. The #1367 implementation
adds the selected execution path, endpoints and internal store migration described
in the operator guide, with no new operation kind, SDL grammar or participant
registration/delivery. Acceptance, willingness,
installation, effects, delivery and observation remain separate facts.

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

The `participant-free-environment.json` request and occurrence fixtures trigger
`release` against `orchestration.inject-binding.host.release` on node
`provision.node.host`, anchored to `gate`. The caller is an authenticated
operator, not a participant or controller.
`test_issue_1423_inject_occurrence_contracts.py` compiles this environment and
checks that the occurrence fixture names only its compiled identities. It
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
