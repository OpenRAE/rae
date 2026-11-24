package admission

import "strings"

func absoluteSDLPath(value string, empty bool) bool {
	return empty && value == "" || strings.HasPrefix(value, "/") || variableRef(value)
}
func imageEnvironmentName(v any) error {
	name := stringAt(v, termName)
	return require(!sdlBlank(name) && !strings.Contains(name, "="))
}
func imageConfigShape(v any) error {
	entries := array(at(v, "default_environment"))
	return require(absoluteSDLPath(stringAt(v, termWorkingDirectory), true) && len(rowTupleSet(entries, termName)) == len(entries))
}
func imageBuildShape(v any) error {
	for field, key := range map[string]string{"build_args": termName, "source_inputs": "identifier"} {
		entries := array(at(v, field))
		if len(rowTupleSet(entries, key)) != len(entries) {
			return invalid()
		}
	}
	return nil
}
func imageSourceInput(v any) error {
	return require(!sdlBlank(stringAt(v, "identifier")) && absoluteSDLPath(stringAt(v, "destination_path"), true) && (stringAt(v, "checksum") == "") == (stringAt(v, "checksum_algorithm") == ""))
}
func imageCopiedSource(v any) error {
	return require(!sdlBlank(stringAt(v, "source_path")) && absoluteSDLPath(stringAt(v, "destination_path"), false))
}
