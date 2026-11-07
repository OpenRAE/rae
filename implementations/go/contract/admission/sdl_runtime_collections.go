package admission

import "strings"

func sdlApplicationRoute(v any) error {
	if !sdlSymbolField(v, "route_id") || !sdlURLPath(stringAt(v, "path"), false) {
		return invalid()
	}
	parameters := array(at(v, "parameters"))
	return require(len(rowTupleSet(parameters, "location", termName)) == len(parameters) && fieldsUnique(v, "templates", "static_assets"))
}
func sdlApplicationSurface(v any) error {
	if !sdlSymbolField(v, "application_id") || !sdlURLPath(stringAt(v, "base_path"), true) || !sdlUniqueKey(at(v, "routes"), "route_id", false) {
		return invalid()
	}
	seen := map[string]bool{}
	for _, route := range array(at(v, "routes")) {
		path := stringAt(route, "path")
		for _, method := range stringsOf(at(route, "methods")) {
			if variableRef(path) || variableRef(method) {
				continue
			}
			key := join(method, path)
			if seen[key] {
				return invalid()
			}
			seen[key] = true
		}
	}
	return nil
}
func sdlNetworkRealization(v any) error {
	if !sdlUniqueKey(at(v, "endpoints"), "network", false) {
		return invalid()
	}
	seen := map[[3]string]bool{}
	for _, binding := range array(at(v, "published_ports")) {
		port := at(binding, "host_port")
		if port == nil {
			continue
		}
		key := [3]string{stringAt(binding, "host_ip"), sdlScalarIdentity(port), text(defaultMember(binding, "protocol", "tcp"))}
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
func sdlScalarIdentity(v any) string {
	if n, ok := number(v); ok {
		return "n:" + n.RatString()
	}
	return "s:" + text(v)
}
func sdlContainerConfiguration(v any) error {
	if !sdlAbsoluteList(v, "masked_paths", "read_only_paths") {
		return invalid()
	}
	devices := array(at(v, "devices"))
	if len(rowTupleSet(devices, "host_path", "container_path")) != len(devices) || !sdlUniqueKey(at(v, "extra_hosts"), "hostname", false) {
		return invalid()
	}
	options := stringsOf(at(v, "security_opt"))
	if !unique(options) {
		return invalid()
	}
	profiles := map[string]bool{}
	addProfile := func(value string) {
		if value != "" && !variableRef(value) {
			profiles[value] = true
		}
	}
	addProfile(stringAt(v, "seccomp_profile"))
	for _, option := range options {
		if sdlBlank(option) {
			return invalid()
		}
		if len(option) > 8 && strings.EqualFold(option[:7], "seccomp") && (option[7] == ':' || option[7] == '=') {
			// Python's dot does not match LF. Strip only the matched first line.
			value, _, _ := strings.Cut(option[8:], "\n")
			addProfile(strings.TrimFunc(value, sdlWhitespace))
		}
	}
	return require(len(profiles) <= 1)
}
func sdlIdentityInventory(v any) error {
	if !sdlUniqueKey(at(v, "users"), "username", false) || !sdlUniqueKey(at(v, "groups"), termName, false) {
		return invalid()
	}
	gids := map[string]bool{}
	for _, group := range array(at(v, "groups")) {
		gid := at(group, "gid")
		if gid == nil || variableRef(text(gid)) {
			continue
		}
		key := sdlScalarIdentity(gid)
		if gids[key] {
			return invalid()
		}
		gids[key] = true
	}
	seen := map[string]bool{}
	for _, rule := range array(at(v, "sudo_rules")) {
		key := join(text(defaultMember(rule, "principal_kind", termUser)), stringAt(rule, "principal"), join(stringsOf(at(rule, "commands"))...))
		if seen[key] {
			return invalid()
		}
		seen[key] = true
	}
	return nil
}
