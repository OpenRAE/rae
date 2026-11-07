package authoring

import (
	"encoding/json"
	"strings"
)

func networkNamespace(node map[string]any) map[string]any {
	return object(object(object(object(node["runtime"])["container"])["namespaces"])["network"])
}
func (c materializedChecks) singletonNode(name string) bool {
	count := object(object(c.value[infrastructureField])[name])["count"]
	return count == nil || variable(count) || scalarEqual(count, json.Number("1"))
}
func (c materializedChecks) sharedNetworkNamespace(name string, node map[string]any, namespace map[string]any) error {
	reference := text(namespace["target_node_ref"])
	if variable(reference) {
		return nil
	}
	targetName := strings.TrimPrefix(reference, "nodes.")
	target := object(object(c.value[nodesSection])[targetName])
	if targetName == name || target["type"] != computeType || networkNamespace(target) != nil || !c.singletonNode(name) || !c.singletonNode(targetName) {
		return semanticInvalid()
	}
	infrastructure := object(object(c.value[infrastructureField])[name])
	if len(array(infrastructure["links"])) > 0 || infrastructure["properties"] != nil || len(array(infrastructure["acls"])) > 0 {
		return semanticInvalid()
	}
	network := object(object(node["runtime"])["network"])
	if len(array(network["endpoints"])) > 0 || len(array(network["published_ports"])) > 0 {
		return semanticInvalid()
	}
	return nil
}
func (c materializedChecks) runtimeNetwork() error {
	for name, raw := range object(c.value[nodesSection]) {
		node := object(raw)
		if namespace := networkNamespace(node); namespace != nil {
			if err := c.sharedNetworkNamespace(name, node, namespace); err != nil {
				return err
			}
		}
		network := object(object(node["runtime"])["network"])
		for _, rawEndpoint := range array(network["endpoints"]) {
			endpoint := object(rawEndpoint)
			reference := text(endpoint["network"])
			if err := c.switchReference(reference); err != nil {
				return err
			}
			if err := c.endpointAddresses(reference, endpoint); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c materializedChecks) endpointAddresses(reference string, endpoint map[string]any) error {
	properties := object(object(object(c.value[infrastructureField])[reference])["properties"])
	cidr := text(properties["cidr"])
	if cidr == "" || variable(cidr) {
		return nil
	}
	network, err := networkPrefix(cidr)
	if err != nil {
		return semanticInvalid()
	}
	for _, field := range []string{"ip_address", "gateway"} {
		value := text(endpoint[field])
		if value == "" || variable(value) {
			continue
		}
		address, parseErr := networkAddress(value)
		if parseErr == nil && address.BitLen() == network.Addr().BitLen() && !network.Contains(address.WithZone("")) {
			return semanticInvalid()
		}
	}
	return nil
}
