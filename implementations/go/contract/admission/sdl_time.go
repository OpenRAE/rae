package admission

import "slices"

func nonblankSDLFields(v any, fields ...string) bool {
	for _, field := range fields {
		if sdlBlank(stringAt(v, field)) {
			return false
		}
	}
	return true
}
func sdlTimeDomain(v any) error {
	kind, epoch := stringAt(v, termKind), stringAt(v, "epoch")
	return require(nonblankSDLFields(v, termDescription) && reducedRatio(at(v, "tick_period_seconds")) && (kind != termWallClock || epoch == epochUnix) && (kind != termMonotonic || epoch != epochUnix))
}
func sdlTimeMapping(v any) error {
	if !nonblankSDLFields(v, "source_domain_ref", "target_domain_ref", termDescription) || stringAt(v, "source_domain_ref") == stringAt(v, "target_domain_ref") {
		return invalid()
	}
	if stringAt(v, "mapping_kind") == termIdentity {
		return require(unitRatio(at(v, "scale")) && countEqual(defaultMember(v, "offset_ticks", jsonZero), 0))
	}
	return nil
}
func sdlTimeProgression(v any) error {
	mode := stringAt(v, "advancement_mode")
	return require(nonblankSDLFields(v, "clock_ref", termDescription) && (mode == advancementStepped) == (at(v, "step_ticks") != nil) && (mode == advancementRealTime || mode == advancementDilated || unitRatio(at(v, "pacing_ratio"))))
}
func sdlTemporalConstraint(v any) error {
	subjects := stringsOf(at(v, "subject_refs"))
	if !nonblankSDLFields(v, "clock_ref", termDescription) || !unique(subjects) || slices.ContainsFunc(subjects, sdlBlank) {
		return invalid()
	}
	valid := map[string]bool{
		constraintPrecedence: len(subjects) == 2,
		constraintDuration:   at(v, "duration_ticks") != nil,
		termWindow:           at(v, termStart) != nil && at(v, termEnd) != nil,
		kindDeadline:         at(v, termEnd) != nil,
		constraintCadence:    at(v, "cadence_ticks") != nil,
	}[stringAt(v, "constraint_kind")]
	if !valid {
		return invalid()
	}
	if at(v, termStart) != nil && at(v, termEnd) != nil {
		order, ok := fullCoordinateCompare(at(v, termStart), at(v, termEnd))
		if !ok || order > 0 {
			return invalid()
		}
	}
	return nil
}

const (
	epochUnix            = "unix"
	advancementDilated   = "dilated"
	constraintCadence    = "cadence"
	constraintPrecedence = "precedence"
	constraintDuration   = "duration"
)

const (
	advancementRealTime = "real_time"
	advancementStepped  = "stepped"
)
