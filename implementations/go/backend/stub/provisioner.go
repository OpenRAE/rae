package stub

import (
	"context"

	"github.com/google/go-cmp/cmp"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

type provisioner struct{ envelope map[string]any }

// NewProvisioner constructs an inert provisioner with no configured envelope.
func NewProvisioner() (Provisioner, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	return NewProvisionerWithConfiguration(Configuration{})
}

// NewProvisionerWithConfiguration admits and copies a full configured envelope.
func NewProvisionerWithConfiguration(configuration Configuration) (Provisioner, error) { //nolint:ireturn // The declared public API returns the portable role interface.
	result := &provisioner{}
	if configuration.Envelope != nil {
		envelope, err := checkedPlan(*configuration.Envelope, "realization-envelope-v1")
		if err != nil {
			return nil, err
		}
		result.envelope = envelope
	}
	return result, nil
}
func (*provisioner) Validate(ctx context.Context, _ binding.ProvisioningPlanV1) ([]diagnostic.Diagnostic, error) {
	if err := callReady(ctx); err != nil {
		return nil, err
	}
	return []diagnostic.Diagnostic{}, nil
}
func (p *provisioner) Apply(ctx context.Context, plan binding.ProvisioningPlanV1, previous binding.RuntimeSnapshotV1) (runtimecontract.ApplyResult, error) {
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := admitProvisioning(plan); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	request, err := checkedPlan(plan, "provisioning-plan-v1")
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	snapshot, err := snapshotObject(previous)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	var identity map[string]any
	if p.envelope != nil {
		identity = envelopeIdentity(p.envelope)
		if len(array(request["realization_constraints"])) > 0 && (request["operation_id"] == nil || !cmp.Equal(request["realization_envelope"], identity)) {
			copied, copyErr := snapshotResult(snapshot)
			return runtimecontract.ApplyResult{Success: false, Snapshot: copied, Diagnostics: []diagnostic.Diagnostic{{Code: "stub-backend.realization-envelope.mismatch", Severity: termError, Domain: termRuntime, Address: "runtime.stub.provisioning", Message: "Provisioning plan does not match the selected stub realization envelope."}}}, copyErr
		}
	}
	observations := []runtimecontract.RealizationObservationDisclosure{}
	if p.envelope != nil {
		observations, err = retainedObservations(request, snapshot, p.envelope)
		if err != nil {
			return runtimecontract.ApplyResult{}, err
		}
	}
	changed := foldProvisioning(request, snapshot)

	if identity != nil {
		snapshot["realization_envelope"] = identity
		snapshot["realization_observations"] = []any{}
	}
	output, err := snapshotResult(snapshot)
	if err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	if err := callReady(ctx); err != nil {
		return runtimecontract.ApplyResult{}, err
	}
	return runtimecontract.ApplyResult{Success: true, Snapshot: output, ChangedAddresses: changed, OperationalRealizationObservations: observations}, nil
}
func admitProvisioning(plan binding.ProvisioningPlanV1) error {
	// The existing runtime-operation limits are stricter than transport byte bounds.
	return admission.CheckPreparationOperations(plan)
}
func envelopeIdentity(envelope map[string]any) map[string]any {
	return map[string]any{"contract_id": envelope["contract_id"], "schema_version": envelope["schema_version"], "envelope_id": envelope["id"], "digest": envelope["digest"], termConfigurationDigest: object(envelope, "configuration")[termConfigurationDigest]}
}
func operationEntry(operation map[string]any, domain, status string) map[string]any {
	ordering, refresh := operation["ordering_dependencies"], operation["refresh_dependencies"]
	if ordering == nil {
		ordering = []any{}
	}
	if refresh == nil {
		refresh = []any{}
	}
	return map[string]any{"address": operation["address"], "domain": domain, "resource_type": operation["resource_type"], "payload": operation["payload"], "ordering_dependencies": ordering, "refresh_dependencies": refresh, termStatus: status}
}

func foldProvisioning(request, snapshot map[string]any) []string {
	entries := table(snapshot, "entries")
	changed := []string{}
	for _, item := range array(request["operations"]) {
		operation, _ := item.(map[string]any)
		address := text(operation, "address")
		action := text(operation, "action")
		if action == termDelete {
			delete(entries, address)
			changed = append(changed, address)
			continue
		}
		status := "applied"
		if action == termUnchanged {
			status = termUnchanged
		}
		entries[address] = operationEntry(operation, "provisioning", status)
		if action != termUnchanged {
			changed = append(changed, address)
		}
	}
	return changed
}
