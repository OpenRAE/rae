package admission

import (
	"math/big"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (r *materializationInventory) capabilities() error {
	envelope, err := r.execution.owner.flowAdmittedDocument(termRealizationEnvelopeV1, r.context.MaterializationEnvelope())
	if err != nil {
		return err
	}
	pin := at(r.execution.manifest, "realization_envelope")
	if !matchingFields(pin, envelope, "contract_id", termSchemaVersion, "digest") || !equal(at(pin, "envelope_id"), at(envelope, "id")) || !equal(at(pin, "configuration_digest"), at(envelope, termConfiguration, "configuration_digest")) {
		return invalid()
	}
	r.envelope = envelope
	live := materializationScope(r.entries, "provisioning")
	available, edges, total, err := materializationCapabilityInventory(live)
	if err != nil {
		return err
	}
	if graph.HasCycle(edges) {
		return invalid()
	}
	provisioner := at(r.execution.manifest, "capabilities", "provisioner")
	if provisioner == nil {
		return invalid()
	}
	if upperBound := at(provisioner, "max_total_nodes"); upperBound != nil {
		upper, ok := number(upperBound)
		if !ok || total.Cmp(upper) > 0 {
			return invalid()
		}
	}
	for address, entry := range live {
		if err := r.capabilityEntry(address, entry, provisioner, available, live); err != nil {
			return err
		}
	}
	return nil
}
func materializationNodeCapabilities(entry, provisioner any) error {
	payload := at(entry, "payload")
	if !set(at(provisioner, "supported_node_types"))[stringAt(payload, "node_kind")] {
		return invalid()
	}
	if len(array(at(payload, "spec", "infrastructure", "acls"))) > 0 && !boolean(at(provisioner, "supports_acls")) {
		return invalid()
	}
	if stringAt(entry, "resource_type") == termNetwork {
		return nil
	}
	for field, supported := range map[string]string{termOsFamily: "supported_os_families", termArchitecture: "supported_node_architectures"} {
		if selected := stringAt(payload, field); selected != "" && !set(at(provisioner, supported))[selected] {
			return invalid()
		}
	}
	return nil
}
func (r *materializationInventory) addedNode(entry any, available, live map[string]any) error {
	if !subset(stringsOf(at(entry, "ordering_dependencies")), keySet(live)) || !subset(stringsOf(at(entry, termRefreshDependencies)), keySet(live)) {
		return invalid()
	}
	payload := at(entry, "payload")
	name := stringAt(payload, "name")
	node, err := r.execution.normalizedNode(name, at(payload, "spec", termNode), nil)
	if err != nil {
		return err
	}
	if err = materializationNodeIdentity(entry, node); err != nil {
		return err
	}
	if err = materializationNodeReferences(entry, node, available); err != nil {
		return err
	}
	for _, raw := range r.execution.current.prepared[stringAt(entry, "address")] {
		requirement, parseErr := materializationJSON(raw)
		if parseErr != nil {
			return parseErr
		}
		if stringAt(requirement, "address") != stringAt(entry, "address") {
			return invalid()
		}
		if err = r.preparedSupport(requirement); err != nil {
			return err
		}
	}
	return materializationOfferIn(at(payload, "spec", termNode), "nodes."+name, r.execution.current.presence[name], at(r.envelope, "expression"))
}
func materializationNodeIdentity(entry, node any) error {
	payload, spec := at(entry, "payload"), at(entry, "payload", "spec")
	if !equalSet(keySet(spec), map[string]bool{termNode: true, "infrastructure": true}) {
		return invalid()
	}
	kind := stringAt(node, "type")
	prefix := "provision.node."
	resourceType := termNode
	if kind == "switch" {
		prefix, resourceType = "provision.network.", termNetwork
	}
	name := stringAt(payload, "name")
	if stringAt(payload, "node_name") != name || stringAt(entry, "address") != prefix+name || stringAt(entry, "resource_type") != resourceType || stringAt(payload, "node_kind") != kind {
		return invalid()
	}
	for _, field := range []string{"features", "conditions", "injects", "roles"} {
		if len(object(at(node, field))) > 0 {
			return invalid()
		}
	}
	if resourceType == termNetwork {
		return nil
	}
	return materializationComputeIdentity(payload, node, spec, name)
}

func materializationComputeIdentity(payload, node, spec any, name string) error {
	if at(payload, "domain_topology") != nil || !equal(at(payload, "count"), at(spec, "infrastructure", "count")) {
		return invalid()
	}
	if count := at(payload, "count"); count != nil {
		n, ok := number(count)
		if !ok || !n.IsInt() || n.Sign() <= 0 {
			return invalid()
		}
	}
	for field, source := range map[string]string{termOsFamily: "os", termOsDistribution: termOsDistribution, termOsVersion: termOsVersion, termArchitecture: termArchitecture} {
		if stringAt(payload, field) != stringAt(node, source) {
			return invalid()
		}
	}
	allowed := map[string]bool{"name": true, "spec": true, "node_name": true, "node_kind": true, termOsFamily: true, termOsDistribution: true, termOsVersion: true, termArchitecture: true, "count": true, "network_namespace_target": true, "domain_topology": true}
	return require(subset(mapKeys(payload), allowed) && !strings.Contains(name, "${"))
}

func materializationCapabilityInventory(live map[string]any) (map[string]any, map[string][]string, *big.Rat, error) {
	available, edges := map[string]any{}, map[string][]string{}
	total := big.NewRat(0, 1)
	for address, entry := range live {
		edges[address] = append(stringsOf(at(entry, "ordering_dependencies")), stringsOf(at(entry, termRefreshDependencies))...)
		kind := stringAt(entry, "resource_type")
		if kind != termNode && kind != termNetwork {
			continue
		}
		name := stringAt(entry, "payload", "name")
		if name == "" || available[name] != nil {
			return nil, nil, nil, invalid()
		}
		available[name] = entry
		count := defaultMember(at(entry, "payload", "spec", "infrastructure"), "count", jsonOne)
		if n, ok := number(count); ok {
			total.Add(total, n)
		}
	}
	return available, edges, total, nil
}

func (r *materializationInventory) capabilityEntry(address string, entry, provisioner any, available, live map[string]any) error {
	kind := stringAt(entry, "resource_type")
	if kind != termNode && kind != termNetwork {
		return nil
	}
	if err := materializationNodeCapabilities(entry, provisioner); err != nil {
		return err
	}
	if r.originals[address] != nil {
		return nil
	}
	if err := r.addedNode(entry, available, live); err != nil {
		return err
	}

	return nil
}
