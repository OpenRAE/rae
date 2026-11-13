package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/processor"
)

// AssumedSnapshot projects a valid empty-base plan into explicitly assumed
// state. It contains no backend delivery or observation assertion.
func AssumedSnapshot(input ExecutionPlan) (binding.RuntimeSnapshotV1, error) {
	plan, ok := input.(*executionPlan)
	if !ok || plan == nil || !plan.Valid() || len(fieldValue(plan.context.Snapshot.Entries)) > 0 {
		return binding.RuntimeSnapshotV1{}, invalidPlan()
	}
	entries := map[string]snapshotEntry{}
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		for _, operation := range plan.operations[domain] {
			if operation.Action == termDelete {
				continue
			}
			resource := plan.resources[operation.Address]
			entries[operation.Address] = snapshotEntry{Address: operation.Address, Domain: domain, Kind: operation.Kind, Payload: operation.Payload, Ordering: operation.Ordering, Refresh: operation.Refresh, Profiles: resource.profiles, Status: "planned-state-projection"}
		}
	}
	wire := map[string]any{"schema_version": "runtime-snapshot/v1", "entries": entries}
	if err := value.ValidateProjected(wire, value.Runtime(), planProjectionValue); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	raw, err := json.Marshal(wire)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, invalidPlan()
	}
	var snapshot binding.RuntimeSnapshotV1
	if json.Unmarshal(raw, &snapshot) != nil {
		return binding.RuntimeSnapshotV1{}, invalidPlan()
	}
	if err := checkTransport("runtime-snapshot-v1", snapshot); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	return snapshot, nil
}

// Reconcile plans the baseline, assumes its state, and plans the candidate against it.
func Reconcile(baseline, candidate processor.Compilation, manifest binding.BackendManifestV2, options Options) (Reconciliation, error) {
	first, err := PlanWithManifest(baseline, manifest, options)
	if err != nil {
		return Reconciliation{}, err
	}
	result := Reconciliation{Baseline: first}
	if !first.Plan.Valid() {
		return result, nil
	}
	snapshot, err := AssumedSnapshot(first.Plan)
	if err != nil {
		return result, err
	}
	result.Snapshot = snapshot
	options.Snapshot = &snapshot
	second, err := PlanWithManifest(candidate, manifest, options)
	if err != nil {
		return result, err
	}
	result.Candidate = second
	native, ok := second.Plan.(*executionPlan)
	if !ok {
		return result, invalidPlan()
	}
	counts := &Actions{}
	for _, domain := range []string{termProvisioning, termOrchestration, termEvaluation} {
		for _, operation := range native.operations[domain] {
			switch operation.Action {
			case termCreate:
				counts.Create++
			case termUpdate:
				counts.Update++
			case termDelete:
				counts.Delete++
			case termUnchanged:
				counts.Unchanged++
			}
		}
	}
	result.Actions = counts
	return result, nil
}
