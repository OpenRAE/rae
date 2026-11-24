package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
	"strings"
)

type semanticTopology struct {
	model           *semanticModel
	collector       *semanticCollector
	controllers     map[string][]string
	joins           []semanticDomainJoin
	pairs           map[[3]string]bool
	memberships     map[string]map[string]uint8
	membershipOrder []string
}
type semanticDomainJoin struct {
	name, node, domain string
	controllers        []string
}
type semanticRelationship struct {
	services                   semanticRelationshipServices
	participant                *semanticParticipantRelation
	name, kind, source, target string
	controller, join           bool
	controllers                []string
	placement                  bool
	shared                     *semanticSharedService
	proxy                      *semanticProxyUpstream
}

func (m *semanticModel) relationshipFacts() ([]semanticRelationship, error) {
	var result []semanticRelationship
	for _, name := range m.keys(relationshipsField) {
		row, err := m.relationshipFact(name)
		if err != nil {
			return nil, err
		}
		result = append(result, row)
	}
	return result, nil
}
func (m *semanticModel) relationshipFact(name string) (semanticRelationship, error) {
	values := fieldValue(m.transport.Relationships)
	raw := values[name]
	row := semanticRelationship{name: name, kind: string(fieldValue(raw.Type)), source: fieldValue(raw.Source), target: fieldValue(raw.Target), controller: raw.DomainController.Present() && !raw.DomainController.Null(), join: raw.DomainJoin.Present() && !raw.DomainJoin.Null()}
	if err := m.relationshipServices(name, &row.services); err != nil {
		return semanticRelationship{}, err
	}
	if hasField(raw.Participant) {
		var detail semanticParticipantRelation
		if err := json.Unmarshal(fieldValue(raw.Participant), &detail); err != nil {
			return semanticRelationship{}, invalid()
		}
		row.participant = &detail
	}
	row.placement = raw.CarrierPlacement.Present() && !raw.CarrierPlacement.Null()
	if hasField(raw.ProxyUpstream) {
		if err := json.Unmarshal(fieldValue(raw.ProxyUpstream), &row.proxy); err != nil {
			return semanticRelationship{}, invalid()
		}
	}
	if raw.SharedService.Present() && !raw.SharedService.Null() {
		if err := json.Unmarshal(fieldValue(raw.SharedService), &row.shared); err != nil {
			return semanticRelationship{}, invalid()
		}
	}
	if err := m.domainJoinFacts(name, &row); err != nil {
		return semanticRelationship{}, err
	}
	return row, nil
}

func (m *semanticModel) domainJoinFacts(name string, row *semanticRelationship) error {
	raw := fieldValue(m.transport.Relationships)[name]
	if row.join {
		var detail struct {
			Controllers []string `json:"controller_refs"`
		}
		if err := json.Unmarshal(fieldValue(raw.DomainJoin), &detail); err != nil {
			return invalid()
		}
		row.controllers = detail.Controllers
	}
	return nil
}

