# Execute an externally triggered inject

An operator with the right role can trigger one authored inject against chosen
live nodes. Use `RuntimeControlPlane.submit_inject(request, identity=...)` or
P2 `POST /injects/trigger`. The runtime uses its existing operation ledger,
supervision and store. A queued snapshot or accepted receipt proves no world
effect on its own.

## Configure an executing provider

RAES ships no executing inject provider. The default stub target refuses
occurrence commands. A backend distribution supplies the provider. RAES 7.0.0
was the last release to bundle the reference OCI provider. Read the
[concrete backends migration](https://github.com/OpenRAE/rae/blob/main/docs/migration/concrete-backends.md).

Configure the provider through the existing control-plane seams:

1. Provision the selected nodes with the backend's own target. Keep their live
   snapshot and target/run scope.
2. Pass the backend's `InjectExecutionResolver` as `inject_execution` to the
   control plane. Pass its `OperationEvidenceResolver` as
   `operation_evidence`. Use the same retained snapshot and store.
3. Register the original execution plan through
   `register_planner_produced_plan`.

The provider acts as the target's operation provider. It must refuse other
commands. The host checks who supplied the source, issues permits and keeps
scopes apart. Keep the store, provider setup and record reader private.

A provider must read each binding's target state before and after the source
runs. An applied effect needs the expected after state and proof that the
source stopped. A provider that cannot prove both facts must report an unknown
effect. It must not report success.

## Trigger and read back

Send a strict `inject-trigger-request-v1` body using the exact plan, inject,
bindings, target/run, placement, fresh occurrence and retry key. The trusted
permit binds that exact request and its predecessor/order position. The first
head is `inject-order:genesis`. Get later heads through
`raes_runtime.inject_claims.inject_order_head`. Arrival order does not issue a
permit or repair a stale head. An exact retry returns the original receipt.
It grants no dispatch or new budget. A fresh repeat needs a fresh occurrence
and key. It also needs a new permit and a valid world precondition.

P2 authenticates before body decoding, counts at most 256 KiB, limits JSON depth
to 16 and rejects duplicate members, nonfinite values and unknown fields. An
optional `Idempotency-Key` header must equal the body's `request_key`. Mutation
requires target-bound operator/backend authority. All responses use
`Cache-Control: no-store`. Unknown and unauthorized operation reads both return
404. P0/P1 SDK hosts supply the trusted caller identity.

| Read | Meaning |
| --- | --- |
| `GET /operations/{id}` | Existing operation state and diagnostics. |
| `GET /operations/{id}/inject-occurrence` | The committed request, actor admission, source/plan/realization and ordering pins. |
| `GET /operations/{id}/inject-outcome` | Validated per-binding world-effect facts, independently of participant results. |
| `GET /operations/{id}/inject-result` | The retained checksummed associated-artifact manifest. |
| `GET /operations/{id}/inject-artifacts/{artifact_id}` | Retained approved evidence bytes as a binary attachment; the ID is never a filesystem path. |
| `GET /operations/{id}/inject-correlation` | The exact successful occurrence/outcome/result join, only after verified application and successful settlement. |

The corresponding SDK methods are `get_inject_occurrence`, `get_inject_outcome`,
`get_inject_result`, `get_inject_artifact` and `get_inject_correlation` with
optional trusted `identity`. They apply the existing actor/scope read policy.
The store commits evidence manifests and bytes with the outcome. Later target
changes and restart do not change that record. Keep evidence non-secret.
This realization does not accept secret inputs or store secret outputs.

## Failure, recovery and supported scope

Admission refusal creates no accepted occurrence or dispatch. A refusal after
the atomic claim cancels the operation and keeps that claim. An entrypoint that
exits with an error may still change the world. Such an operation fails and
yields no success correlation. Unknown bindings, unproven cessation, readback
failure and crashes cannot become success. Unknown effects keep their invocation
reservation. They never restore consumed dispatch authority.

P0 holds process-lifetime state. P1 and served P2 retain claims, ordering,
evidence and startup state in the existing store. Local records migrate to
schema 9. PostgreSQL records use schema 2 with one owner. Older records gain no
invented occurrence or readback. Reopening never reruns an effect on its own.
Reconciliation can append checked, linked facts. It cannot rewrite an immutable
indeterminate outcome or grant another dispatch. An accepted control request or
local timeout does not prove that native effects stopped.

Each provider declares the bindings, placements and parameters it supports.
The portable contracts cover more cases than one provider can realize. The
store checks unique occurrences, schedule slots and the full order chain for
every admitted provider. History holds at
most 1024 claims. It is never truncated to admit more work. P3, multiple owners
and exactly-once backend effects are unavailable.

World execution needs no participant declaration. Correlation grants no
participant disclosure, delivery, observation or controller authority. Existing
consumers must authorize their exact join and final sink on their own.
Legacy plan-start receipts, authoring and participant anchors retain their
original meaning. See the [contract reference](https://github.com/OpenRAE/rae/blob/dev/docs/explain/reference/inject-occurrence-contracts.md)
and [control-plane guide](control-plane.md) for the transport/host boundary.

## Evidence

The RAES unit tests use substituted providers. They check runtime and binding
behavior, not concrete native support.
Concrete provider evidence belongs to the backend distribution's own release
gate. Full integration runs remain in CI/CD.
