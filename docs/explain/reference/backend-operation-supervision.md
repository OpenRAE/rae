# Implement the backend operation protocol

The optional `operation-supervision` profile defines messages for one admitted backend call.
A backend reports acceptance, progress and refusal.
It also reports effects and cancellation evidence.
RAE retains scenario execution and terminal publication.

Install the profile through `RuntimeTarget.operation_provider`.
The runtime P0–P3 profile matrix remains unchanged.

The [normative contract](../../../specs/formal/runtime-contracts/backend-operation-supervision.md)
defines field meaning, guarantees, identity, budgets and validation.
Import models and validation helpers from `raes_contracts.contracts`.
Import `BackendOperationProvider` and `require_operation_provider` from `raes_backend_protocols.operation_supervision`.
This interface does not depend on `raes_runtime`.
Schemas, profile and examples ship in the existing packaged contract corpus.
Use `raes_contracts.corpus` to locate them in an installed wheel.

## Provider responsibilities

Native phase commands can carry authored execution requirements.
Resolve the exact native artifact.
Use `require_backend_execution_policy_admission` to check its policy commitment, support and willingness bound to the request.
See [execution requirement migration](execution-recovery-migration.md).
Support for a capability grants no authority to repeat effects.
This optional protocol adds no general continuation or trial allocator.

The default policy helper checks the canonical native-plan digest.
A protected artifact owner can supply `resolved_native_plan_commitment` instead.
It computes that proof afresh from its exact authorized native plan.
Never copy that proof from the request.

RAE's installed adapter uses an HMAC-SHA256 commitment private to the process.
Stored invocation metadata thus exposes no unkeyed plan digest that depends on credentials.
Request/control commitments and native snapshot digests keep their existing canonical rules.

1. Declare all four `backend-operation-*-v1` contracts in the existing backend manifest.
   Implement the six protocol methods.
   Return the current capability declaration.
   Use `require_operation_provider` to check the declaration and call shapes without making an effect call.
2. Implement `check_operation` against the exact resolved native requirements,
   command and execution context.
   Return explicit refusal if any required guarantee is unsupported or currently unavailable.
   Match the request and capability digests.
   Do not claim that a supported protocol proves readiness.
3. Accept `start_operation` only through the trusted RAE invocation path after
   it confirms the one-use claim and current authority.
   Deduplicate the exact binding/commitment.
   Retain reservations against conflicting effects.
   Return the same work for duplicate delivery.
   A changed commitment under an existing invocation is a conflict.
   It must never start new work.
4. Return bounded evidence records.
   Keep a sequence within the invocation.
   Retries retain its content.
   Resolve and validate artifacts through their owning contracts.
   Partial results include the native residual snapshot and changed-address scope.
   Native output, secrets, exception text and process arguments must not enter these carriers.
5. Serve observation, cancellation and reconciliation independently of effect
   worker saturation.
   Respect the remaining apparatus budget.
   An accepted cancellation is only a commitment to attempt it.
   Report cessation only with evidence that accounts for outstanding workers, effects and residual state.
6. Preserve unknown outcomes and retained exclusion.
   RAE validates native results and commits terminal operation/snapshot/audit state.
   A backend must not schedule workflow retries or allocate new trials.
   It must not rewrite an immutable terminal parent or treat reconciliation as execution replay.

Each method returns one `BackendOperationResponseModel`.
Its `message.kind` identifies the payload.
`check_operation` returns `admission`.
`start_operation` returns `acknowledgement`.
`cancel_operation` returns `control`.

`observe_operation` returns a retained progress/outcome record, a correlated
reconciliation observation, or a control refusal. `reconcile_operation` returns
`reconciliation` or a control refusal.
All exceptions and lost replies leave the caller uncertain.
Callers never infer no effects from a failed call.

The shape checker does not authenticate callers, grant claims, exercise the
backend or certify liveness.
Independent integrations must meet those normative duties before they claim support.
With a provider installed, `RuntimeControlPlane` uses this path for native provisioning, orchestration and evaluation plans.
Configure a trusted `OperationEvidenceResolver`.
Use it to validate scoped effect/cessation witnesses and resolve committed native results.
A backend assertion with the right shape alone cannot establish success.