func (m *semanticModel) checkTopology(c *semanticCollector) {
	t := semanticTopology{model: m, collector: c, controllers: map[string][]string{}, pairs: map[[3]string]bool{}, memberships: map[string]map[string]uint8{}}
	for _, row := range m.relationships {
		t.details(row)
	}
	for _, row := range m.relationships {
		t.relationship(row)
	}
	t.controllerChecks()
	t.buildMemberships()
	t.membershipChecks()
	t.accountChecks()
}
func (t *semanticTopology) details(row semanticRelationship) {
	if variable(row.kind) {
		return
	}
	owner := semanticOwner{relationshipsField, row.name}
	label := fmt.Sprintf("Relationship '%s'", row.name)
	switch row.kind {
	case domainControllerType:
		if !row.controller {
			t.collector.report(owner, label+" type 'domain_controller_for' requires domain_controller detail")
		}
		if row.join {
			t.collector.report(owner, label+" type 'domain_controller_for' must not carry domain_join detail")
		}
	case joinsDomainType:
		if !row.join {
			t.collector.report(owner, label+" type 'joins_domain' requires domain_join detail")
		}
		if row.controller {
			t.collector.report(owner, label+" type 'joins_domain' must not carry domain_controller detail")
		}
	default:
		if row.controller || row.join {
			t.collector.report(owner, fmt.Sprintf("%s carries domain topology detail but has type '%s'", label, row.kind))
		}
	}
}
func (m *semanticModel) sectionReference(ref, section string) (string, bool) {
	if m.definitions[section][ref] {
		return ref, true
	}
	name, prefixed := strings.CutPrefix(ref, section+".")
	return name, prefixed && m.definitions[section][name]
}
func (t *semanticTopology) relationship(row semanticRelationship) {
	if variable(row.kind) || variable(row.source) || variable(row.target) || (row.kind != domainControllerType && row.kind != joinsDomainType) {
		return
	}
	owner := semanticOwner{relationshipsField, row.name}
	label := fmt.Sprintf("Relationship '%s'", row.name)
	node, nodeOK := t.model.sectionReference(row.source, nodesSection)
	domain, domainOK := t.model.sectionReference(row.target, identityDomainsField)
	if !nodeOK {
		t.collector.report(owner, fmt.Sprintf("%s domain topology source '%s' does not resolve to a node", label, row.source))
	} else if t.model.nodes[t.model.nodeIndex[node]].kind != computeType {
		role := "controller"
		if row.kind == joinsDomainType {
			role = "join"
		}
		t.collector.report(owner, fmt.Sprintf("%s %s source '%s' must be a compute node", label, role, row.source))
	}
	if !domainOK {
		t.collector.report(owner, fmt.Sprintf("%s target '%s' does not resolve to an identity domain", label, row.target))
	}
	if nodeOK && domainOK {
		t.record(row, node, domain)
	}
}
func (t *semanticTopology) record(row semanticRelationship, node, domain string) {
	if row.kind == domainControllerType && !row.controller || row.kind == joinsDomainType && !row.join {
		return
	}
	owner := semanticOwner{relationshipsField, row.name}
	pair := [3]string{row.kind, node, domain}
	if t.pairs[pair] {
		kind := "controller"
		if row.kind == joinsDomainType {
			kind = "join"
		}
		t.collector.report(owner, fmt.Sprintf("Relationship '%s' repeats duplicate %s fact for node '%s' and identity domain '%s'", row.name, kind, node, domain))
		return
	}
	t.pairs[pair] = true
	if row.kind == domainControllerType {
		t.controllers[domain] = append(t.controllers[domain], node)
		return
	}
	join := semanticDomainJoin{name: row.name, node: node, domain: domain}
	for _, ref := range row.controllers {
		if variable(ref) {
			continue
		}
		controller, ok := t.model.sectionReference(ref, nodesSection)
		if !ok {
			t.collector.report(owner, fmt.Sprintf("Relationship '%s' controller_ref '%s' does not resolve to a node", row.name, ref))
		} else {
			join.controllers = append(join.controllers, controller)
		}
	}
	t.joins = append(t.joins, join)
}
func (t *semanticTopology) controllerChecks() {
	for _, domain := range t.model.keys(identityDomainsField) {
		if len(t.controllers[domain]) == 0 {
			t.collector.report(semanticOwner{identityDomainsField, domain}, fmt.Sprintf("Identity domain '%s' has no controller relationship", domain))
		}
	}
	// Python groups joins by domain in first-encounter order.
	for _, domain := range t.joinDomains() {
		for _, join := range t.joins {
			if join.domain == domain {
				t.checkJoinControllers(join)
			}
		}
	}
}
func (t *semanticTopology) joinDomains() []string {
	var domains []string
	for _, join := range t.joins {
		if !slices.Contains(domains, join.domain) {
			domains = append(domains, join.domain)
		}
	}
	return domains
}
func (t *semanticTopology) checkJoinControllers(join semanticDomainJoin) {
	for _, controller := range join.controllers {
		if !slices.Contains(t.controllers[join.domain], controller) {
			t.collector.report(semanticOwner{relationshipsField, join.name}, fmt.Sprintf("Relationship '%s' controller_ref '%s' does not control the same domain '%s'", join.name, controller, join.domain))
		}
	}
}
func (t *semanticTopology) addMembership(node, domain string, role uint8) {
	if t.memberships[node] == nil {
		t.memberships[node] = map[string]uint8{}
		t.membershipOrder = append(t.membershipOrder, node)
	}
	t.memberships[node][domain] |= role
}
func (t *semanticTopology) buildMemberships() {
	for _, domain := range t.model.keys(identityDomainsField) {
		for _, node := range t.controllers[domain] {
			t.addMembership(node, domain, 1)
		}
	}
	for _, domain := range t.joinDomains() {
		for _, join := range t.joins {
			if join.domain == domain {
				t.addMembership(join.node, domain, 2)
			}
		}
	}
}
func (t *semanticTopology) membershipChecks() {
	domains := fieldValue(t.model.transport.IdentityDomains)
	for _, node := range t.membershipOrder {
		var active []string
		for _, domain := range t.model.keys(identityDomainsField) {
			roles := t.memberships[node][domain]
			if roles == 0 {
				continue
			}
			if roles == 3 {
				t.collector.report(semanticOwner{nodesSection, node}, fmt.Sprintf("Node '%s' is a controller for domain '%s' and must not declare a redundant join", node, domain))
			}
			if string(fieldValue(domains[domain].Profile)) == `"active_directory"` {
				active = append(active, domain)
			}
		}
		if len(active) > 1 {
			slices.Sort(active)
			t.collector.report(semanticOwner{nodesSection, node}, fmt.Sprintf("Node '%s' belongs to multiple active_directory domains: %s", node, strings.Join(active, ", ")))
		}
	}
}
func (t *semanticTopology) accountChecks() {
	bound := map[string]string{}
	accounts := fieldValue(t.model.transport.Accounts)
	for _, name := range t.model.keys(accountsSection) {
		account := accounts[name]
		ref := fieldValue(account.DomainRef)
		owner := semanticOwner{accountsSection, name}
		if ref == "" && fieldValue(account.Spn) != "" {
			t.collector.report(owner, fmt.Sprintf("Account '%s' declares an SPN and requires explicit domain_ref", name))
		}
		if ref == "" || variable(ref) {
			continue
		}
		domain, ok := t.model.sectionReference(ref, identityDomainsField)
		if !ok {
			t.collector.report(owner, fmt.Sprintf("Account '%s' domain_ref '%s' does not resolve to an identity domain", name, ref))
			continue
		}
		t.bindAccount(name, domain, fieldValue(account.Node), bound)
	}
	t.authorityChecks(bound)
}
func (t *semanticTopology) bindAccount(name, domain, ref string, bound map[string]string) {
	if variable(ref) {
		return
	}
	node, known := t.model.sectionReference(ref, nodesSection)
	if !known {
		return
	}
	if t.memberships[node][domain] == 0 {
		t.collector.report(semanticOwner{accountsSection, name}, fmt.Sprintf("Account '%s' is placed on node '%s', which does not belong to domain '%s'", name, node, domain))
	} else {
		bound[name] = domain
	}
}
func (t *semanticTopology) authorityChecks(bound map[string]string) {
	domains, accounts := fieldValue(t.model.transport.IdentityDomains), fieldValue(t.model.transport.Accounts)
	for _, domain := range t.model.keys(identityDomainsField) {
		ref := fieldValue(domains[domain].AuthorityAccountRef)
		if variable(ref) {
			continue
		}
		owner := semanticOwner{identityDomainsField, domain}
		name, known := t.model.sectionReference(ref, accountsSection)
		if !known {
			t.collector.report(owner, fmt.Sprintf("Identity domain '%s' authority account '%s' is not declared", domain, ref))
			continue
		}
		node, _ := t.model.sectionReference(fieldValue(accounts[name].Node), nodesSection)
		switch {
		case !slices.Contains(t.controllers[domain], node):
			t.collector.report(owner, fmt.Sprintf("Identity domain '%s' authority account '%s' must be placed on one of its controller nodes", domain, name))
		case bound[name] != "" && bound[name] != domain:
			t.collector.report(owner, fmt.Sprintf("Identity domain '%s' authority account '%s' is already bound to domain '%s'", domain, name, bound[name]))
		default:
			bound[name] = domain
		}
	}
}
