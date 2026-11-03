package admission

import "math/big"

func executionState(v any) error {
	generation, ok := number(at(v, "generation"))
	if !ok {
		return invalid()
	}
	observed, ok := number(at(v, "observed_generation"))
	if !ok || observed.Cmp(generation) > 0 {
		return invalid()
	}
	reserved, ok := number(at(v, "reserved"))
	if !ok {
		return invalid()
	}
	inFlight, ok := number(at(v, "in_flight"))
	if !ok {
		return invalid()
	}
	capacity, ok := number(at(v, "capacity"))
	if !ok || new(big.Rat).Add(reserved, inFlight).Cmp(capacity) > 0 {
		return invalid()
	}
	if boolean(at(v, "quiescent")) && (reserved.Sign() != 0 || inFlight.Sign() != 0) {
		return invalid()
	}
	if err := executionReadback(v); err != nil {
		return err
	}
	return require(fieldsUnique(v, "scheduler_state_refs", "resource_budget_state_refs", "pacing_deviation_refs", fieldEvidenceRefs))
}
func executionReadback(v any) error {
	lifecycle := stringAt(v, "observed_lifecycle")
	if boolean(at(v, "accepting_new_work")) && ((lifecycle != "starting" && lifecycle != statusRunning) || stringAt(v, "readiness") != termReady) {
		return invalid()
	}
	return require(boolean(at(v, "draining")) == (lifecycle == "draining") && boolean(at(v, "resources_released")) == (lifecycle == termTerminated))
}
