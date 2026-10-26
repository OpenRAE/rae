# Runtime descendant reports

Use `backend-runtime-descendants-v1` to report resources absent from the original plan.
The same contract reports children discovered after initial apply.
The backend supplies materialized SDL and causal receipts.
The runtime checks the report and records the origin of each concern.

## Requirements

Advertise both `backend-runtime-descendants-v1` and `backend-materialization-attestation-v1` in the backend manifest.
Install `refresh_inventory(request, predecessor)` on the provisioner.
That method returns `ApplyResult` and must perform only read-only inventory work.
`raes_backend_protocols.inventory.RuntimeInventoryReporter` defines its optional producer interface.
Configure the existing `materialization_archive` on the manager or control plane.
Plan the original SDL with a stable `PlanScope(run_id=...)`.

The original enclosing node collection must permit additional members.
Opening one node's runtime concerns does not open the collection.
Keep imported namespace restrictions and exact declarations intact.
The first apply still needs permission for added effects. It must also report those effects before it creates them.
Refresh does not authorize a collector installation or another guest probe.

## Producer procedure

1. Read the runtime-bound request and isolated predecessor.
2. Describe the complete current world in ordinary materialized SDL.
3. Keep original source, producer, plan, operation and predecessor bindings.
4. Add the typed inventory report to `materialization_provenance.inventory`.
5. Bind its attempt to `request.inventory_attempt_id`.
6. Increase the producer's collection sequence.
7. Report every retained descendant, including lifecycle tombstones.
8. Return the SDL through `MaterializationSubmission` on the ordinary result.

Import report types from `raes_contracts.materialization_inventory`.
Use `RuntimeInventoryReport`, `RuntimeDescendantBinding` and `RuntimeInventoryEvidence`.
The report uses the existing `/nodes` collection and source digest.
Its target scope must match `request.materialization_source.target_scope`.
Each binding names its address, the parent that caused it, and the source from the original plan.
Use a stable native identity digest for the resource incarnation.
Keep its creation receipt unchanged across refreshes.
A child can be created in one operation and reported in another. Its creation receipt keeps the first operation and attempt.
The source address identifies an original admitted node or network.
The parent instance index identifies the responsible replica.
Each discovered member has its own single-instance portable address.
Arbitrary native objects cannot become nodes without valid existing SDL semantics.

Populate resource bindings and native member origins as for ordinary materialization attestations.
Added nodes have no authored `source_node`.
Their causal parent belongs in the inventory binding.
Use `materialization_differences` to compute actual SDL differences.
Do not create executable plan nodes or modify the predecessor to insert discovered children.
The runtime derives their entries from the admitted description.

A terminated child remains in live SDL and has a `terminated` inventory record.
An autoremoved child leaves live SDL and retains an `autoremoved` record.
Both states require a separate lifecycle receipt.
A surviving child can retain a historical link to an autoremoved causal parent.
Do not infer either state from an incomplete scan or missing evidence.
Set `complete=false` when the declared collection cut is incomplete.
The runtime refuses success and retains its preceding accepted inventory.

`backend_selections` can identify chosen OPEN or CONSTRAINED concerns.
Use `RuntimeConcernSelection` with the registered address, field path and concern kind.
The runtime then records backend origin even if the value matches the processor template.
An unchanged processor choice retains processor origin without that additional claim.
EXACT declarations cannot be relabeled.
A choice or creation receipt does not prove an independent observation. It does not prove ownership.

## Public runtime operations

The manager keeps the original execution plan available for refresh:

```python
execution = manager.plan(scenario, run_scope=PlanScope(run_id="run-1"))
applied = manager.apply(execution)
refreshed = manager.refresh_inventory(execution)
```

Check each result's `success` and structured diagnostics.
The authored scenario and original execution plan remain unchanged.
The manager never calls apply during refresh.

The durable control plane uses the existing provisioning mutation owner:

```python
plane.register_planner_produced_plan(execution)
initial = plane.submit_provisioning(execution.provisioning, idempotency_key="initial")
refresh = plane.submit_inventory_refresh(execution.provisioning, idempotency_key="inventory-1")
status = plane.get_operation(refresh.operation_id)
```

Reusing the same key returns its saved receipt without another producer invocation.
Use a new key for a new inventory cut.
For HTTP submission, use the existing authenticated provisioning route with `inventory_refresh=true`.
The request must retain the exact original planner-authorized plan.
The refresh flag is part of the request identity. A refresh cannot reuse an apply claim.
The caller still needs permission to change state. Target and run scopes and request limits still apply.
After restart, register the original composite plan again before a new refresh.
Existing receipt retries remain available without replaying the backend.

Supervised providers use the admitted native operation and attempt identities.
The provider's result reference commits its original snapshot proposal.
The runtime validates that commitment before deriving accepted inventory and provenance.
The existing terminal commit records the separate accepted snapshot revision.

Accepted archive records expose their typed `inventory` report.
Existing snapshot DTOs, codecs, local stores and experiment run records retain it.
The protected archive contains the corresponding SDL bytes.
If a report fails any check, the runtime keeps the last trusted state. It does the same if the archive write fails.
Diagnostics identify the violated invariant without returning rejected document values.
Physical resources can still exist after a refusal.
Use the backend's established recovery and cleanup procedures for those effects.

## Dependency and migration

The existing `raes==7.0.0` pin does not provide this extension.
Use the first released RAE version that publishes `backend-runtime-descendants-v1`.
Do not select an unreleased version number from this document.
Update the downstream dependency pin after that release and verify manifest negotiation.
Older consumers must refuse the new semantics.
The bundled stubs do not advertise this contract.

LilRAE owns native creator attribution and lifecycle receipt authenticity.
This contract consumes those receipts as scoped producer assertions.
It does not find Docker creators, grant operator rights, scan hosts or capture and export study data.
Keep stronger ownership and independent observation claims under their own contracts.

See the [normative attestation contract](../../../specs/sdl/materialization-attestation.md#runtime-descendant-inventory)
and [result admission rules](../../../specs/formal/runtime-contracts/backend-result-admission.md).
