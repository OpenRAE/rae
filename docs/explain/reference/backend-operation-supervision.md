# Implement the backend operation protocol

The optional `operation-supervision` profile publishes messages for one
admitted backend invocation. It lets a backend report acceptance, progress,
refusal, effects and cancellation evidence while RAE retains scenario execution
and terminal publication. Install it through `RuntimeTarget.operation_provider`.
The runtime P0–P3 profile matrix remains unchanged.

The [normative contract](../../../specs/formal/runtime-contracts/backend-operation-supervision.md)
defines field meaning, guarantees, identity, budgets and validation. Import
models and validation helpers from `raes_contracts.contracts`, and
`BackendOperationProvider`/`require_operation_provider` from
`raes_backend_protocols.operation_supervision`. This interface has no dependency
on `raes_runtime`. Schemas, profile and examples ship in the existing packaged
contract corpus; use `raes_contracts.corpus` to locate them in an installed wheel.

## Provider responsibilities

Native phase commands can carry authored execution requirements. Resolve the
exact native artifact and use `require_backend_execution_policy_admission`
to check its policy commitment/support and request-bound willingness. See
[execution requirement migration](execution-recovery-migration.md). Capability
support is not authorization to repeat effects; no general continuation or
trial allocator is introduced by this optional protocol.

The default policy helper checks the canonical native-plan digest. A protected
artifact owner can instead supply `resolved_native_plan_commitment`, freshly
computed from its exact authorized native plan. Never copy that proof from the
request. RAE's installed adapter uses a process-private HMAC-SHA256 commitment
so durable invocation metadata does not expose a credential-dependent unkeyed
plan digest. Request/control commitments and native snapshot digests retain
their existing canonical rules.

1. Declare all four `backend-operation-*-v1` contracts in the existing backend
   manifest. Implement the six protocol methods and return the current
   capability declaration. Use `require_operation_provider` to check the
   declaration and call shapes without making an effect call.
2. Implement `check_operation` against the exact resolved native requirements,
   command and execution context. Return explicit refusal if any required
   guarantee is unsupported or currently unavailable. Match the request and
   capability digests; do not claim that a supported protocol proves readiness.
3. Accept `start_operation` only through the trusted RAE invocation path after
   it confirms the one-use claim and current authority. Deduplicate the exact
   binding/commitment, retain conflicting-effect reservations and return the
   same work for duplicate delivery. A changed commitment under an existing
   invocation is a conflict, never another start.
4. Return bounded evidence records. Keep a sequence within the invocation;
   retries retain its content. Resolve and validate artifacts through their
   owning contracts. Partial results include the native residual snapshot and
   changed-address scope. Native output, secrets, exception text and process
   arguments must not enter these carriers.
5. Serve observation, cancellation and reconciliation independently of effect
   worker saturation. Respect the remaining apparatus budget; an accepted
   cancellation is only an undertaking. Report cessation only with evidence
   that accounts for outstanding workers, effects and residual state.
6. Preserve unknown outcomes and retained exclusion. RAE validates native
   results and commits terminal operation/snapshot/audit state. A backend must
   not schedule workflow retries, allocate new trials, rewrite an immutable
   terminal parent, or treat reconciliation as execution replay.

Each method returns one `BackendOperationResponseModel`, whose `message.kind`
identifies the payload. `check_operation` returns `admission`; `start_operation`
returns `acknowledgement`; `cancel_operation` returns `control`.
`observe_operation` returns a retained progress/outcome record, a correlated
reconciliation observation, or a control refusal. `reconcile_operation` returns
`reconciliation` or a control refusal. All exceptions/lost replies leave the
caller uncertain; callers never infer no effects from a failed call.

The shape checker does not authenticate callers, grant claims, exercise the
backend or certify liveness. Independent integrations must implement those
normative duties before claiming support. `RuntimeControlPlane` uses this path
for native provisioning, orchestration and evaluation plans when a provider is
installed. Configure a trusted `OperationEvidenceResolver` to validate scoped
effect/cessation witnesses and resolve committed native results. Returning a
well-shaped backend assertion alone cannot establish success.

