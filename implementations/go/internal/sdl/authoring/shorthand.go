package authoring

import (
	"encoding/json"
	"sort"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

func shorthands(value map[string]any) error {
	for key, item := range object(value["infrastructure"]) {
		if _, ok := item.(json.Number); ok || variable(item) {
			object(value["infrastructure"])[key] = map[string]any{"count": item}
		}
	}
	for _, item := range object(value["nodes"]) {
		node := object(item)
		for name, role := range object(node["roles"]) {
			if s, ok := role.(string); ok {
				object(node["roles"])[name] = map[string]any{"username": s}
			}
		}
		for _, key := range []string{"features", "conditions", "injects"} {
			if names, ok := node[key].([]any); ok {
				mapped := map[string]any{}
				for _, name := range names {
					s, ok := name.(string)
					if !ok {
						return invalid()
					}
					mapped[s] = ""
				}
				node[key] = mapped
			}
		}
	}
	return nil
}
func migrateVM(value map[string]any, document *source.Document, policy, name string) ([]source.Diagnostic, error) {
	realization := object(value["realization"])
	for _, raw := range array(realization["constraints"]) {
		if _, present := object(raw)["provenance"]; present {
			return nil, invalid()
		}
	}
	nodes := object(value["nodes"])
	names := make([]string, 0)
	for key, raw := range nodes {
		if strings.EqualFold(text(object(raw)["type"]), "vm") {
			names = append(names, key)
		}
	}
	ranges := document.Ranges()
	sort.Slice(names, func(i, j int) bool {
		a, b := ranges["/nodes/"+jsonpointer.EscapeToken(names[i])], ranges["/nodes/"+jsonpointer.EscapeToken(names[j])]
		if a.Start.Line != b.Start.Line {
			return a.Start.Line < b.Start.Line
		}
		return a.Start.Column < b.Start.Column
	})
	var warnings []source.Diagnostic
	for _, key := range names {
		if policy != "accept" {
			return nil, invalid()
		}
		if realization == nil {
			if value["realization"] != nil {
				return nil, invalid()
			}
			realization = map[string]any{}
			value["realization"] = realization
		}
		pointer := "/nodes/" + jsonpointer.EscapeToken(key)
		for _, raw := range array(realization["constraints"]) {
			constraint := object(raw)
			if constraint["field_pointer"] == pointer && constraint["concern"] == "compute-substrate" && len(array(constraint["namespace"])) == 0 {
				return nil, invalid()
			}
		}
		if _, ok := realization["constraints"].([]any); realization["constraints"] != nil && !ok {
			return nil, invalid()
		}
		realization["constraints"] = append(array(realization["constraints"]), map[string]any{"field_pointer": pointer, "concern": "compute-substrate", "posture": "exact", "domain": map[string]any{"kind": "exact", "value": "virtual-machine"}})
		object(nodes[key])["type"] = "compute"
		span, ok := ranges[pointer+"/type"]
		if !ok {
			span = source.Range{Start: source.Position{Line: 1, Column: 1}, End: source.Position{Line: 1, Column: 1}}
		}
		warnings = append(warnings, source.Diagnostic{Code: "sdl.legacy_node_type_vm", Pointer: pointer + "/type", Range: span, Severity: "warning", Source: name})
	}
	return warnings, nil
}
