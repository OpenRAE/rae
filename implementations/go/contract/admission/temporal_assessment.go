package admission

func coordinateLE(left, right any) bool {
	order, ok := fullCoordinateCompare(left, right)
	return ok && order <= 0
}
func coordinateLT(left, right any) bool {
	order, ok := fullCoordinateCompare(left, right)
	return ok && order < 0
}
func temporalDeadline(context any, proofs []any, boundary string, clock any, native string) (string, string) {
	if native == "not_dispatched" {
		if coordinateLT(at(context, "bound_end"), at(context, "submitted_at")) {
			return termMissed, "The shared clock is past the authored deadline before dispatch."
		}
		return outcomeIndeterminate, "The action was not dispatched; its selected event did not occur."
	}
	if len(proofs) != 1 || !validDeadlineProof(context, proofs[0], boundary, clock) {
		return outcomeIndeterminate, "Missing or invalid evidence for the bound action event and shared-time context."
	}
	if coordinateLE(at(proofs[0], "coordinate"), at(context, "bound_end")) {
		return "met", "The selected action event is evidenced at or before the authored deadline."
	}
	return termMissed, "The selected action event is evidenced after the authored deadline."
}
func validDeadlineProof(context, proof any, boundary string, clock any) bool {
	coordinate := at(proof, "coordinate")
	if coordinate == nil {
		return false
	}
	return text(defaultMember(proof, "evidence_mode", termEvent)) == termEvent && stringAt(proof, "observation_boundary_address") == boundary && equal(at(proof, "event_point"), at(context, "binding", "event_point")) && equal(at(coordinate, "segment"), at(context, "submitted_at", "segment")) && equal(at(coordinate, "segment"), at(clock, "coordinate", "segment")) && coordinateLE(at(context, "submitted_at"), coordinate) && coordinateLE(coordinate, at(clock, "coordinate"))
}
func temporalDwell(context any, proofs []any, clock any) (string, string) {
	start, end := at(context, "bound_start"), at(context, "bound_end")
	for _, event := range array(at(clock, "history")) {
		if stringAt(event, termKind) == "pause" && coordinateLE(start, at(event, "resulting")) && coordinateLT(at(event, "resulting"), end) {
			return outcomeIndeterminate, "The dwell interval crosses a pause; frozen shared time is not continuous condition evidence."
		}
	}
	if len(proofs) == 1 && validDwellScope(context, proofs[0], clock) {
		status, reason, valid := dwellCoverage(proofs[0], start, end)
		if valid {
			return status, reason
		}
	}
	return outcomeIndeterminate, "Missing or invalid continuous evidence for the bound condition and interval."
}
func validDwellScope(context, proof, clock any) bool {
	binding := at(context, "binding")
	start, end, submitted := at(context, "bound_start"), at(context, "bound_end"), at(context, "submitted_at")
	return stringAt(proof, "evidence_mode") == "continuous" && equal(at(proof, "condition_precondition_id"), at(binding, "condition_precondition_id")) && equal(at(proof, "observation_boundary_address"), at(binding, "observation_boundary_address")) && start != nil && equal(at(start, "segment"), at(end, "segment")) && equal(at(start, "segment"), at(submitted, "segment")) && equal(at(start, "segment"), at(clock, "coordinate", "segment")) && coordinateLE(end, submitted)
}
func dwellCoverage(proof, start, end any) (string, string, bool) {
	position := start
	holds := true
	valid := len(array(at(proof, "coverage"))) > 0
	for _, interval := range array(at(proof, "coverage")) {
		left, right := at(interval, "start"), at(interval, "end")
		if !equal(left, position) || !coordinateLT(left, right) || !coordinateLE(right, end) || !equal(at(left, "segment"), at(right, "segment")) {
			valid = false
		} else {
			position = right
			holds = holds && boolean(at(interval, "condition_holds"))
		}
	}
	valid = valid && equal(position, end)
	if holds {
		return "met", "Continuous coverage attests the condition throughout the authored interval.", valid
	}
	return termMissed, "The condition did not hold throughout the authored interval.", valid
}