The local adapter bounds extension calls with AnyIO and reserves independent
effect, control and store capacity. A timeout abandons the wait while retaining
the physical slot until the callback exits. Native synchronous backends also
use this bounded phase path; an unsuccessful dispatched native call becomes
indeterminate because `ApplyResult.success=False` supplies no cessation proof.
See [supervised execution](../../public/guides/supervised-execution.md) for
configuration, shutdown and the optional distributed composition.

## Migration and compatibility

| Existing surface | Migration rule |
| --- | --- |
| `operation-receipt-v1`, `operation-status-v1` | Preserve their shared `runtime-operation/v1` discriminator, six states and existing readers. New backend records are separate evidence for the runtime authority. Do not inject unknown fields into old closed readers. |
| `ApplyResult` | Preserve native result admission. A false success flag or predecessor snapshot cannot be converted to effect absence, known failure or cessation. Without independently validated new evidence, the new outcome is indeterminate. |
| `RecoveryObservationResult` | Its absent/applied/indeterminate vocabulary has no general cessation or partial-effect witness. Conversion cannot invent one. Keep legacy reports on the old observer, or obtain fresh evidence before constructing a new report. |
| P1/P2 stored operation records | SQLite schema 7 adds a strict versioned invocation ledger and linked reconciliation evidence. Historical records retain `invocation=None`; migration invents no grant, generation or cessation witness. Preserve the schema-7 database and its retained reservations. |
| Backend manifests/profiles | New draft schemas expand the backend contract-ID allowlist. Old manifests and profiles remain valid under the new reader; old closed readers can reject new IDs. Negotiate support before sending new messages. Never strip IDs or fields to disguise incompatibility. |
| P0–P3 runtime profiles | Unchanged guarantees. This backend profile is a separate axis; schema availability cannot activate distributed operation, interruption, recovery, or P3. |

Migration must preserve complete bindings, request/requirement commitments,
control actors, sequence and remaining budget origins. If historical records
lack any required fact, there is **no lossless automatic conversion**. Refuse
the stronger protocol or retain unknown evidence through the existing recovery
path. Do not fabricate generations, claim IDs, cessation, clean state,
continuation points or retry authority. Changing operation IDs, restoring a
database or restarting a timer is not a migration strategy.

The four new contracts are draft v1 publications under ADR-009/061. Incompatible
future changes follow the existing evolution policy; the reference bundle must
match each normative schema and each publication entry records its content hash
and contract-facing change. Receipt/status projections keep their existing
shape. Private worker RPCs and persisted invocation carriers are separate
integration surfaces; installing them does not upgrade a backend declaration.

## Examples and evidence limits

The packaged `fixtures/control-plane/` corpus groups exchanges by filename:

| Prefix | What the exchange demonstrates |
| --- | --- |
| `accepted` | Willing admission, accepted invocation, progress and a success proposal awaiting RAE validation. |
| `refused` | A capable backend declines the exact context. No invocation follows. |
| `cancel-race` | Cancellation is accepted, then completion proposes success. RAE decides the atomic settlement order. |
| `partial-cancel` | Cancellation is established with known residual effects; no rollback is asserted. |
| `duplicate` | Identical sequence and acknowledgement may be read twice without a second invocation. |
| `uncertain` | Unknown effects remain indeterminate; later reconciliation evidence cannot rewrite that parent. |

`test_issue_1360_backend_operations.py` validates these messages and their
relationships. Fixture evidence references are synthetic. A real implementation
must resolve and validate actual evidence and pass runtime/backend conformance
before these examples can support stronger claims.

RUN-310 [reusable participant control](reusable-participant-control.md) joins an
accepted cancellation occurrence to this invocation/control ledger. Its readback
keeps control acceptance, backend disposition and validated work outcome
separate, retaining unknown effects and the original one-use delivery budget.
