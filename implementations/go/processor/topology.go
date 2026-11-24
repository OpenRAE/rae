package processor

import (
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type compiledTopology struct {
	nodes        map[string]*DomainTopology
	nodeOrder    []string
	accountNodes map[string]string
}

// SDL admission owns topology validity. This pass only lowers admitted
// relationships to resolved runtime identities and dependency facts.
func (state *compilerState) compileTopology() {
	controllers, joins, joinDomains := state.topologyRelations()
	if state.err != nil {
		return
	}
	topology := compiledTopology{nodes: map[string]*DomainTopology{}, accountNodes: map[string]string{}}
	domains := fieldValue(state.input.model.IdentityDomains)
	for _, domain := range orderedNames(domains, state.names("identity_domains")) {
		for _, node := range controllers[domain] {
			state.addTopologyBinding(&topology, node, domain, "controller", controllers[domain])
		}
	}
	for _, domain := range joinDomains {
		for _, join := range joins[domain] {
			state.addTopologyBinding(&topology, join.node, domain, "member", join.controllers)
		}
	}
	state.compileTopologyAccountNodes(&topology)
	state.topology = topology
}

type domainTopologyJoin struct {
	node        string
	controllers []string
}

func (state *compilerState) topologyRelations() (map[string][]string, map[string][]domainTopologyJoin, []string) {
	relationships := fieldValue(state.input.model.Relationships)
	controllers := map[string][]string{}
	joins := map[string][]domainTopologyJoin{}
	order := []string{}
	for _, name := range orderedNames(relationships, state.names("relationships")) {
		relation := relationships[name]
		kind := string(fieldValue(relation.Type))
		if kind != "domain_controller_for" && kind != "joins_domain" {
			continue
		}
		node := state.sectionName(fieldValue(relation.Source), termNodes)
		domain := state.sectionName(fieldValue(relation.Target), "identity_domains")
		if kind == "domain_controller_for" {
			controllers[domain] = append(controllers[domain], node)
			continue
		}
		names := state.joinControllerNames(fieldValue(relation.DomainJoin))
		if state.err != nil {
			return nil, nil, nil
		}
		if _, present := joins[domain]; !present {
			order = append(order, domain)
		}
		joins[domain] = append(joins[domain], domainTopologyJoin{node, names})
	}
	return controllers, joins, order
}
func (state *compilerState) joinControllerNames(raw json.RawMessage) []string {
	var detail struct {
		ControllerRefs []string `json:"controller_refs"`
	}
	if err := json.Unmarshal(raw, &detail); err != nil {
		state.err = invalidCompiled()
		return nil
	}
	names := []string{}
	for _, ref := range detail.ControllerRefs {
		names = append(names, state.sectionName(ref, termNodes))
	}
	return names
}
func (state *compilerState) addTopologyBinding(topology *compiledTopology, node, domain, role string, controllerNames []string) {
	if _, exists := topology.nodes[node]; exists {
		return
	}
	declaration := fieldValue(state.input.model.IdentityDomains)[domain]
	profile := fieldValue(declaration.Profile)
	result := &DomainTopology{DomainID: domain, Profile: rawString(profile), DNSName: fieldValue(declaration.DnsName), NetBIOSName: fieldValue(declaration.NetbiosName), AuthorityAccountAddress: state.address(termProvision, "account", state.sectionName(fieldValue(declaration.AuthorityAccountRef), termAccounts)), Role: role, ControllerAddresses: []string{}}
	if result.Profile == "" && len(profile) > 0 {
		result.ProfileBinding = domainProfileBinding(profile)
	}
	for _, name := range controllerNames {
		result.ControllerAddresses = append(result.ControllerAddresses, state.address(termProvision, termNode, name))
	}
	topology.nodes[node] = result
	topology.nodeOrder = append(topology.nodeOrder, node)
}
func (state *compilerState) compileTopologyAccountNodes(topology *compiledTopology) {
	accounts := fieldValue(state.input.model.Accounts)
	for _, name := range orderedNames(accounts, state.names(termAccounts)) {
		account := accounts[name]
		if fieldValue(account.DomainRef) != "" {
			topology.accountNodes[name] = state.sectionName(fieldValue(account.Node), termNodes)
		}
	}
	domains := fieldValue(state.input.model.IdentityDomains)
	for _, domain := range orderedNames(domains, state.names("identity_domains")) {
		authority := state.sectionName(fieldValue(domains[domain].AuthorityAccountRef), termAccounts)
		topology.accountNodes[authority] = state.sectionName(fieldValue(accounts[authority].Node), termNodes)
	}
}

func (state *compilerState) sectionName(ref, section string) string {
	if state.known(section)[ref] {
		return ref
	}
	return strings.TrimPrefix(ref, section+".")
}
func domainProfileBinding(raw json.RawMessage) *binding.DomainProfileBindingV1 {
	if len(raw) == 0 || raw[0] != '{' {
		return nil
	}
	var result binding.DomainProfileBindingV1
	if err := json.Unmarshal(raw, &result); err != nil {
		return nil
	}
	return &result
}
func topologyWire(input *DomainTopology) any {
	if input == nil {
		return nil
	}
	profile := any(input.Profile)
	if input.ProfileBinding != nil {
		profile = input.ProfileBinding
	}
	return struct {
		DomainID                string   `json:"domain_id"`
		Profile                 any      `json:"profile"`
		DNSName                 string   `json:"dns_name"`
		NetBIOSName             string   `json:"netbios_name"`
		AuthorityAccountAddress string   `json:"authority_account_address"`
		Role                    string   `json:"role"`
		ControllerAddresses     []string `json:"controller_addresses"`
	}{input.DomainID, profile, input.DNSName, input.NetBIOSName, input.AuthorityAccountAddress, input.Role, input.ControllerAddresses}
}
func (state *compilerState) compileDomainControllerPlacements() {
	for _, node := range state.topology.nodeOrder {
		topology := state.topology.nodes[node]
		if topology.Role != "controller" {
			continue
		}
		target := state.address(termProvision, termNode, node)
		payload := struct {
			Name           string   `json:"name"`
			Spec           struct{} `json:"spec"`
			TargetAddress  string   `json:"target_address"`
			DomainTopology any      `json:"domain_topology"`
		}{node + "." + topology.DomainID, struct{}{}, target, topologyWire(topology)}
		state.model.Resources = append(state.model.Resources, Resource{Address: state.address(termProvision, "domain-controller", topology.DomainID, node), Name: node + "." + topology.DomainID, Domain: termProvisioning, Kind: termDomainControllerPlacement, OrderingDependencies: []string{target}, RefreshDependencies: []string{target}, TargetAddress: target, Topology: topology, Payload: state.payload(payload)})
	}
}
