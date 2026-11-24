package admission

func sdlCapabilityOverride(v any) error {
	if !fieldsUnique(v, termEffective, "add", "drop") || len(array(at(v, termEffective)))+len(array(at(v, "add")))+len(array(at(v, "drop"))) == 0 {
		return invalid()
	}
	subject := at(v, "subject")
	for _, field := range []string{termName, termUser, termGroup, termWorkingDirectory, termDescription} {
		if stringAt(subject, field) != "" {
			return nil
		}
	}
	return require(at(subject, termPID) != nil || at(subject, termParentPID) != nil || len(array(at(subject, "command"))) > 0 || text(defaultMember(subject, "role", termOther)) != termOther)
}
func sdlCapabilityPolicy(v any) error {
	if !fieldsUnique(v, "required", termEffective, "add", "drop") {
		return invalid()
	}
	seen := map[string]bool{}
	for _, override := range array(at(v, "process_overrides")) {
		subject := at(override, "subject")
		selectors := []string{}
		for _, field := range []string{termName, termPID, termParentPID, termUser, termGroup, termWorkingDirectory} {
			value := at(subject, field)
			if value == nil || value == "" {
				selectors = append(selectors, "")
			} else {
				selectors = append(selectors, sdlScalarIdentity(value))
			}
		}
		selectors = append(selectors, join(stringsOf(at(subject, "command"))...))
		role := text(defaultMember(subject, "role", termOther))
		if role == termOther {
			role = ""
		}
		selectors = append(selectors, role)
		// A description-only selector does not anchor duplicate identity.
		if join(selectors...) == join("", "", "", "", "", "", "[]", "") {
			continue
		}
		key := join(append(selectors, text(defaultMember(override, "scope", "process")))...)
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
