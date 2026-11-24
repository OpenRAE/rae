package realization

type packageCoordinate struct{ manager, name, architecture string }

func (m *concernMetadata) linkedPackage(reference map[string]any) map[string]any {
	coordinate := func(row map[string]any) packageCoordinate {
		manager, _ := row[termManager].(string)
		name, _ := row[termName].(string)
		architecture, _ := row[termArchitecture].(string)
		return packageCoordinate{manager, name, architecture}
	}
	if m.packages == nil {
		m.packages = map[packageCoordinate][]map[string]any{}
		value, err := sourceConcernValue(m.concern.input.sections[termNodes].values[m.concern.name], []string{termRuntime, termPackages})
		if err != nil {
			m.err = err
			return nil
		}
		rows, _ := value.([]any)
		for _, item := range rows {
			row, _ := item.(map[string]any)
			key := coordinate(row)
			m.packages[key] = append(m.packages[key], row)
			if key.architecture != "" {
				key.architecture = ""
				m.packages[key] = append(m.packages[key], row)
			}
		}
	}
	rows := m.packages[coordinate(reference)]
	if len(rows) != 1 {
		m.invalid = true
		return nil
	}
	return rows[0]
}

func (m *concernMetadata) softwareConstraints(component map[string]any, pointer, path string) {
	var linked map[string]any
	if reference, ok := component["package_ref"].(map[string]any); ok {
		linked = m.linkedPackage(reference)
		if linked == nil {
			return
		}
	}
	for _, field := range []string{termVersion, "package_version", "package_name", "package_manager"} {
		rules := m.softwareLeafRules(component, linked, field, path)
		if len(rules) == 0 {
			continue
		}
		rule, origin := softwareLeafConstraint(rules)
		fragment, err := m.concern.input.valueFragment(rule)
		if err != nil {
			m.err = err
			return
		}
		childPointer := metadataPointer(pointer, field)
		m.metadata.LeafConstraints[childPointer] = fragment
		m.metadata.Origins[childPointer] = origin
		delete(m.optional, childPointer)
	}
}

func (m *concernMetadata) softwareLeafRules(component, linked map[string]any, field, path string) []any {
	domain := component[field+"_constraint"]
	if field != termVersion && field != "package_version" {
		domain = nil
	}
	implied := linked != nil && field != termVersion
	if domain == nil && !implied {
		return nil
	}
	rules := []any{}
	if _, authored := m.concern.input.explicitness[path+"."+field]; authored {
		rules = append(rules, map[string]any{termKind: termLiteral, termValue: component[field], termPresence: termRequired, termOrigin: termAuthor})
	}
	if domain != nil {
		rules = append(rules, map[string]any{termKind: termDomain, termDomain: domain, termPresence: termRequired, termOrigin: termAuthor})
	}
	if implied {
		key := field[len("package_"):]
		rules = append(rules, map[string]any{termKind: termLiteral, termValue: linked[key], termPresence: termRequired, termOrigin: termProcessor})
	}
	return rules
}
func softwareLeafConstraint(rules []any) (any, string) {
	rule := rules[0]
	origin := termAuthor
	if len(rules) > 1 {
		rule = map[string]any{termKind: "all-of", "constraints": rules, termPresence: termRequired, termOrigin: termAuthor}
	} else {
		origin = ownedProjection[string](ownedProjection[map[string]any](rules[0])[termOrigin])
	}
	return rule, origin
}
