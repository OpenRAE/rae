package authoring

import (
	"fmt"
	"slices"
	"strings"
)

func (m *semanticModel) checkEnterpriseIdentity(c *semanticCollector) {
	m.checkForestMemberships(c)
	facades := fieldValue(m.transport.IdentityFacades)
	for _, name := range m.keys(identityFacadesField) {
		ref := fieldValue(facades[name].ServiceRef)
		if !variable(ref) && !m.namedService(ref) {
			c.report(semanticOwner{identityFacadesField, name}, fmt.Sprintf("Identity facade '%s' service_ref '%s' does not resolve to a named compute service", name, ref))
		}
	}
	values := fieldValue(m.transport.Relationships)
	for _, row := range m.relationships {
		raw := values[row.name]
		checkEnterpriseDetails(c, row.name, row.kind, raw.ForestTrust.Present() && !raw.ForestTrust.Null(), raw.IdentityFederation.Present() && !raw.IdentityFederation.Null())
	}
	m.checkEnterpriseEdges(c)
}
func (m *semanticModel) namedService(ref string) bool {
	return m.serviceNode(ref) != ""
}
func (m *semanticModel) serviceNode(ref string) string { node, _, _ := m.findService(ref); return node }
func (m *semanticModel) findService(ref string) (string, string, bool) {
	for _, node := range m.nodes {
		for _, serviceName := range node.services {
			if serviceName != "" && ref == nodesSection+"."+node.name+".services."+serviceName {
				return node.name, serviceName, true
			}
		}
	}
	return "", "", false
}
func (m *semanticModel) checkForestMemberships(c *semanticCollector) {
	forests := fieldValue(m.transport.IdentityForests)
	memberships := map[string][]string{}
	var membershipOrder []string
	for _, name := range m.keys(identityForestsField) {
		forest := forests[name]
		members := map[string]bool{}
		for _, ref := range fieldValue(forest.DomainRefs) {
			domain, known := m.forestMember(c, name, ref)
			if !known {
				continue
			}
			members[domain] = true
			if memberships[domain] == nil {
				membershipOrder = append(membershipOrder, domain)
			}
			memberships[domain] = append(memberships[domain], name)
		}
		m.checkForestRoot(c, name, fieldValue(forest.RootDomainRef), members)
	}
	m.checkForestDomainMemberships(c, memberships, membershipOrder, len(forests) != 0)
}
func (m *semanticModel) checkForestDomainMemberships(c *semanticCollector, memberships map[string][]string, membershipOrder []string, required bool) {
	for _, domain := range membershipOrder {
		if len(memberships[domain]) > 1 {
			names := slices.Clone(memberships[domain])
			slices.Sort(names)
			c.report(semanticOwner{identityDomainsField, domain}, fmt.Sprintf("Identity domain '%s' belongs to multiple forests: %s", domain, strings.Join(names, ", ")))
		}
	}
	if !required {
		return
	}
	for _, domain := range m.keys(identityDomainsField) {
		if memberships[domain] == nil {
			c.report(semanticOwner{identityDomainsField, domain}, fmt.Sprintf("Identity domain '%s' must belong to exactly one identity forest", domain))
		}
	}
}
func (m *semanticModel) forestMember(c *semanticCollector, name, ref string) (string, bool) {
	if variable(ref) {
		return "", false
	}
	domain, known := m.sectionReference(ref, identityDomainsField)
	if !known {
		c.report(semanticOwner{identityForestsField, name}, fmt.Sprintf("Identity forest '%s' domain_ref '%s' does not resolve to an identity domain", name, ref))
	}
	return domain, known
}
func (m *semanticModel) checkForestRoot(c *semanticCollector, name, ref string, members map[string]bool) {
	if variable(ref) {
		return
	}
	owner := semanticOwner{identityForestsField, name}
	domain, known := m.sectionReference(ref, identityDomainsField)
	if !known {
		c.report(owner, fmt.Sprintf("Identity forest '%s' root_domain_ref '%s' does not resolve to an identity domain", name, ref))
	} else if !members[domain] {
		c.report(owner, fmt.Sprintf("Identity forest '%s' root_domain_ref '%s' must appear in domain_refs", name, ref))
	}
}

type semanticRelationshipDetail struct {
	kind, field string
	present     bool
}

func checkEnterpriseDetails(c *semanticCollector, name, kind string, forest, federation bool) {
	checkRelationshipDetails(c, name, kind, []semanticRelationshipDetail{{forestTrustsType, forestTrustField, forest}, {directoryFederatesType, identityFederationField, federation}})
}
func checkRelationshipDetails(c *semanticCollector, name, kind string, details []semanticRelationshipDetail) {
	if variable(kind) {
		return
	}
	owner := semanticOwner{relationshipsField, name}
	for _, detail := range details {
		if detail.kind == kind && !detail.present {
			c.report(owner, fmt.Sprintf("Relationship '%s' type '%s' requires %s detail", name, kind, detail.field))
		}
	}
	for _, detail := range details {
		if detail.present && detail.kind != kind {
			c.report(owner, fmt.Sprintf("Relationship '%s' carries %s detail with type '%s'", name, detail.field, kind))
		}
	}
}
func (m *semanticModel) checkEnterpriseEdges(c *semanticCollector) {
	trusts, federations := map[[2]string]bool{}, map[string]bool{}
	for _, row := range m.relationships {
		if variable(row.kind) || variable(row.source) || variable(row.target) {
			continue
		}
		switch row.kind {
		case forestTrustsType:
			m.checkForestTrust(c, row, trusts)
		case directoryFederatesType:
			m.checkFederation(c, row, federations)
		}
	}
}
func (m *semanticModel) checkForestTrust(c *semanticCollector, row semanticRelationship, seen map[[2]string]bool) {
	source, sourceOK := m.sectionReference(row.source, identityForestsField)
	target, targetOK := m.sectionReference(row.target, identityForestsField)
	owner := semanticOwner{relationshipsField, row.name}
	switch {
	case !sourceOK || !targetOK:
		c.report(owner, fmt.Sprintf("Relationship '%s' forest trust endpoints must resolve to identity forests", row.name))
	case source == target:
		c.report(owner, fmt.Sprintf("Relationship '%s' cannot trust a forest with itself", row.name))
	default:
		if source > target {
			source, target = target, source
		}
		pair := [2]string{source, target}
		if seen[pair] {
			c.report(owner, fmt.Sprintf("Relationship '%s' duplicates a forest trust for the same forest pair", row.name))
		}
		seen[pair] = true
	}
}
func (m *semanticModel) checkFederation(c *semanticCollector, row semanticRelationship, seen map[string]bool) {
	_, domainOK := m.sectionReference(row.source, identityDomainsField)
	_, forestOK := m.sectionReference(row.source, identityForestsField)
	facade, facadeOK := m.sectionReference(row.target, identityFacadesField)
	switch {
	case (!domainOK && !forestOK) || !facadeOK:
		c.report(semanticOwner{relationshipsField, row.name}, fmt.Sprintf("Relationship '%s' must connect one identity domain or forest to an identity facade", row.name))
	case seen[facade]:
		c.report(semanticOwner{identityFacadesField, facade}, fmt.Sprintf("Identity facade '%s' has multiple authored human authorities", facade))
	default:
		seen[facade] = true
	}
}
