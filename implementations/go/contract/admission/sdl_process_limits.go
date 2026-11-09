package admission

import "slices"

const processLimitScopeField = "scope"

func sdlProcessProjection(subject any) map[string]any {
	projection := map[string]any{}
	for _, field := range []string{termName, termPID, termParentPID, termUser, termGroup, termWorkingDirectory} {
		fallback := any("")
		if field == termPID || field == termParentPID {
			fallback = nil
		}
		projection[field] = defaultMember(subject, field, fallback)
	}
	command := slices.Clone(array(at(subject, "command")))
	if command == nil {
		command = []any{}
	}
	projection["command"] = command
	projection["command_redacted"] = defaultMember(subject, "command_redacted", false)
	projection["role"] = defaultMember(subject, "role", termOther)
	return projection
}
func sdlStableProcessSelector(projection map[string]any) bool {
	for _, field := range []string{termName, termUser, termGroup, termWorkingDirectory} {
		if projection[field] != "" {
			return true
		}
	}
	return projection[termPID] != nil || projection[termParentPID] != nil || projection["role"] != termOther
}
func sdlProcessLimit(v any) error {
	projection := sdlProcessProjection(at(v, "subject"))
	for _, value := range projection {
		if materializedToken.MatchString(text(value)) {
			return invalid()
		}
	}
	command := array(projection["command"])
	for _, item := range command {
		if materializedToken.MatchString(text(item)) {
			return invalid()
		}
	}
	stable := sdlStableProcessSelector(projection)
	if !stable && len(command) == 0 || projection["command_redacted"] == true && (len(command) > 0 || !stable) || materializedToken.MatchString(stringAt(v, termDescription)) {
		return invalid()
	}
	return sdlProcessLimitBounds(at(v, "soft"), at(v, "hard"))
}

func sdlProcessLimitBounds(soft, hard any) error {
	for _, value := range []any{soft, hard} {
		if value != termUnlimited && !sdlNumberField(value, "integer:0:") {
			return invalid()
		}
	}
	return require(!numericGreater(soft, hard) && (soft != termUnlimited || hard == termUnlimited))
}
func sdlResourceLimits(v any) error {
	seen := map[string]bool{}
	for _, limit := range array(at(v, "process_limits")) {
		identity, err := sdlProcessLimitIdentity(limit)
		if err != nil {
			return err
		}
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	return nil
}

// Identity excludes bound values and description, as the authored limit does.
func sdlProcessLimitIdentity(v any) (string, error) {
	return jsonDigest(sdlProcessLimitIdentityPayload(v))
}
func sdlProcessLimitIdentityPayload(v any) map[string]any {
	return map[string]any{
		"resource":             at(v, "resource"),
		"subject":              sdlProcessProjection(at(v, "subject")),
		processLimitScopeField: defaultMember(v, processLimitScopeField, "process"),
	}
}
func sdlProcessLimitProjection(v any) map[string]any {
	projection := sdlProcessLimitIdentityPayload(v)
	projection["soft"] = at(v, "soft")
	projection["hard"] = at(v, "hard")
	return projection
}

// Callers supply constructed limit and capability records. Nil domains select
// the corresponding bound value; an explicit empty domain stays empty.
func sdlProcessLimitCapabilityAdmits(capability, v any, soft, hard []any) bool {
	if soft == nil {
		soft = []any{at(v, "soft")}
	}
	if hard == nil {
		hard = []any{at(v, "hard")}
	}
	return sdlProcessLimitDomainAdmits(capability, stringAt(v, "resource"), text(defaultMember(v, processLimitScopeField, "process")), soft, hard)
}
func sdlProcessLimitDomainAdmits(capability any, resource, scope string, soft, hard []any) bool {
	if stringAt(capability, "resource") != resource || !slices.Contains(stringsOf(at(capability, "scopes")), scope) {
		return false
	}
	for _, values := range [][]any{soft, hard} {
		for _, value := range values {
			if !sdlProcessLimitValueAdmitted(capability, value) {
				return false
			}
		}
	}
	return true
}
func sdlProcessLimitValueAdmitted(capability, value any) bool {
	if value == termUnlimited {
		return at(capability, "supports_unlimited") == true
	}
	actual, valid := number(value)
	minimum, minOK := defaultNumber(capability, "minimum", 0)
	if !valid || !actual.IsInt() || !minOK || actual.Cmp(minimum) < 0 {
		return false
	}
	if at(capability, "maximum") == nil {
		return true
	}
	maximum, maxOK := number(at(capability, "maximum"))
	return maxOK && actual.Cmp(maximum) <= 0
}
