package admission

import (
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// BackendPreparationCommitments binds a portable provisioning plan and its
// exact native predecessor. It reuses the existing model factories and JCS
// projections. These commitments grant no execution or delivery authority.
func BackendPreparationCommitments(v *Validator, plan binding.ProvisioningPlanV1, snapshot binding.RuntimeSnapshotV1) (string, string, error) {
	if v == nil || CheckPreparationOperations(plan) != nil || CheckPreparedSnapshot(snapshot) != nil {
		return "", "", invalid()
	}
	proposed, err := portableInventoryTransport(v, termProvisioningPlanV1, plan)
	if err != nil {
		return "", "", err
	}
	previous, err := portableInventoryTransport(v, termRuntimeSnapshotV1, snapshot)
	if err != nil {
		return "", "", err
	}
	if err = augmentationSnapshotFactories(previous, snapshot); err != nil {
		return "", "", err
	}
	delete(previous, termSchemaVersion)
	for _, key := range []string{"time_model_state", "realization_envelope"} {
		if _, ok := previous[key]; !ok {
			previous[key] = nil
		}
	}
	request, err := jsonDigest(map[string]any{fieldDomain: termProvisioning, "plan": augmentationPlanProjection(proposed, termProvisioningPlanV1)})
	if err != nil {
		return "", "", err
	}
	predecessor, err := jsonDigest(previous)
	return request, predecessor, err
}
