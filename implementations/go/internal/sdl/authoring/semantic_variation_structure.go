package authoring

import (
	"fmt"
	"strings"
)

type semanticConsumerSelector struct {
	Node  string `json:"node"`
	Mount string `json:"mount_destination"`
}

func (m *semanticModel) variationConsumerFacts() {
	m.variationConsumers = map[semanticOwner][]semanticConsumerSelector{}
	for name, resource := range fieldValue(m.transport.PersistentVolumes) {
		for _, consumer := range fieldValue(resource.Consumers) {
			owner := semanticOwner{persistentVolumesField, name}
			m.variationConsumers[owner] = append(m.variationConsumers[owner], semanticConsumerSelector{fieldValue(consumer.Node), fieldValue(consumer.MountDestination)})
		}
	}
	for name, resource := range fieldValue(m.transport.GeneratedArtifacts) {
		for _, consumer := range fieldValue(resource.Consumers) {
			owner := semanticOwner{generatedArtifactsField, name}
			m.variationConsumers[owner] = append(m.variationConsumers[owner], semanticConsumerSelector{fieldValue(consumer.Node), fieldValue(consumer.MountDestination)})
		}
	}
}
func (v semanticVariationCheck) structural() {
	members, names := v.members()
	for _, name := range names {
		if !v.structuralMember(members[name]) {
			v.report(fmt.Sprintf("member '%s' has an invalid structural target or candidate", name))
		}
	}
}
func (m *semanticModel) structuralOwner(ref, section string) (string, bool) {
	name, count := "", 0
	for _, entry := range m.index.aliases[ref] {
		if len(entry.tokens) == 2 && entry.tokens[0] == section {
			name = entry.tokens[1]
			count++
		}
	}
	return name, count == 1
}
func (v semanticVariationCheck) structuralMember(member semanticVariationMember) bool {
	slot := v.point.Target.Slot
	if slot == "nodes.runtime.network_detection_engines.rule_sources" {
		return v.childInventory(member.References)
	}
	section, _, known := strings.Cut(slot, ".")
	if !known {
		return false
	}
	owner, valid := v.model.structuralOwner(v.point.Target.Owner, section)
	if !valid {
		return false
	}
	switch {
	case slot == "nodes.presence":
		for inventory, refs := range member.Inventory {
			if !v.model.inventoryChoice(owner, inventory, refs) {
				return false
			}
		}
		return true
	case runtimeInventorySlot(slot):
		return v.model.inventoryChoice(owner, slot, member.References)
	case declarationPresenceSlot(slot):
		return true
	case slot == "persistent_volumes.consumers" || slot == "generated_artifacts.consumers":
		return v.model.consumerChoice(semanticOwner{section, owner}, member.Consumers)
	default:
		return false
	}
}
func declarationPresenceSlot(slot string) bool {
	switch slot {
	case "accounts.presence", "content.presence", "persistent_volumes.presence", "generated_artifacts.presence", "relationships.presence", "propositions.presence", "assertions.presence", "evidence_requirements.presence":
		return true
	default:
		return false
	}
}
func runtimeInventorySlot(slot string) bool {
	switch slot {
	case "nodes.runtime.service_listeners", "nodes.runtime.applications", "nodes.runtime.database_services", "nodes.runtime.dns_services", "nodes.runtime.identity_authorities", "nodes.runtime.file_services", "nodes.runtime.mail_services", "nodes.runtime.network_sensors", "nodes.runtime.network_detection_engines", "nodes.runtime.security_monitoring_managers", "nodes.runtime.ssh_servers", "nodes.runtime.app_authorizations", "nodes.runtime.scheduled_jobs", "nodes.runtime.datastore_services", "nodes.runtime.platform_applications", "nodes.runtime.forwarding_agents", "nodes.runtime.orchestration_authorities":
		return true
	default:
		return false
	}
}
func (m *semanticModel) inventoryChoice(owner, slot string, refs []string) bool {
	if !runtimeInventorySlot(slot) {
		return false
	}
	node, known := m.nodeIndex[owner]
	if !known || m.nodes[node].runtime == nil {
		return false
	}
	collection := strings.TrimPrefix(slot, "nodes.runtime.")
	for _, ref := range refs {
		entry, present := m.index.declarations[ref]
		if !present || len(entry.tokens) != 6 || entry.node != owner || entry.kind != collection {
			return false
		}
	}
	return true
}
func (v semanticVariationCheck) childInventory(refs []string) bool {
	owner := ""
	count := 0
	for address, entry := range v.model.index.aliases[v.point.Target.Owner] {
		if len(entry.tokens) == 6 && entry.tokens[0] == nodesSection && entry.tokens[2] == runtimeField && entry.tokens[3] == "network_detection_engines" {
			owner = address
			count++
		}
	}
	if count != 1 {
		return false
	}
	for _, ref := range refs {
		entry, known := v.model.index.declarations[ref]
		if !known || entry.parent != owner || entry.kind != "network_detection_engines.rule_sources" {
			return false
		}
	}
	return true
}
func (m *semanticModel) consumerChoice(owner semanticOwner, selectors []semanticConsumerSelector) bool {
	available := map[semanticConsumerSelector]bool{}
	for _, row := range m.variationConsumers[owner] {
		row.Node = strings.TrimPrefix(row.Node, nodesPrefix)
		available[row] = true
	}
	chosen := map[semanticConsumerSelector]bool{}
	for _, row := range selectors {
		row.Node = strings.TrimPrefix(row.Node, nodesPrefix)
		if !m.definitions[nodesSection][row.Node] || chosen[row] || !available[row] {
			return false
		}
		chosen[row] = true
	}
	return true
}