The local adapter bounds extension calls with AnyIO.
It reserves independent effect, control and store capacity.
A timeout abandons the wait.
The physical slot stays held until the callback exits.
Native synchronous backends also use this bounded phase path.
An unsuccessful native call that was dispatched becomes indeterminate.

`ApplyResult.success=False` supplies no cessation proof.
See [supervised execution](../../public/guides/supervised-execution.md) for
configuration, shutdown and the optional distributed composition.

## Migration and compatibility

| Existing surface | Migration rule |
| --- | --- |
| `operation-receipt-v1`, `operation-status-v1` | Preserve their shared `runtime-operation/v1` discriminator, six states and existing readers. New backend records are separate evidence for the runtime authority. Do not inject unknown fields into old closed readers. |
| `ApplyResult` | Preserve native result admission. A false success flag or predecessor snapshot cannot become proof of no effects, known failure or cessation. Without new evidence validated independently, the new outcome is indeterminate. |
| `RecoveryObservationResult` | Its absent/applied/indeterminate vocabulary has no general cessation or partial-effect witness. Conversion cannot invent one. Keep legacy reports on the old observer. Or obtain fresh evidence before you construct a new report. |
| P1/P2 stored operation records | SQLite schema 7 added a strict versioned invocation ledger and linked reconciliation evidence. Historical records retain `invocation=None`. Migration invents no grant, generation or cessation witness. Preserve the schema-7 database and its retained reservations. |
| Backend manifests/profiles | New draft schemas expand the backend contract-ID allowlist. Old manifests and profiles remain valid under the new reader. Old closed readers can reject new IDs. Negotiate support before you send new messages. Never strip IDs or fields to hide a lack of compatibility. |
| P0–P3 runtime profiles | These keep their guarantees. This backend profile is a separate axis. The presence of schemas cannot activate distributed operation, interruption, recovery, or P3. |

Migration must preserve complete bindings and request/requirement commitments.
It must also preserve control actors, sequence and remaining budget origins.
If old records lack any required fact, there is **no lossless automatic conversion**.
Refuse the stronger protocol or retain unknown evidence through the existing recovery path.
Do not fabricate generations, claim IDs, cessation, clean state, continuation points or retry authority.
Changing operation IDs, restoring a database or restarting a timer is not a migration strategy.

The four new contracts are draft v1 publications under ADR-009/061.
Incompatible future changes follow the existing evolution policy.
The reference bundle must match each normative schema.
Publication records give contract identity, schema path, and stability.
They contain no hash or change summary. Git records schema history.
Required runtime content pins still bind exact schema artifacts.
Obtain those artifacts from a pinned release or Git revision.
Use the owning protocol's digest rule for those artifacts.

Receipt/status projections keep their existing shape.
Private worker RPCs and stored invocation carriers are separate integration surfaces.
Their installation does not upgrade a backend declaration.

## Examples and evidence limits

The packaged `fixtures/control-plane/` corpus groups exchanges by filename:

| Prefix | What the exchange demonstrates |
| --- | --- |
| `accepted` | Admission is willing and the invocation is accepted. It reports progress, then proposes success for RAE to validate. |
| `refused` | A capable backend declines the exact context. No invocation follows. |
| `cancel-race` | Cancellation is accepted, then completion proposes success. RAE decides the atomic settlement order. |
| `partial-cancel` | Cancellation is established with known residual effects. It asserts no rollback. |
| `duplicate` | Identical sequence and acknowledgement may be read twice without a second invocation. |
| `uncertain` | Unknown effects remain indeterminate. Later reconciliation evidence cannot rewrite that parent. |

`test_issue_1360_backend_operations.py` validates these messages and their
relationships.
Fixture evidence references are synthetic.
A real implementation must resolve and validate actual evidence.
It must also pass runtime/backend conformance before these examples can support stronger claims.

RUN-310 [reusable participant control](reusable-participant-control.md) joins an accepted cancellation occurrence to this invocation/control ledger.
Its readback keeps control acceptance, backend disposition and validated work outcome separate.
It retains unknown effects and the original one-use delivery budget.
