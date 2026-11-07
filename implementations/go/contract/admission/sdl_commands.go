package admission

import "strings"

func sdlCommand(v any, ssh bool) error {
	kind := text(defaultMember(v, "command_kind", "absolute_path"))
	command := stringAt(v, "command")
	redacted := at(v, "command_redacted")
	kindVar, redactedVar := variableRef(kind), variableRef(text(redacted))
	if redacted == true && (command != "" || !kindVar && kind != termRedacted) {
		return invalid()
	}
	if !kindVar && kind == termRedacted && (command != "" || !redactedVar && redacted != true) {
		return invalid()
	}
	if kindVar || redactedVar || redacted == true {
		return nil
	}
	if kind == "absolute_path" && !absoluteSDLPath(command, false) || ssh && kind == "internal_sftp" && command != "internal-sftp" {
		return invalid()
	}
	return nil
}
func sdlServiceManagerUnit(v any) error {
	result := text(defaultMember(v, termResult, statusUnknown))
	if at(v, "exit_code") != nil && !variableRef(result) && result != "exit_code" {
		return invalid()
	}
	manager := at(v, "manager_kind")
	if manager == nil || variableRef(text(manager)) {
		return nil
	}
	if manager == "systemd" {
		name := stringAt(v, "unit_name")
		return require(name == "" || strings.ContainsRune(name, '.'))
	}
	defaults := map[string]any{"unit_type": termOther, "load_state": statusUnknown, "active_state": statusUnknown, "sub_state": "", "enabled_state": statusUnknown, termResult: statusUnknown, "exit_code": nil, "status_text": "", "main_pid": nil, "exec_start": nil}
	for field, expected := range defaults {
		if value, present := object(v)[field]; present && !equal(value, expected) {
			return invalid()
		}
	}
	return nil
}
func sdlSSHMatch(v any) error {
	criteria := array(at(v, "criteria"))
	return require(len(criteria) > 0 && len(rowTupleSet(criteria, termKind, "pattern")) == len(criteria))
}
func sdlSSHServer(v any) error {
	if !sdlUniqueKey(at(v, "match_rules"), "match_id", false) {
		return invalid()
	}
	seen := map[string]bool{}
	for _, rule := range array(at(v, "match_rules")) {
		parts := []string{}
		for _, criterion := range array(at(rule, "criteria")) {
			parts = append(parts, join(stringAt(criterion, termKind), stringAt(criterion, "pattern")))
		}
		key := join(parts...)
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
