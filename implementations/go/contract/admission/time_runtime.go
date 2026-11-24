package admission

func runtimeClock(v any) error {
	history := array(at(v, "history"))
	if len(history) == 0 {
		return invalid()
	}
	if stringAt(history[0], termKind) != "initialize" || at(history[0], "previous") != nil {
		return invalid()
	}
	for index, event := range history {
		if !countEqual(at(event, "sequence"), index) {
			return invalid()
		}
		if index > 0 {
			prior := history[index-1]
			if !coordinateEqual(at(event, "previous"), at(prior, "resulting")) {
				return invalid()
			}
			if err := clockTransition(at(prior, "resulting"), event); err != nil {
				return err
			}
		}
	}
	last := history[len(history)-1]
	return require(equal(at(v, "sequence"), at(last, "sequence")) && coordinateEqual(at(v, "coordinate"), at(last, "resulting")) && equal(at(v, termState), at(last, "resulting_state")))
}
func clockTransition(previous, event any) error {
	prior := coordinateView(previous)
	result := coordinateView(at(event, "resulting"))
	if prior == nil || result == nil {
		return invalid()
	}
	switch stringAt(event, termKind) {
	case "advance":
		order, ok := fullCoordinateCompare(result, prior)
		return require(ok && order > 0 && equal(at(result, "segment"), at(prior, "segment")))
	case "pause", "resume":
		return require(equal(result, prior))
	case "jump", "reset", "replay":
		return require(numericSuccessor(at(result, "segment"), at(prior, "segment")))
	default:
		return invalid()
	}
}
func timeRuntime(v any) error {
	if !keyed(at(v, "clocks"), "clock_address") {
		return invalid()
	}
	for _, clock := range object(at(v, "clocks")) {
		if err := runtimeClock(clock); err != nil {
			return err
		}
	}
	return nil
}
