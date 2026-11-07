package admission

func sdlProcessProjection(subject any) map[string]any {
	projection := map[string]any{}
	for _, field := range []string{termName, termPID, termParentPID, termUser, termGroup, termWorkingDirectory} {
		fallback := any("")
		if field == termPID || field == termParentPID {
			fallback = nil
		}
		projection[field] = defaultMember(subject, field, fallback)
	}
	command := array(at(subject, "command"))
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
	soft, hard := at(v, "soft"), at(v, "hard")
	return require(!numericGreater(soft, hard) && (soft != termUnlimited || hard == termUnlimited))
}
func sdlResourceLimits(v any) error {
	seen := map[string]bool{}
	for _, limit := range array(at(v, "process_limits")) {
		identity := sdlProcessLimitIdentity(limit)
		if seen[identity] {
			return invalid()
		}
		seen[identity] = true
	}
	return nil
}
func sdlProcessLimitIdentity(v any) string {
	projection := sdlProcessProjection(at(v, "subject"))
	parts := []string{stringAt(v, "resource"), text(defaultMember(v, "scope", "process"))}
	for _, field := range []string{termName, termPID, termParentPID, termUser, termGroup, termWorkingDirectory, "role"} {
		parts = append(parts, sdlScalarIdentity(projection[field]))
	}
	redacted := "false"
	if projection["command_redacted"] == true {
		redacted = "true"
	}
	return join(append(parts, redacted, join(stringsOf(projection["command"])...))...)
}
