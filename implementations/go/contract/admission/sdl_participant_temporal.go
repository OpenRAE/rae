package admission

const termResetBoundary = "reset_boundary"

func sdlParticipantTemporal(v any) error {
	if !fieldsUnique(v, "event_points") || !nonblankSDLRefs(v, "backend_disclosure_refs") || len(array(at(v, "backend_disclosure_refs"))) == 0 {
		return invalid()
	}
	for _, field := range participantTemporalFields(stringAt(v, "temporal_kind")) {
		if at(v, field) == nil {
			return invalid()
		}
	}
	if err := participantTemporalPoints(v); err != nil {
		return err
	}
	return participantSharedTemporal(v)
}

func participantTemporalFields(kind string) []string {
	switch kind {
	case "schedule":
		return []string{termWindowRef}
	case "cadence":
		return []string{termDurationRef, termResetBoundary, termReplayBoundary, "randomization_basis"}
	case "time_window":
		return []string{termWindowRef, termResetBoundary, termReplayBoundary, "randomization_basis"}
	case termDwell:
		return []string{termWindowRef, termDurationRef, termResetBoundary, termReplayBoundary}
	default:
		return []string{termDurationRef, termResetBoundary, termReplayBoundary}
	}
}

func participantTemporalPoints(v any) error {
	points := set(at(v, "event_points"))
	switch stringAt(v, "temporal_kind") {
	case "schedule":
		return require(!disjoint([]string{"submit", termStart}, points))
	case "cadence":
		return require(!disjoint([]string{"submit", termStart, basisObserved, termEffective}, points))
	case "time_window":
		return require(points["window_open"] && points["window_close"])
	case kindDeadline:
		outcomes := []string{termEnd, basisObserved, termEffective}
		if at(v, "shared_time_binding") != nil {
			outcomes = append(outcomes, termStart)
		}
		return require(len(points) >= 2 && points[kindDeadline] && !disjoint(outcomes, points))
	case termDwell:
		return require(len(points) >= 2 && !disjoint([]string{termStart, "window_open"}, points) && !disjoint([]string{termEnd, "window_close"}, points))
	case "latency":
		return require(len(points) >= 2)
	default:
		return nil
	}
}

func participantSharedTemporal(v any) error {
	binding := at(v, "shared_time_binding")
	if binding == nil {
		return nil
	}
	point := stringAt(binding, "event_point")
	if !set(at(v, "event_points"))[point] {
		return invalid()
	}
	switch stringAt(v, "temporal_kind") {
	case kindDeadline:
		return require(stringAt(binding, "evidence_mode") == termEvent)
	case termDwell:
		return require(stringAt(binding, "evidence_mode") != termEvent && point == termStart)
	default:
		return invalid()
	}
}

const termReplayBoundary = "replay_boundary"
