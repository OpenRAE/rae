package admission

func controlEffectSubject(v any) string {
	switch stringAt(v, termKind) {
	case termTransform, termMask, termRoute:
		return stringAt(v, termSource, "subject_ref")
	case "request-review":
		return stringAt(v, "parent", "subject_ref")
	case termInterrupt, termShutdown:
		return stringAt(v, "target_ref")
	case termInject, termHandoff:
		return stringAt(v, "participant_address")
	default:
		return stringAt(v, "subject", "subject_ref")
	}
}

func controlLifecycleInvalidates(lifecycle, operation, context any) bool {
	if stringAt(lifecycle, termKind) != termInterrupt && stringAt(lifecycle, termKind) != termShutdown {
		return false
	}
	var scope any
	switch stringAt(operation, termKind) {
	case termInject, termHandoff:
		scope = operation
	case termTransform, termMask, termRoute:
		scope = at(operation, termResult)
	case termPermit, termDelay:
		scope = at(operation, "subject")
	default:
		return false
	}
	scopes := map[string]any{termParticipant: at(scope, "participant_address"), termEpisode: at(scope, "episode_id"), "run": at(context, "run", "ref")}
	value, known := scopes[stringAt(lifecycle, "target_kind")]
	return !known || equal(value, at(lifecycle, "target_ref"))
}

func controlSameSubjectConflict(a, b any) bool {
	aKind, bKind := stringAt(a, termKind), stringAt(b, termKind)
	if aKind == termDelay && bKind == termDelay {
		return !equal(at(a, "clock"), at(b, "clock")) || numericGreater(at(a, "earliest_order"), at(b, "latest_order")) || numericGreater(at(b, "earliest_order"), at(a, "latest_order"))
	}
	if aKind == termHandoff && bKind == termHandoff {
		return !equal(at(a, "resulting_controller_ref"), at(b, "resulting_controller_ref"))
	}
	transformations := map[string]bool{termTransform: true, termMask: true, termRoute: true}
	return transformations[aKind] && transformations[bKind] && !equal(a, b) || aKind == termInterrupt && bKind == termShutdown || aKind == termShutdown && bKind == termInterrupt
}

func controlEffectPair(left, right any, ancestors map[string]map[string]bool, context any) bool {
	a, b := at(left, "target"), at(right, "target")
	leftFirst, rightFirst := ancestors[stringAt(right, "effect_id")][stringAt(left, "effect_id")], ancestors[stringAt(left, "effect_id")][stringAt(right, "effect_id")]
	if leftFirst && controlLifecycleInvalidates(a, b, context) || rightFirst && controlLifecycleInvalidates(b, a, context) {
		return true
	}
	sameSubject := controlEffectSubject(a) == controlEffectSubject(b)
	if sameSubject && stringAt(a, termKind) == termDelay && stringAt(b, termKind) == termDelay {
		return controlSameSubjectConflict(a, b)
	}
	return sameSubject && controlSameSubjectConflict(a, b) || !leftFirst && !rightFirst
}
