# Backend operation and supervision contracts

Status: published draft contracts, issue #1360, API-402. Classification: FM3.
The [supervision semantics](../runtime-control-plane/supervision.md) and
[ADR-113](../../../docs/decisions/adrs/adr-113-reusable-execution-machinery.md)
own the execution design. This publication supplies portable messages and
validation obligations. It does not implement the runtime dispatch, claim,
supervision, store, or physical fencing mechanisms described by that design.

## 1. Authority and contract family

RAE admits authored work and drives one backend invocation through the public
`raes_backend_protocols.operation_supervision.BackendOperationProvider` protocol.
The backend performs concrete work and supplies evidence. RAE retains scenario
ordering, authorization, workflow/time/trial policy, retries, trusted snapshots,
result admission, terminal publication and operational audit. A backend needs
no second scenario interpreter. Schema validity proves none of these duties.

The additive `operation-supervision` backend profile requires the existing
backend manifest plus four schemas under `contracts/schemas/control-plane/`:

| Contract | Direction and purpose |
| --- | --- |
| `backend-operation-request-v1` | RAE to backend: exact admitted command, requirements, context and apparatus budget. |
| `backend-operation-capabilities-v1` | Backend to RAE: installed versioned declaration for operation kinds and guarantees. |
| `backend-operation-control-v1` | Authorized supervisor to backend via RAE: cancel, observe or reconcile the original invocation. |
| `backend-operation-response-v1` | Backend to RAE: discriminated admission, acknowledgement, progress, control disposition, outcome or reconciliation evidence. |

Wire `schema_version` values use `/v1`; publication IDs use `-v1`. All objects
are closed. Unknown versions, fields, enum values or required guarantees fail
closed. Profile membership is contract support, not backend conformance or a
P0–P3 runtime guarantee. Existing backends do not opt in automatically.

## 2. Binding, command and authorization

Every request and response preserves the original `OperationAdmissionContext`:
actor, authorization scope, target/run, operation kind, request commitment and
parent operation. A binding additionally identifies backend, deployment,
operation, invocation, authored attempt, authorized worker, owner generation,
execution generation, baseline snapshot revision and conflicting-effect scope.
These identifiers have distinct meanings and must not be substituted for one
another. An engine delivery attempt is not an authored attempt or invocation.
An ordinary operation needs no experiment, participant or trial wrapper.

`command` is a digest-bound reference to the admitted native command/plan.
`requirement_refs` identify exact admitted requirement artifacts, including any
selected workflow, time, trial, effect or release constraints. The command's
owning contract retains its resolved policy and provenance. These references
are not a free-form policy language: the runtime must resolve and validate
their native types, expected kind and immutable contents before dispatch.
Unresolved, unsupported or incompatible references prevent invocation. No
raw credentials, executable paths, native job locators or arbitrary metadata
are carried here. References and digests grant neither access nor permission.

The request digest is SHA-256 over RFC 8785 canonical JSON of the complete
validated request, including materialized defaults and null values. Preserve
array order. `backend_operation_request_digest()` is the reference encoder;
the original admission commitment remains a distinct value. Every response
echoes both the binding and this digest. Capability and control digests follow
the same rule. A changed requirement, budget, scope or command is a different
request, not a transport retry of an existing invocation.

Before `start_operation`, the current authenticated RAE authority must validate
the command, current scope authorization, budget, capability and willingness,
then consume the one-use invocation claim specified by ADR-113. The first
confirmed consumer may invoke. A lost claim acknowledgement grants no usable
permission. No database transaction spans the backend call. Duplicate delivery
observes the same invocation and cannot cause another effect or authored
attempt. Credential-sensitive retries retain their incumbent ephemeral proof
requirements; a durable public digest cannot replace that proof after restart.

Owner generation, execution generation and baseline revision fence **state
publication**. They cannot prove cessation or fence a remote effect. A backend
external fence requires separate scoped evidence under its admitted guarantee.
Replacing an owner or worker retains outstanding reservations and quarantine.

Effect exclusion defaults to the entire target/run. A `resources` scope requires
bounded canonical addresses and a digest-bound independence artifact that the
runtime validates. Residual addresses must stay within this admitted scope.
Unrepresented or out-of-scope effects invalidate the report and require
indeterminacy, not silent truncation. An external fence reference is evidence
to validate against this exact scope, not a self-authenticating token.

