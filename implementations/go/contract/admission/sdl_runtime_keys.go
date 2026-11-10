package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/sdlrules"

func sdlUniqueKey(rows any, field string, skipEmpty bool) bool {
	seen := map[string]bool{}
	for _, row := range array(rows) {
		value := at(row, field)
		if skipEmpty && (value == nil || value == "") {
			continue
		}
		key := "s:" + text(value)
		if n, ok := number(value); ok {
			key = "n:" + n.RatString()
		}
		if seen[key] {
			return false
		}
		seen[key] = true
	}
	return true
}
func sdlRuntimeKeys(v any) error {
	for _, family := range sdlrules.RuntimeFamilies() {
		if !sdlUniqueKey(at(v, family.Collection), family.Identity, true) {
			return invalid()
		}
	}
	for _, pair := range [][2]string{
		{termEnvironment, termName}, {"environment_files", termName}, {"mounts", "target"}, {"local_control_interfaces", "control_interface_id"},
		{"filesystem_inventory", "path"}, {"processes", termName}, {"processes", termPID},
		{"service_manager_units", "unit_id"}, {"service_manager_units", "unit_name"}, {"software_components", termComponentID},
	} {
		if !sdlUniqueKey(at(v, pair[0]), pair[1], true) {
			return invalid()
		}
	}
	packages := array(at(v, "packages"))
	if len(rowTupleSet(packages, "manager", termName, termArchitecture)) != len(packages) {
		return invalid()
	}
	return nil
}
