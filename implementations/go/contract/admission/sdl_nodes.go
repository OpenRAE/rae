package admission

import (
	"strings"
	"unicode"

	"golang.org/x/text/cases"
	"golang.org/x/text/language"
)

func sdlServicePort(v any) error {
	port := at(v, "port")
	if variableRef(text(port)) {
		return nil
	}
	n, ok := integer(port)
	return require(ok && n >= 1 && n <= 65535)
}
func sdlNode(v any) error {
	if stringAt(v, "type") == termSwitch {
		return sdlSwitch(v)
	}
	state := sdlServiceSet{names: map[string]bool{}, bindings: map[[2]string]bool{}, protocols: map[string]string{}}
	for _, service := range array(at(v, "services")) {
		if err := state.add(service); err != nil {
			return err
		}
	}
	return nil
}

type sdlServiceSet struct {
	names     map[string]bool
	bindings  map[[2]string]bool
	protocols map[string]string
}

func (state *sdlServiceSet) add(service any) error {
	name := stringAt(service, termName)
	if name != "" && state.names[name] {
		return invalid()
	}
	state.names[name] = true
	if variableRef(stringAt(service, "port")) || variableRef(stringAt(service, "protocol")) {
		return nil
	}
	port, ok := number(at(service, "port"))
	if !ok || !port.IsInt() {
		return invalid()
	}
	protocol := text(defaultMember(service, "protocol", "tcp"))
	normalized, present := state.protocols[protocol]
	if !present {
		normalized = sdlProtocol(protocol)
		state.protocols[protocol] = normalized
	}
	key := [2]string{normalized, port.RatString()}
	if state.bindings[key] {
		return invalid()
	}
	state.bindings[key] = true
	return nil
}

func sdlProtocol(value string) string {
	if strings.IndexFunc(value, func(r rune) bool { return r > unicode.MaxASCII }) < 0 {
		return strings.ToLower(value)
	}
	return cases.Lower(language.Und).String(value)
}
func sdlSwitch(v any) error {
	for _, field := range []string{termSource, "resources", "os", "os_distribution", "architecture", "asset_value", "endpoint_persona", "runtime"} {
		if at(v, field) != nil {
			return invalid()
		}
	}
	if stringAt(v, "os_version") != "" {
		return invalid()
	}
	for _, field := range []string{"features", "conditions", "injects", termRoles} {
		if len(object(at(v, field))) > 0 {
			return invalid()
		}
	}
	return require(len(array(at(v, "services"))) == 0)
}
func sdlInfrastructure(v any) error {
	if !fieldsUnique(v, "links", "dependencies") {
		return invalid()
	}
	names := map[string]bool{}
	for _, rule := range array(at(v, "acls")) {
		name := stringAt(rule, termName)
		if name != "" && names[name] {
			return invalid()
		}
		names[name] = true
	}
	return nil
}
