package admission

import "strings"

func materializationNodeReferences(entry, node any, available map[string]any) error {
	required := map[string]bool{}
	infra := at(entry, "payload", "spec", "infrastructure")
	for _, field := range []string{"dependencies", "links"} {
		for _, reference := range stringsOf(at(infra, field)) {
			target := available[reference]
			if target == nil || field == "links" && stringAt(target, "resource_type") != termNetwork {
				return invalid()
			}
			required[stringAt(target, "address")] = true
		}
	}

	target := strings.TrimPrefix(stringAt(node, "runtime", "container", "namespaces", termNetwork, "target_node_ref"), "nodes.")
	if target != "" {
		resource := available[target]
		if resource == nil || stringAt(resource, "resource_type") != termNode || stringAt(entry, "payload", "network_namespace_target") != stringAt(resource, "address") {
			return invalid()
		}
		required[stringAt(resource, "address")] = true
	} else if stringAt(entry, "resource_type") == termNode && stringAt(entry, "payload", "network_namespace_target") != "" {
		return invalid()
	}
	return require(subsetSet(required, set(at(entry, "ordering_dependencies"))) && subsetSet(required, set(at(entry, termRefreshDependencies))))
}
