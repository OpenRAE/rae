package authoring

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func shorthands(value map[string]any, hints map[string][]string) error {
	infrastructure := object(value["infrastructure"])
	for key, item := range infrastructure {
		if _, ok := item.(json.Number); ok || variable(item) {
			infrastructure[key] = map[string]any{"count": item}
		}
	}
	for name, item := range object(value[nodesSection]) {
		if err := nodeShorthands(object(item), name, hints); err != nil {
			return err
		}
	}
	return nil
}
func nodeShorthands(node map[string]any, name string, hints map[string][]string) error {
	roles := object(node["roles"])
	for name, role := range roles {
		if value, ok := role.(string); ok {
			roles[name] = map[string]any{"username": value}
		}
	}
	for _, field := range []string{featuresSection, conditionsSection, injectsSection} {
		if names, ok := node[field].([]any); ok {
			mapped, order, err := namedShorthand(names)
			if err != nil {
				return err
			}
			node[field] = mapped
			hints[jsonpointer.FromTokens([]string{nodesSection, name, field})] = order
		}
	}
	return nil
}
func namedShorthand(names []any) (map[string]any, []string, error) {
	mapped := map[string]any{}
	order := make([]string, 0, len(names))
	for _, raw := range names {
		name, ok := raw.(string)
		if !ok {
			return nil, nil, invalid()
		}
		if _, present := mapped[name]; !present {
			order = append(order, name)
		}
		mapped[name] = ""
	}
	return mapped, order, nil
}
func migrateVM(value map[string]any, document *source.Document, policy, name string) ([]source.Diagnostic, error) {
	for _, raw := range array(object(value["realization"])["constraints"]) {
		if _, present := object(raw)["provenance"]; present {
			return nil, invalid()
		}
	}
	nodes := object(value[nodesSection])
	var warnings []source.Diagnostic
	for _, key := range document.View().Child(nodesSection).Keys() {
		if !strings.EqualFold(text(object(nodes[key])["type"]), "vm") {
			continue
		}
		if policy != "accept" {
			return nil, invalid()
		}
		realization, err := vmRealization(value)
		if err != nil {
			return nil, err
		}
		pointer := "/nodes/" + jsonpointer.EscapeToken(key)
		if err = addVMConstraint(realization, pointer); err != nil {
			return nil, err
		}
		object(nodes[key])["type"] = "compute"
		span, ok := document.View().Child(nodesSection).Child(key).Child("type").Range()
		if !ok {
			span = source.Range{Start: source.Position{Line: 1, Column: 1}, End: source.Position{Line: 1, Column: 1}}
		}
		warnings = append(warnings, source.Diagnostic{Code: "sdl.legacy_node_type_vm", Pointer: pointer + "/type", Range: span, Severity: "warning", Source: name})
	}
	return warnings, nil
}
func vmRealization(value map[string]any) (map[string]any, error) {
	realization := object(value["realization"])
	if realization == nil {
		if _, present := value["realization"]; present {
			return nil, invalid()
		}
		realization = map[string]any{}
		value["realization"] = realization
	}
	if raw, present := realization["constraints"]; present {
		if _, ok := raw.([]any); !ok {
			return nil, invalid()
		}
	}
	return realization, nil
}
func addVMConstraint(realization map[string]any, pointer string) error {
	for _, raw := range array(realization["constraints"]) {
		constraint := object(raw)
		if constraint["field_pointer"] == pointer && constraint["concern"] == "compute-substrate" && len(array(constraint["namespace"])) == 0 {
			return invalid()
		}
	}
	realization["constraints"] = append(array(realization["constraints"]), map[string]any{"field_pointer": pointer, "concern": "compute-substrate", "posture": exactTerm, "domain": map[string]any{"kind": exactTerm, "value": "virtual-machine"}})
	return nil
}
