package trial

import (
	"context"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func admitPlan(plan binding.AdmittedTrialPlanV1) (validation.Value, error) {
	owner, err := trialOwner()
	if err != nil {
		return validation.Value{}, err
	}
	if err = admission.CheckTransport(plan, trialIngress()); err != nil {
		return validation.Value{}, err
	}
	raw, err := encoded(plan)
	if err != nil {
		return validation.Value{}, err
	}
	return owner.Validate("admitted-trial-plan-v1", raw, trialIngress(), nil)
}

// Readmit requires the candidate to equal recompilation of independent original inputs.
func Readmit(ctx context.Context, plan binding.AdmittedTrialPlanV1, request Request) (binding.AdmittedTrialPlanV1, error) {
	candidate, err := admitPlan(plan)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	owner, err := trialOwner()
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	raw, err := admission.TrialPlanProjection(owner, candidate, trialIngress())
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	expected, err := CompileContext(ctx, request)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if expected.Plan == nil {
		return binding.AdmittedTrialPlanV1{}, fault.New(fault.InvalidInput, "trial-readmission-mismatch", nil)
	}
	expectedRaw, err := encoded(expected.Plan)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, err
	}
	if !sameJSON(raw, expectedRaw) {
		return binding.AdmittedTrialPlanV1{}, fault.New(fault.InvalidInput, "trial-readmission-mismatch", nil)
	}
	var result binding.AdmittedTrialPlanV1
	err = decode(raw, &result)
	return result, err
}

// PlanBatchSchedule computes dispatch order from a generated plan carrier.
func PlanBatchSchedule(plan binding.AdmittedTrialPlanV1) (BatchSchedule, error) {
	admitted, err := admitPlan(plan)
	if err != nil {
		return BatchSchedule{}, err
	}
	return PlanBatchScheduleValue(admitted)
}

// PlanBatchScheduleValue retains source member order when coordinate keys tie.
func PlanBatchScheduleValue(plan validation.Value) (BatchSchedule, error) {
	owner, err := trialOwner()
	if err != nil {
		return BatchSchedule{}, err
	}
	order, err := admission.TrialEntryOrder(owner, plan)
	if err != nil {
		return BatchSchedule{}, err
	}
	var document trialPlan
	if decode(plan.JSON(), &document) != nil {
		return BatchSchedule{}, trialInvalid()
	}
	schedule := BatchSchedule{PlanID: document.ID, PlanDigest: document.Digest, SchedulingPolicyID: "trial-coordinate-canonical-v1", AdmittedParallelismCeiling: 1, Entries: make([]ScheduledEntry, len(order))}
	if !isNull(document.Allocation) {
		schedule.SchedulingPolicyID = "experiment-recorded-allocation-v1"
	}
	if !isNull(document.Isolation) {
		var proof struct {
			ID          string `json:"proof_id"`
			Parallelism int    `json:"requested_parallelism"`
		}
		if json.Unmarshal(document.Isolation, &proof) != nil {
			return BatchSchedule{}, trialInvalid()
		}
		if proof.Parallelism > 1 {
			schedule.AdmittedParallelismCeiling = min(proof.Parallelism, len(order))
			schedule.IsolationProofRef = &proof.ID
		}
	}
	for index, id := range order {
		schedule.Entries[index] = ScheduledEntry{PlanEntryID: id, RunID: document.Entries[id].RunID, DispatchOrdinal: index}
	}
	return schedule, nil
}

// RealizationAssignmentKey returns the canonical coordinate projection used for exact assignments.
func RealizationAssignmentKey(coordinate admission.Fragment) (string, error) {
	if admission.CheckFragment(coordinate, admission.RealizationValue) != nil {
		return "", trialInvalid()
	}
	raw, err := encoded(coordinate.Document())
	if err != nil {
		return "", err
	}
	return assignmentKey(raw)
}
func assignmentKey(raw []byte) (string, error) {
	owner, err := trialOwner()
	if err != nil {
		return "", err
	}
	if err = owner.CheckModelFragment("admitted-trial-plan-v1", "#/$defs/TrialCoordinateModel", raw, trialIngress()); err != nil {
		return "", err
	}
	var c coordinate
	if decode(raw, &c) != nil {
		return "", trialInvalid()
	}
	raw, err = canonical(c.projection())
	return string(raw), err
}
