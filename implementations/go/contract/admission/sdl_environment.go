package admission

import "strings"

func sdlEnvironmentVariable(v any) error {
	if err := imageEnvironmentName(v); err != nil {
		return err
	}
	return require(at(v, "value_from") == nil || stringAt(v, "value") == "" && stringAt(v, "value_classification") != "operator_secret")
}
func sdlWindowsPipe(value string) bool {
	// The prefixes contain only ASCII; full Unicode casing cannot change them.
	const width = len(`\\.\pipe\`)
	if len(value) < width {
		return false
	}
	prefix := strings.ToLower(value[:width])
	return prefix == `\\.\pipe\` || prefix == `\\?\pipe\`
}
func sdlControlPath(value string, optional bool) bool {
	return absoluteSDLPath(value, optional) || sdlWindowsPipe(value)
}
func sdlControlInterface(v any) error {
	path, source := stringAt(v, "path"), stringAt(v, "bind_source")
	if !sdlSymbolField(v, "control_interface_id") || !sdlControlPath(path, false) || !sdlControlPath(source, true) {
		return invalid()
	}
	kind := text(defaultMember(v, termKind, "unix_socket"))
	return require(variableRef(kind) || kind == "named_pipe" || !sdlWindowsPipe(path) && !sdlWindowsPipe(source))
}
