package authoring

import (
	"encoding/json"
	"math/big"
	"strings"
)

func (w *normalizer) modelCheck(pointer string, value map[string]any) error {
	model := strings.TrimPrefix(pointer, "#/$defs/")
	if err := artifactModel(model, value); err != nil {
		return err
	}
	switch model {
	case scriptModelName:
		return scriptModel(value)
	case "Variable":
		return variableModel(value)
	case "Inject":
		if populated(value["from_entity"]) != populated(value["to_entities"]) {
			return invalid()
		}
	case "Node":
		return nodeModel(value)
	case "InfraNode":
		return infrastructureModel(value)
	case "SimpleProperties":
		return networkModel(value)
	case "ModuleDescriptor":
		return moduleModel(value)
	case "ImportDecl":
		if _, err := versionSpec(text(value["version"])); err != nil {
			return err
		}
		if (text(value[sourceField]) == "") == (text(value["path"]) == "") || !localIdentifier(text(value[namespaceField])) {
			return invalid()
		}
	case "Scenario", "MaterializedScenario":
		return nil
	}
	return nil
}
func nodeModel(value map[string]any) error {
	if strings.EqualFold(text(value["type"]), "switch") {
		if err := switchModel(value); err != nil {
			return err
		}
	}
	names := map[string]bool{}
	ports := map[string]bool{}
	for _, raw := range array(value["services"]) {
		row := object(raw)
		name := text(row[nameField])
		if name != "" && names[name] {
			return invalid()
		}
		names[name] = true
		key, err := servicePortKey(row)
		if err != nil {
			return err
		}
		if key == "" {
			continue
		}
		if ports[key] {
			return invalid()
		}
		ports[key] = true
	}
	return nil
}
func servicePortKey(row map[string]any) (string, error) {
	if variable(row["port"]) || variable(row["protocol"]) {
		return "", nil
	}
	port, err := normalizeInteger(row["port"], true)
	if err != nil {
		return "", err
	}
	protocol := text(row["protocol"])
	if protocol == "" {
		protocol = "tcp"
	}
	return lower(protocol) + ":" + stringNumber(port), nil
}
func switchModel(value map[string]any) error {
	for _, key := range []string{sourceField, "resources", "os", "os_distribution", architectureField, "asset_value", "endpoint_persona", "runtime"} {
		if value[key] != nil {
			return invalid()
		}
	}
	for _, key := range []string{"os_version", featuresSection, conditionsSection, injectsSection, "roles", "services"} {
		if populated(value[key]) {
			return invalid()
		}
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
	case ordered:
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
		if !uniqueStrings(array(value[key])) {
			return invalid()
		}
	}
	names := map[string]bool{}
	for _, raw := range array(value["acls"]) {
		name := text(object(raw)[nameField])
		if name != "" && names[name] {
			return invalid()
		}
		names[name] = true
	}
	return nil
}
func uniqueStrings(values []any) bool {
	seen := map[string]bool{}
	for _, value := range values {
		s, ok := value.(string)
		if !ok {
			return false
		}
		if seen[s] {
			return false
		}
		seen[s] = true
	}
	return true
}
func moduleModel(value map[string]any) error {
	parts := strings.Split(text(value["id"]), "/")
	if len(parts) != 2 || !localIdentifier(parts[0]) || !localIdentifier(parts[1]) {
		return invalid()
	}
	if !uniqueStrings(array(value["parameters"])) {
		return invalid()
	}
	for _, names := range object(value["exports"]) {
		if !uniqueStrings(array(names)) {
			return invalid()
		}
	}
	return nil
}
func (w *normalizer) fieldInput(pointer, name string, value any) (any, error) {
	model := strings.TrimPrefix(pointer, "#/$defs/")
	if bound, ok := integerBound(model, name); ok && !variable(value) {
		return boundedInteger(value, bound)
	}
	switch model {
	case scriptModelName:
		return scriptInput(name, value)
	case "Story":
		if name == "speed" && !variable(value) {
			return speed(value, model)
		}
	case "Resources":
		if name == "ram" {
			return ram(value)
		}
	case "Node":
		return nodeInput(name, value)
	}
	return structuredInput(model, name, value)
}
func scriptInput(name string, value any) (any, error) {
	switch name {
	case "start_time", "end_time":
		return duration(value)
	case "events":
		return eventDurations(value)
	case "speed":
		if !variable(value) {
			return speed(value, scriptModelName)
		}
	}
	return value, nil
}
func nodeInput(name string, value any) (any, error) {
	switch name {
	case architectureField:
		return architecture(value), nil
	case "os_distribution":
		if s, ok := value.(string); ok && !variable(value) {
			return lower(s), nil
		}
	}
	return value, nil
}
func boundedInteger(value any, bound integerRange) (any, error) {
	parsed, err := normalizeInteger(value, true)
	if err != nil {
		return nil, err
	}
	n, ok := parsed.(json.Number)
	if !ok {
		return nil, invalid()
	}
	number, valid := new(big.Int).SetString(n.String(), 10)
	if !valid || number.Cmp(big.NewInt(bound.minimum)) < 0 || bound.maximum > 0 && number.Cmp(big.NewInt(bound.maximum)) > 0 {
		return nil, invalid()
	}
	return parsed, nil
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
	s = lower(s)
	aliases := map[string]string{"amd64": architectureX86, "x64": architectureX86, "x86-64": architectureX86, "arm64": "aarch64"}
	if canonical, ok := aliases[s]; ok {
		return canonical
	}
	return s
}

func eventDurations(value any) (any, error) {
	events := object(value)
	if events == nil {
		return value, nil
	}
	result := map[string]any{}
	for name, value := range events {
		parsed, err := duration(value)
		if err != nil {
			return nil, err
		}
		result[name] = parsed
	}
	return result, nil
}
func speed(value any, model string) (any, error) {
	parsed, err := normalizeFloat(value)
	if err != nil {
		return nil, err
	}
	n, ok := parsed.(json.Number)
	if !ok {
		return nil, invalid()
	}
	f, err := n.Float64()
	if err != nil || model == scriptModelName && f <= 0 || model == "Story" && f < 1 {
		return nil, invalid()
	}
	return parsed, nil
}
func variableModel(value map[string]any) error {
	kind := lower(text(value["type"]))
	if v := value["default"]; v != nil && (!variableType(v, kind) || !allowedValue(v, array(value["allowed_values"]))) {
		return invalid()
	}
	for _, v := range array(value["allowed_values"]) {
		if !variableType(v, kind) {
			return invalid()
		}
	}
	return nil
}

func scriptModel(value map[string]any) error {
	start, err := duration(value["start_time"])
	if err != nil {
		return err
	}
	end, err := duration(value["end_time"])
	if err != nil {
		return err
	}
	lower, lOK := start.(json.Number)
	upper, uOK := end.(json.Number)
	if !lOK || !uOK {
		return nil
	}
	minimum, mOK := new(big.Int).SetString(lower.String(), 10)
	maximum, xOK := new(big.Int).SetString(upper.String(), 10)
	if !mOK || !xOK || minimum.Cmp(maximum) > 0 {
		return invalid()
	}
	for _, raw := range object(value["events"]) {
		parsed, err := duration(raw)
		if err != nil {
			return err
		}
		if n, ok := parsed.(json.Number); ok {
			number, valid := new(big.Int).SetString(n.String(), 10)
			if !valid || number.Cmp(minimum) < 0 || number.Cmp(maximum) > 0 {
				return invalid()
			}
		}
	}
	return nil
}