## 3. Capability, willingness and bounded calls

`operation_capabilities()` returns an installed provider declaration with a
backend identity, revision, operation kinds and selectable guarantees:

| Guarantee | Required meaning when selected |
| --- | --- |
| `cancellation` | Accept the scoped cancellation protocol and explicitly report its disposition. It does not promise successful cessation. |
| `effect-observation` | Provide bounded, correlated effect observations during execution/reconciliation, including honest uncertainty. |
| `cessation-evidence` | Establish scoped cessation evidence required by the admitted operation, or refuse that operation before effects. |
| `partial-effects` | Represent known partial effects with a native residual snapshot and complete residual scope. |
| `external-fencing` | Establish the admitted backend fence for the exact external effect scope; local CAS is insufficient. |

The exact required strength, durations, scope and native evidence are in the
admitted command/requirement artifacts. A guarantee name alone never proves
their satisfaction. General continuation/checkpoint support is absent from v1;
a request requiring an unsupported continuation guarantee must be refused.

`require_operation_provider()` checks declared contract IDs and installed call
shapes without invoking the provider. `check_operation(request)` returns an
`admission` response bound to the complete request and the canonical capability
digest. `require_backend_operation_admission()` requires matching backend/kind,
all requested guarantees, the exact capability digest and current willingness.
This pure validator does not authorize effects. The runtime must recheck after
queueing and immediately before consuming the invocation claim. A previous
willing answer is not an irrevocable promise. No missing guarantee becomes
best effort, a shorter duration, a replacement backend or an implicit retry.

Each request/control carries a positive finite integral apparatus budget in
milliseconds, its immutable origin ID, a valid RFC 3339 origin instant and the
remaining allowance. Integers are strict and bounded to the interoperable JSON
integer range. The remaining allowance cannot exceed the original limit.
It is a ceiling, not a restartable timer: the runtime tracks elapsed apparatus
monotonic time and every nested call consumes the enclosing remaining budget.
Duplicates never renew it. Restart requires clock-continuity/elapsed evidence;
otherwise the remaining time is unknown and invocation is refused. UTC origin
evidence does not make a portable monotonic deadline. Authored semantic clock,
domain and segment semantics remain in their native contracts.

RAE must independently bound admission, execution, observation/interruption,
store readback/commit and drain. This backend carrier transmits the remaining
budget for the particular backend stage; it does not implement those timers.
Effect and control calls require independent bounded capacity. If that cannot
be provided, the composition cannot advertise the stronger supervision claim.
No unbounded callback iterator is part of this protocol: each method returns
one bounded response. Transport loss, method exceptions, malformed results and
timeout are uncertainty; native exception text must not become public records.

## 4. Response meanings and ordering

| Message | Meaning |
| --- | --- |
| `admission` | Current willingness or contextual refusal, referencing the exact capability declaration. |
| `acknowledgement` | This invocation was accepted, or refused before it could produce effects. Acceptance is not success. |
| `progress` | Bounded operational phase/evidence; it neither extends a budget nor proves a result. |
| `control` | A supervisory request was recorded, accepted, refused, unsupported, or arrived after terminal evidence. None of these establishes cessation. |
| `outcome` | Proposed existing terminal state with independent effect knowledge, cessation, satisfaction, release and cancellation claims. RAE must validate before publishing. |
| `reconciliation` | Bounded observation for a correlated observe/reconcile request; it does not invoke, replay or rewrite a terminal parent. |

Backend sequence numbers are positive and ordered within one exact invocation
binding. They order reports, not the runtime's atomic commits. The identical
sequence/content may be retransmitted; different content at the same sequence
or a previously unseen lower sequence is invalid. Gaps are permitted, since
progress may be coalesced before publication; acknowledged controls must remain
retrievable and cannot be silently discarded. Retain deduplication for as long
as the admitted effect/recovery window requires. Sequence exhaustion must close
admission; wrapping a counter cannot create a new invocation.

`validate_backend_operation_history()` checks bounded transcripts of at most
1024 response records and 256 controls. Progress/outcome requires an accepted
acknowledgement. Refused acknowledgement closes that invocation. A proposed
terminal report is immutable within the transcript; later control/reconciliation
records may add evidence, but cannot replace it. Transcript validation is a
conformance check, not a scheduler, persistence implementation or proof that
a backend deduplicates its physical effects.

