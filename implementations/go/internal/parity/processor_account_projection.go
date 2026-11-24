package parity

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func processorValueFreeAccounts(plan binding.ProvisioningPlanV1) (binding.ProvisioningPlanV1, error) {
	operations := processorField(plan.Operations)
	owner, err := processorTargetOwner()
	if err != nil {
		return binding.ProvisioningPlanV1{}, err
	}
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}
	for i := range operations {
		operation := &operations[i]
		if processorField(operation.ResourceType) != "account-placement" {
			continue
		}
		raw, err := processorAccountPayload(owner, processorField(operation.Payload), limits)
		if err != nil {
			return binding.ProvisioningPlanV1{}, err
		}
		if err := operation.Payload.UnmarshalJSON(raw); err != nil {
			return binding.ProvisioningPlanV1{}, err
		}
	}
	return plan, nil
}

func processorAccountPayload(owner *admission.Validator, payload map[string]json.RawMessage, limits ingress.Limits) (json.RawMessage, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	document, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		return nil, err
	}
	fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, document, limits)
	if err != nil {
		return nil, err
	}
	projected, err := admission.ValueFreeAccountPlacement(fragment)
	if err != nil {
		return nil, err
	}
	raw, err = json.Marshal(projected.Document())
	if err != nil {
		return nil, err
	}
	return raw, nil
}
