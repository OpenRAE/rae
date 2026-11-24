package experiment

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

func checkRecordTree(document any) error {
	return admission.CheckTransportTree(document, runtimeIngress())
}

// checkRuntimeValue reuses the contract owner's portable runtime value profile.
// Transport checks bound allocation before the stricter per-value work limits.
func checkRuntimeValue(document any) error {
	if err := admission.CheckTransportTree(document, runtimeIngress()); err != nil {
		return err
	}
	raw, err := json.Marshal(document)
	if err != nil {
		return integrity()
	}
	limits := runtimeIngress()
	limits.MaxBytes += 2
	limits.MaxDepth++
	parsed, err := ingress.Parse(append(append([]byte{'['}, raw...), ']'), limits, ingress.Array)
	if err != nil {
		return err
	}
	values := array(parsed)
	if len(values) != 1 {
		return integrity()
	}
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	_, err = admission.AdmitFragment(owner, admission.RealizationValue, values[0], runtimeIngress())
	return err
}
func checkTrialRequest(request Trial) error {
	return checkRuntimeValue(map[string]any{"plan": request.Plan, termPlanEntryID: request.PlanEntryID, "execution_attempt_id": request.ExecutionAttemptID, "instantiated_sdl_digest": request.Realization.SnapshotDigest, "provisioning_plan": request.Realization.ProvisioningPlan, "orchestration_plan": request.Realization.OrchestrationPlan, "evaluation_plan": request.Realization.EvaluationPlan})
}
func checkTrialResult(result Observation) error {
	return checkRuntimeValue(map[string]any{"operation_receipts": result.OperationReceipts, "execution_snapshot": result.Snapshot, "evidence": result.Evidence, "cleanup_receipt": result.CleanupReceipt, "cleanup_evidence": result.CleanupEvidence})
}