Each control request binds its own actor, authorization scope, unique control
ID and canonical digest to the original operation. Runtime authorization must
independently authenticate that supervisor and check the precise subject/scope;
fields asserted by a caller are not identity proof. Responses to control and
reconciliation echo its ID and digest. Same control ID with changed content is
invalid. A repeated cancellation cannot multiply interrupts or restart budgets.
Status retrieval may return previously recorded progress/outcomes unchanged;
the runtime still authorizes each disclosure.

## 5. Effects, settlement and uncertainty

Effect knowledge is `absent`, `complete`, `partial` or `unknown`, independently
of `cessation_established`. Known effect/cessation/fence claims require scoped
content-bound evidence references. Known partial effects require both a native
`runtime-snapshot-v1` residual state reference and its complete changed-address
scope. Unknown remainder may preserve a known residual prefix, but must stay
`unknown`. Absence cannot include residual changes. Complete effects may be a
validated no-op. Evidence references must be resolved, authenticated, bounded,
scope-checked and validated; presence of a reference does not establish truth.

| Proposed state | Required claims, in addition to native runtime validation |
| --- | --- |
| `succeeded` | Known nonpartial effects, cessation, all admitted requirements satisfied, result reference and final release gates satisfied. |
| `failed` | Known effects, cessation and established non-satisfaction. Known partial effects remain represented. |
| `cancelled` | Known effects, cessation and established cancellation contract. Known partial residuals remain represented; rollback is not implied. |
| `indeterminate` | Required for unknown effects or unproved cessation, and available for other unsettled contract/commit facts. Preserve trusted state and exclusion. |

The proposed state uses the existing `OperationState` vocabulary. There is no
new PARTIAL, REFUSED, CANCELLING or TIMED_OUT state. The backend proposal cannot
override native result validation, trusted-predecessor isolation, requirement
satisfaction or final release validation. RAE alone commits the permitted
snapshot, terminal record and actor-bound audit atomically with revision CAS.
An effect can be known complete while a release gate still prevents success.
Generic failure or a predecessor snapshot cannot prove no external effect.

If cancellation is accepted and valid completion wins the runtime commit,
success remains possible. Cancellation requires evidence, not the accepted
request. A late completion after cancellation/indeterminacy may supply linked
resolution evidence, but cannot rewrite the parent. Pre-dispatch contextual
refusal after runtime claim becomes the existing cancellation/refusal path;
before claim it remains denial audit. A refusal after possible effects is not
an absent-effect acknowledgement: report classified/unknown effects instead.

Backend effect uncertainty and store commit uncertainty remain separate. For a
lost store acknowledgement, read back the complete atomic cut, poison readiness
while unknown, and do not publish a second terminal record. A backend outcome
cannot resolve store uncertainty. Reconciliation observes without replay;
administrative acceptance, compensation, cleanup and new trial allocation keep
their separate owning contracts. Unknown cessation retains quarantine even
after a terminal indeterminate record or owner loss.

## 6. Validation and examples

Consumers must run structural JSON Schema validation **and** the semantic
invariants declared with `x-raes-semantic-profile`/`x-raes-invariants`.
Annotations document the mandatory rules; a generic JSON Schema validator does
not execute Python validators or validate backend truth. The Python facade
exports the four models, nested message models, digest helpers, admission,
response and transcript validators. Cross-message checks require the trusted
request and, for a control result, its independently admitted control request.

The routed fixtures under `contracts/fixtures/control-plane/backend-operation-*`
are executable contract examples. Matching filename prefixes form exchanges:
`accepted`, `refused`, `cancel-race`, `partial-cancel`, `duplicate`, `uncertain`.
They demonstrate every message kind and preserve uncertain parents when new
reconciliation evidence arrives. The `provider` capability fixture is a
synthetic declaration, not a claim about an installed backend. Artifact digests
are synthetic identity witnesses; these examples prove carrier and relationship
validation, not actual artifact contents, physical effects or liveness.

`test_issue_1360_backend_operations.py` executes the corpus, rejects foreign
bindings and changed commitments, exercises cancellation races/duplicates and
checks honest outcome boundaries. The existing #1348 abstract model and lifecycle
tests retain their narrower claims. No fixture establishes runtime interruption,
distributed coordination, recovery truth, physical containment or P3 support.
