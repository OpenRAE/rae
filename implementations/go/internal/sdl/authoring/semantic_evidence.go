package authoring

import (
	"encoding/json"
	"fmt"
)

type semanticEvidence struct {
	name, sourceClass         string
	sources, scopes, channels []string
	trigger, boundary         string
	demand                    *semanticObservationDemand
}
type semanticObservationDemand struct {
	Scope    string `json:"scope"`
	Selector *struct {
		Excluded   []string `json:"excluded_scopes"`
		Scope      string   `json:"semantic_scope"`
		Components []string `json:"component_refs"`
	} `json:"selector"`
}
type semanticForwarder struct {
	Targets []semanticForwardTarget `json:"ship_targets"`
	ID      string                  `json:"forwarding_agent_id"`
	Role    string                  `json:"ownership_role"`
	address string
	owner   semanticOwner
	node    string
}

func (m *semanticModel) evidenceFacts() error {
	values := fieldValue(m.transport.EvidenceRequirements)
	for _, name := range m.keys(evidenceRequirementsSection) {
		raw := values[name]
		row := semanticEvidence{name: name, sources: fieldValue(raw.SourceRefs), scopes: fieldValue(raw.ScopeRefs), channels: fieldValue(raw.ChannelRefs), trigger: fieldValue(raw.TriggerRef), boundary: fieldValue(raw.BoundaryRef)}
		var err error
		row.sourceClass, err = scalarText(fieldValue(raw.SourceClass), "")
		if err != nil {
			return err
		}
		if raw.ObservationDemand.Present() && !raw.ObservationDemand.Null() {
			if err := json.Unmarshal(fieldValue(raw.ObservationDemand), &row.demand); err != nil {
				return invalid()
			}
		}
		m.evidence = append(m.evidence, row)
	}
	return m.forwarderFacts()
}
func (m *semanticModel) forwarderFacts() error {
	for _, raw := range fieldValue(m.transport.ForwardingAgents) {
		var row semanticForwarder
		if err := json.Unmarshal(raw, &row); err != nil {
			return invalid()
		}
		row.address, row.owner = forwardingSection+"."+row.ID, semanticOwner{forwardingSection, row.ID}
		m.forwarders = append(m.forwarders, row)
	}
	for _, name := range m.keys(nodesSection) {
		raw := fieldValue(fieldValue(m.transport.Nodes)[name].Runtime)
		if len(raw) == 0 || string(raw) == nullType {
			continue
		}
		var runtime struct {
			Forwarders []semanticForwarder `json:"forwarding_agents"`
		}
		if err := json.Unmarshal(raw, &runtime); err != nil {
			return invalid()
		}
		for _, row := range runtime.Forwarders {
			row.node = name
			owner := name + ".runtime." + forwardingSection + "." + row.ID
			row.address, row.owner = nodesSection+"."+owner, semanticOwner{nodesSection, owner}
			m.forwarders = append(m.forwarders, row)
		}
	}
	return nil
}
func (m *semanticModel) checkEvidence(c *semanticCollector) {
	for _, row := range m.evidence {
		owner, label := semanticOwner{evidenceRequirementsSection, row.name}, "Evidence requirement '"+row.name+"'"
		for _, group := range []struct {
			field   string
			refs    []string
			purpose semanticPurpose
		}{
			{"source_ref", row.sources, referenceObservation}, {"scope_ref", row.scopes, referenceObservation}, {"channel_ref", row.channels, referenceTarget}, {"trigger_ref", []string{row.trigger}, referenceTarget}, {"boundary_ref", []string{row.boundary}, referenceTarget},
		} {
			for _, ref := range group.refs {
				if ref != "" {
					m.namedReference(c, owner, label, group.field, ref, group.purpose)
				}
			}
		}
		if row.demand != nil {
			m.checkObservationDemand(c, owner, label, *row.demand)
		}
	}
	m.checkForwardingEvidenceRoles(c)
}
func (m *semanticModel) checkObservationScope(c *semanticCollector, owner semanticOwner, label, field, pointer string) {
	if _, err := m.scopes.resolve(pointer); err != nil {
		c.report(owner, fmt.Sprintf("%s %s '%s' does not resolve to a stable SDL semantic scope", label, field, pointer))
	}
}
func (m *semanticModel) checkObservationDemand(c *semanticCollector, owner semanticOwner, label string, demand semanticObservationDemand) {
	m.checkObservationScope(c, owner, label, "observation_demand.scope", demand.Scope)
	if demand.Selector == nil {
		return
	}
	for _, pointer := range demand.Selector.Excluded {
		m.checkObservationScope(c, owner, label, "observation_demand.selector.exclusion", pointer)
	}
	m.checkObservationScope(c, owner, label, "observation_demand.selector.semantic_scope", demand.Selector.Scope)
	for _, ref := range demand.Selector.Components {
		if ref != "" {
			m.namedReference(c, owner, label, "observation_demand.selector.component_ref", ref, referenceObservation)
		}
	}
}
func (m *semanticModel) checkForwardingEvidenceRoles(c *semanticCollector) {
	bound := map[string]bool{}
	for _, row := range m.evidence {
		if row.sourceClass != "apparatus" {
			continue
		}
		for _, ref := range row.sources {
			for address := range m.index.aliases[ref] {
				bound[address] = true
			}
		}
	}
	for _, row := range m.forwarders {
		switch {
		case row.Role == "measurement_apparatus" && !bound[row.address]:
			c.report(row.owner, fmt.Sprintf("Forwarding agent '%s' ownership_role 'measurement_apparatus' requires an inbound EvidenceRequirement.source_refs binding with source_class 'apparatus'", row.address))
		case (row.Role == "system_under_test" || row.Role == "") && bound[row.address]:
			c.report(row.owner, fmt.Sprintf("Forwarding agent '%s' ownership_role 'system_under_test' cannot be targeted by an evidence requirement with source_class 'apparatus'", row.address))
		}
	}
}
