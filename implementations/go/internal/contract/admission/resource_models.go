package admission

import "math/big"

func resourceUnit(kind string) string {
	return map[string]string{termActionRate: termActions, termConcurrentActions: termActions, termStorageGrowth: "bytes", termInferenceTokens: "tokens", termImageGenerations: "images", termAccelerator: "accelerator_milliseconds"}[kind]
}

func resourceQuantity(v any) error {
	if object(at(v, "resource_kind")) != nil {
		return nil // Exact private semantics are checked at configured-pool admission.
	}
	kind, mode := stringAt(v, "resource_kind"), stringAt(v, "accounting_mode")
	allowed := map[string][]string{termActionRate: {termWindowedCounter}, termConcurrentActions: {"reservable_gauge"}, termStorageGrowth: {"growth_counter"}, termInferenceTokens: {termWindowedCounter, "cumulative_counter"}, termImageGenerations: {termWindowedCounter, "cumulative_counter"}, termAccelerator: {"lease"}}
	return require(resourceUnit(kind) == stringAt(v, "unit") && set(jsonStrings(allowed[kind]))[mode])
}

func resourceDemand(v any) error {
	return require(!numericGreater(at(v, "reservation"), at(v, "limit")) && (stringAt(v, "quantity", "accounting_mode") == termWindowedCounter) == (at(v, "window_ticks") != nil) && fieldsUnique(v, "evidence_refs") && (stringAt(v, "quantity", "resource_kind") != termStorageGrowth || stringAt(v, "reset") == "reconciled"))
}

func resourceCapacity(v any) error {
	if err := resourceQuantity(v); err != nil {
		return err
	}
	return require(!numericGreater(at(v, "protected_capacity"), at(v, "capacity")) && fieldsUnique(v, "priority_classes", "evidence_contract_ids"))
}

func resourceStateReference(v any) string {
	return stringAt(v, "policy_address") + ".resource-budget-state." + stringAt(v, "budget_id")
}

func resourceNumbersWithin(limit any, values ...any) bool {
	bound, ok := number(limit)
	if !ok {
		return false
	}
	total := new(big.Rat)
	for _, value := range values {
		amount, ok := number(value)
		if !ok {
			return false
		}
		total.Add(total, amount)
	}
	return total.Cmp(bound) <= 0
}

func resourceState(v any) error {
	if err := resourceQuantity(v); err != nil {
		return err
	}
	return require(stringAt(v, "state_ref") == resourceStateReference(v) && resourceNumbersWithin(at(v, "limit"), at(v, "reserved"), at(v, "current_use")) && resourceNumbersWithin(at(v, "configured_capacity"), at(v, "reserved"), at(v, "current_use")) && fieldsUnique(v, "evidence_refs"))
}

func resourceEvent(v any) error {
	disposition := map[string]string{"reserve": "reserved", "commit": "committed", "release": "released", "throttle": "throttled", "reject": termRejected, termReconcile: "reconciled"}[stringAt(v, "transition")]
	return require(stringAt(v, "budget_state_ref") == resourceStateReference(v) && stringAt(v, "disposition") == disposition && (stringAt(v, "transition") != "commit" || at(v, "measured") != nil) && fieldsUnique(v, "evidence_refs"))
}

func resourceMeasurement(v any) error {
	if object(at(v, "resource_kind")) == nil && stringAt(v, "unit") != resourceUnit(stringAt(v, "resource_kind")) {
		return invalid()
	}
	return require(fieldsUnique(v, "evidence_refs"))
}

func (e *Validator) resourceModel(name string, v any) (bool, error) {
	switch name {
	case termParticipantResourceBudgetPolicyV1, "ParticipantResourceBudgetPolicyModel":
		return true, resourcePolicy(v)
	case "participant-resource-pool-capacity-v1", "ParticipantResourcePoolCapacityModel":
		return true, resourceCapacity(v)
	case "participant-resource-budget-state-v1", "ParticipantResourceBudgetStateModel":
		return true, resourceState(v)
	case "participant-resource-budget-event-v1", "ParticipantResourceBudgetEventModel":
		return true, resourceEvent(v)
	case "ParticipantResourceQuantityModel":
		return true, resourceQuantity(v)
	case "ParticipantResourceBudgetDemandModel":
		return true, resourceDemand(v)
	case "ParticipantResourceMeasurementModel":
		return true, resourceMeasurement(v)
	case "ParticipantResourcePoolAllocationModel":
		return true, require(stringAt(v, "budget_state_ref") == resourceStateReference(v))
	case "ParticipantResourcePoolStateModel":
		return true, resourcePoolState(v)
	default:
		return false, nil
	}
}
