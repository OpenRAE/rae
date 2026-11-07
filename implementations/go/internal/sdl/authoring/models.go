package authoring

import (
	"encoding/json"
	"net/netip"
	"strings"
)

func (w *normalizer) modelInput(pointer string, value map[string]any) error {
	switch strings.TrimPrefix(pointer, "#/$defs/") {
	case "Node":
		return nodeModel(value)
	case "InfraNode":
		return infrastructureModel(value)
	case "SimpleProperties":
		return networkModel(value)
	case "ModuleDescriptor":
		return moduleModel(value)
	case "ImportDecl":
		if (text(value["source"]) == "") == (text(value["path"]) == "") || text(value["namespace"]) == "" {
			return invalid()
		}
	case "Scenario", "MaterializedScenario":
		return nil
	}
	return nil
}
func nodeModel(value map[string]any) error {
	if strings.EqualFold(text(value["type"]), "switch") {
		for _, key := range []string{"source", "resources", "os", "os_distribution", "os_version", "architecture", "features", "conditions", "injects", "roles", "services", "asset_value", "endpoint_persona", "runtime"} {
			if populated(value[key]) {
				return invalid()
			}
		}
	}
	names := map[string]bool{}
	ports := map[string]bool{}
	for _, raw := range array(value["services"]) {
		row := object(raw)
		name := text(row["name"])
		if name != "" && names[name] {
			return invalid()
		}
		names[name] = true
		if variable(row["port"]) || variable(row["protocol"]) {
			continue
		}
		port, err := normalizeInteger(row["port"], true)
		if err != nil {
			return err
		}
		protocol := text(row["protocol"])
		if protocol == "" {
			protocol = "tcp"
		}
		key := strings.ToLower(protocol) + ":" + stringNumber(port)
		if ports[key] {
			return invalid()
		}
		ports[key] = true
	}
	return nil
}
func populated(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case string:
		return v != ""
	case []any:
		return len(v) > 0
	case map[string]any:
		return len(v) > 0
	default:
		return true
	}
}
func stringNumber(value any) string {
	if n, ok := value.(json.Number); ok {
		return n.String()
	}
	return ""
}
func infrastructureModel(value map[string]any) error {
	for _, key := range []string{"links", "dependencies"} {
		if !uniqueStrings(array(value[key]), false) {
			return invalid()
		}
	}
	names := map[string]bool{}
	for _, raw := range array(value["acls"]) {
		name := text(object(raw)["name"])
		if name != "" && names[name] {
			return invalid()
		}
		names[name] = true
	}
	return nil
}
func uniqueStrings(values []any, ignoreBlank bool) bool {
	seen := map[string]bool{}
	for _, value := range values {
		s, ok := value.(string)
		if !ok {
			return false
		}
		if ignoreBlank && s == "" {
			continue
		}
		if seen[s] {
			return false
		}
		seen[s] = true
	}
	return true
}
func networkModel(value map[string]any) error {
	if variable(value["cidr"]) || variable(value["gateway"]) {
		return nil
	}
	network, err := netip.ParsePrefix(text(value["cidr"]))
	if err != nil {
		address, parseErr := netip.ParseAddr(text(value["cidr"]))
		if parseErr != nil {
			return invalid()
		}
		network = netip.PrefixFrom(address, address.BitLen())
	}
	gateway, err := netip.ParseAddr(text(value["gateway"]))
	if err != nil || !network.Contains(gateway) {
		return invalid()
	}
	return nil
}
func moduleModel(value map[string]any) error {
	if !uniqueStrings(array(value["parameters"]), false) {
		return invalid()
	}
	for _, names := range object(value["exports"]) {
		if !uniqueStrings(array(names), false) {
			return invalid()
		}
	}
	return nil
}
func (w *normalizer) fieldInput(pointer, name string, value any) (any, error) {
	model := strings.TrimPrefix(pointer, "#/$defs/")
	if model == "Resources" && name == "ram" {
		return ram(value)
	}
	if bound, ok := integerBound(model, name); ok && !variable(value) {
		parsed, err := normalizeInteger(value, true)
		if err != nil {
			return nil, err
		}
		n, ok := parsed.(json.Number)
		if !ok {
			return nil, invalid()
		}
		number, err := n.Int64()
		if err != nil {
			if bound.maximum > 0 {
				return nil, invalid()
			}
			return parsed, nil
		}
		if number < bound.minimum || bound.maximum > 0 && number > bound.maximum {
			return nil, invalid()
		}
		return parsed, nil
	}
	if model == "Node" {
		if name == "architecture" {
			return architecture(value), nil
		}
		if name == "os_distribution" {
			if s, ok := value.(string); ok && !variable(value) {
				return strings.ToLower(s), nil
			}
		}
	}
	if model == "ImportDecl" && name == "path" && text(value) != "" {
		return value, nil
	}
	return value, nil
}

type integerRange struct{ minimum, maximum int64 }

func integerBound(model, name string) (integerRange, bool) {
	switch model + "/" + name {
	case "Resources/cpu", "InfraNode/count":
		return integerRange{minimum: 1}, true
	case "ServicePort/port":
		return integerRange{minimum: 1, maximum: 65535}, true
	}
	return integerRange{}, false
}
func architecture(value any) any {
	s, ok := value.(string)
	if !ok || variable(value) {
		return value
	}
	s = strings.ToLower(s)
	aliases := map[string]string{"amd64": "x86_64", "x64": "x86_64", "x86-64": "x86_64", "arm64": "aarch64"}
	if canonical, ok := aliases[s]; ok {
		return canonical
	}
	return s
}
