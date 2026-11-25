package stub

import (
	"context"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

// DispatchStep simulates this dispatch only; the runtime owns all control
// transitions. An executable governed step fails with its attempt
// provenance; an executable scripted step succeeds.
func (o *orchestrator) DispatchStep(ctx context.Context, request binding.WorkflowStepDispatchV1) (binding.WorkflowStepResponseV1, error) {
	var response binding.WorkflowStepResponseV1
	if err := callReady(ctx); err != nil {
		return response, err
	}
	dispatch, err := checkedPlan(request, "workflow-step-dispatch-v1")
	if err != nil {
		return response, err
	}
	commitment, err := dispatchDigest(request)
	if err != nil {
		return response, err
	}
	stepType, mode := text(dispatch, "step_type"), text(dispatch, "execution_mode")
	if mode == "" {
		mode = "scripted"
	}
	executable := stepType == "objective" || stepType == "retry"
	governed := executable && mode != "scripted"
	var provenance, outcome any
	if governed {
		provenance = map[string]any{"step_name": dispatch["step_name"], "execution_mode": mode, "attempt_id": dispatch["dispatch_id"], "objective_address": textValue(dispatch, "objective_address"), "procedure_ref": textValue(dispatch, "procedure_ref"), "exposed_scaffold_refs": listValue(dispatch, "scaffold_refs"), "allowed_action_families": listValue(dispatch, "allowed_action_families"), "outcome": termFailed}
	}
	if executable {
		outcome = "succeeded"
		if governed {
			outcome = termFailed
		}
	}
	observations := object(dispatch, "observation_digests")
	if observations == nil {
		observations = map[string]any{}
	}
	raw, err := json.Marshal(map[string]any{termSchemaVersion: "workflow-step-response/v1", "dispatch_id": dispatch["dispatch_id"], "dispatch_digest": commitment, "outcome": outcome, "observations": observations, "attempt_provenance": provenance})
	if err != nil || json.Unmarshal(raw, &response) != nil {
		return binding.WorkflowStepResponseV1{}, invalid()
	}
	return response, nil
}

// dispatchDigest binds the complete dispatch model, with its constructor defaults.
func dispatchDigest(request binding.WorkflowStepDispatchV1) (string, error) {
	owner, err := schemas()
	if err != nil {
		return "", err
	}
	raw, err := json.Marshal(request)
	if err != nil {
		return "", invalid()
	}
	commitment, err := admission.WorkflowStepDispatchDigest(owner, raw)
	if err != nil {
		return "", invalid()
	}
	return commitment, nil
}

func textValue(document map[string]any, field string) any {
	if value, present := document[field]; present {
		return value
	}
	return ""
}

func listValue(document map[string]any, field string) []any {
	return slices.Clone(array(document[field]))
}
