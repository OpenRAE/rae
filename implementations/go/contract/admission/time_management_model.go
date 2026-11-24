package admission

func timeManagementModel(v any) error {
	strength, basis := stringAt(v, "claim_strength"), stringAt(v, "basis")
	if boolean(at(v, "unsupported_disclosure")) && strength == postureExact || basis == termWallClockOnly && strength != "display" || (strength == "bounded" || strength == postureExact) && at(v, "clock_ref") == nil {
		return invalid()
	}
	switch stringAt(v, "mode") {
	case "backend_serialized":
		return require(boolean(at(v, "backend_serialized")) && basis == "serialized_backend_order" && at(v, "clock_ref") != nil)
	case "devs", "fmi":
		return require(at(v, "clock_ref") != nil && basis != termWallClockOnly)
	case "lookahead":
		return require(at(v, "lookahead") != nil)
	case "pacing":
		return require(at(v, "advance_by") != nil)
	case "rollback":
		return require(len(array(at(v, "rollback_event_refs"))) > 0)
	case statusUnsupported:
		return require(boolean(at(v, "unsupported_disclosure")))
	default:
		return nil
	}
}
