package processor

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type controlContextSelection struct {
	SlotID             string          `json:"slot_id"`
	ParticipantAddress string          `json:"participant_address"`
	DeclarationAddress string          `json:"declaration_address"`
	AssetRef           json.RawMessage `json:"asset_ref"`
	Disposition        string          `json:"disposition"`
	OwnerAddress       string          `json:"owner_address"`
}
type participantAccess struct {
	AccessID       string          `json:"access_id"`
	TargetRef      string          `json:"target_ref"`
	TargetAddress  string          `json:"target_address"`
	Channel        json.RawMessage `json:"channel"`
	AccountRef     string          `json:"account_ref"`
	AccountAddress string          `json:"account_address"`
}
type participantBehavior struct {
	Name                           string                    `json:"name"`
	Spec                           any                       `json:"spec"`
	ControlContext                 []controlContextSelection `json:"control_context,omitempty"`
	ParticipantName                string                    `json:"participant_name"`
	AffiliationNames               []string                  `json:"affiliation_names"`
	Role                           string                    `json:"role"`
	StartingAccountRefs            []string                  `json:"starting_account_refs"`
	StartingAccountAddresses       []string                  `json:"starting_account_addresses"`
	InitialKnowledgeAddresses      []string                  `json:"initial_knowledge_addresses"`
	StartingAssertionRefs          []string                  `json:"starting_assertion_refs"`
	StartingAssertionAddresses     []string                  `json:"starting_assertion_addresses"`
	AuthorityAnchorRefs            []string                  `json:"authority_anchor_refs"`
	AuthorityAnchorAddresses       []string                  `json:"authority_anchor_addresses"`
	OperatingScopeRefs             []string                  `json:"operating_scope_refs"`
	OperatingScopeAddresses        []string                  `json:"operating_scope_addresses"`
	ActionContractAddresses        []string                  `json:"action_contract_addresses"`
	TemporallyBoundActionAddresses []string                  `json:"temporally_bound_action_addresses"`
	ObservationBoundaryAddresses   []string                  `json:"observation_boundary_addresses"`
	InteractiveAccess              []participantAccess       `json:"interactive_access"`
	InterpretationMode             string                    `json:"interpretation_mode"`
}

func (state *compilerState) controlContext(owner, participant string, bindings map[string]json.RawMessage, pointer string) []controlContextSelection {
	result := []controlContextSelection{}
	for _, slot := range orderedNames(bindings, state.input.order[pointer]) {
		var source struct {
			DeclarationRef string          `json:"declaration_ref"`
			AssetRef       json.RawMessage `json:"asset_ref"`
			Disposition    string          `json:"disposition"`
		}
		if err := json.Unmarshal(bindings[slot], &source); err != nil {
			state.err = invalidCompiled()
			return nil
		}
		declarations := state.input.aliases[source.DeclarationRef]
		if len(declarations) != 1 {
			state.err = invalidCompiled()
			return nil
		}
		result = append(result, controlContextSelection{slot, "agents." + participant, declarations[0], source.AssetRef, source.Disposition, owner})
	}
	return result
}
func (state *compilerState) participantReferences(refs []string, section, kind, owner, code, label string) ([]string, []diagnostic.Diagnostic) {
	result := []string{}
	findings := []diagnostic.Diagnostic{}
	for _, ref := range dedupe(refs) {
		if state.known(section)[ref] {
			result = append(result, state.address(termParticipant, kind, ref))
			continue
		}
		if ref != "" {
			findings = append(findings, compileDiagnostic(code, termParticipant, owner, "Reference '"+ref+"' does not resolve to a declared "+label+"."))
		}
	}
	return result, findings
}
func (state *compilerState) initialKnowledge(raw json.RawMessage) []string {
	result := []string{}
	if len(raw) == 0 || string(raw) == termNull {
		return result
	}
	var source struct {
		Hosts    []string `json:"hosts"`
		Subnets  []string `json:"subnets"`
		Services []string `json:"services"`
		Accounts []string `json:"accounts"`
	}
	if err := json.Unmarshal(raw, &source); err != nil {
		state.err = invalidCompiled()
		return nil
	}
	nodes := fieldValue(state.input.model.Nodes)
	for _, ref := range source.Hosts {
		if _, exists := nodes[ref]; exists {
			result = append(result, state.nodeAddress(ref))
		}
	}
	result = append(result, state.initialKnowledgeSubnets(source.Subnets)...)
	qualified, services := state.initialKnowledgeServices()
	for _, ref := range source.Services {
		if address, known := qualified[ref]; known {
			result = append(result, address)
		} else {
			result = append(result, services[ref]...)
		}
	}
	for _, ref := range source.Accounts {
		if state.known(termAccounts)[ref] {
			result = append(result, state.address(termProvision, "account", ref))
		}
	}
	return dedupe(result)
}
func (state *compilerState) initialKnowledgeSubnets(refs []string) []string {
	result := []string{}
	nodes := fieldValue(state.input.model.Nodes)
	for _, ref := range refs {
		if state.known("infrastructure")[ref] {
			if _, exists := nodes[ref]; exists {
				result = append(result, state.nodeAddress(ref))
			}
		}
	}
	return result
}

func (state *compilerState) initialKnowledgeServices() (map[string]string, map[string][]string) {
	qualified := map[string]string{}
	unqualified := map[string][]string{}
	nodes := fieldValue(state.input.model.Nodes)
	for _, name := range orderedNames(nodes, state.names(termNodes)) {
		seen := map[string]bool{}
		for _, service := range fieldValue(nodes[name].Services) {
			serviceName := rawString(fieldValue(service.Name))
			if serviceName == "" || seen[serviceName] {
				continue
			}
			seen[serviceName] = true
			address := state.address(termProvision, termNode, name, "service", serviceName)
			if serviceName != "" {
				qualified["nodes."+name+".services."+serviceName] = address
			}
			unqualified[serviceName] = append(unqualified[serviceName], address)
		}
	}
	return qualified, unqualified
}

func (state *compilerState) participantInteractiveAccess(source map[string]json.RawMessage) ([]participantAccess, []string) {
	result := []participantAccess{}
	dependencies := []string{}
	for _, id := range slices.Sorted(maps.Keys(source)) {
		var access struct {
			TargetRef  string          `json:"target_ref"`
			Channel    json.RawMessage `json:"channel"`
			AccountRef string          `json:"account_ref"`
		}
		if err := json.Unmarshal(source[id], &access); err != nil {
			state.err = invalidCompiled()
			return nil, nil
		}
		target := state.nodeAddress(state.sectionName(access.TargetRef, termNodes))
		account := ""
		dependencies = append(dependencies, target)
		if access.AccountRef != "" {
			account = state.address(termProvision, "account", state.sectionName(access.AccountRef, termAccounts))
			dependencies = append(dependencies, account)
		}
		result = append(result, participantAccess{id, access.TargetRef, target, access.Channel, access.AccountRef, account})
	}
	return result, dependencies
}
func (state *compilerState) compileParticipantBehaviors() {
	agents := fieldValue(state.input.model.Agents)
	findings := []diagnostic.Diagnostic{}
	state.behaviors = map[string]participantBehavior{}
	for _, name := range orderedNames(agents, state.names("agents")) {
		findings = append(findings, state.compileParticipantBehavior(name)...)
	}
	state.addDiagnostics(findings)
}

func (state *compilerState) compileParticipantBehavior(name string) []diagnostic.Diagnostic {
	contracts := fieldValue(state.input.model.ActionContracts)
	findings := []diagnostic.Diagnostic{}
	agent := fieldValue(state.input.model.Agents)[name]
	address := state.address(termParticipant, "behavior", name)
	actions := []string{}
	if len(contracts) > 0 {
		var local []diagnostic.Diagnostic
		actions, local = state.participantReferences(fieldValue(agent.Actions), termActionContracts, termActionContract, address, "participant.action-contract-ref-unbound", "participant action contract")
		findings = append(findings, local...)
	}
	observations, local := state.participantReferences(fieldValue(agent.ObservationBoundaries), termObservationBoundaries, termObservationBoundary, address, "participant.observation-boundary-ref-unbound", "participant observation boundary")
	findings = append(findings, local...)
	accesses, accessDependencies := state.participantInteractiveAccess(fieldValue(agent.InteractiveAccess))
	output := participantBehavior{Name: name, Spec: struct {
		Agent              json.RawMessage `json:"agent"`
		InterpretationMode string          `json:"interpretation_mode"`
	}{state.participantAgentSource(name), "role-neutral-projection"}, ParticipantName: name, ControlContext: state.contextByParticipant["agents."+name], AffiliationNames: nonNilStrings(fieldValue(agent.Affiliations)), Role: state.participantRoles[name], StartingAccountRefs: nonNilStrings(fieldValue(agent.StartingAccounts)), StartingAccountAddresses: []string{}, InitialKnowledgeAddresses: state.initialKnowledge(fieldValue(agent.InitialKnowledge)), StartingAssertionRefs: nonNilStrings(fieldValue(agent.StartingAssertions)), StartingAssertionAddresses: []string{}, AuthorityAnchorRefs: nonNilStrings(fieldValue(agent.AuthorityAnchors)), AuthorityAnchorAddresses: state.runtimeAddressesFor(fieldValue(agent.AuthorityAnchors), "authority-anchor"), OperatingScopeRefs: nonNilStrings(fieldValue(agent.OperatingScope)), OperatingScopeAddresses: state.runtimeAddressesFor(fieldValue(agent.OperatingScope), "operating-scope"), ActionContractAddresses: actions, TemporallyBoundActionAddresses: []string{}, ObservationBoundaryAddresses: observations, InteractiveAccess: accesses, InterpretationMode: "role-neutral-projection"}
	for _, ref := range output.StartingAccountRefs {
		if state.known(termAccounts)[ref] {
			output.StartingAccountAddresses = append(output.StartingAccountAddresses, state.address(termProvision, "account", ref))
		}
	}
	for _, ref := range output.StartingAssertionRefs {
		output.StartingAssertionAddresses = append(output.StartingAssertionAddresses, state.address(termEvaluation, termAssertion, ref))
	}
	output.TemporallyBoundActionAddresses = state.temporallyBoundActions(fieldValue(agent.Actions))
	dependencies := []string{}
	for _, refs := range [][]string{actions, observations, output.StartingAccountAddresses, output.InitialKnowledgeAddresses, output.StartingAssertionAddresses, output.AuthorityAnchorAddresses, output.OperatingScopeAddresses, accessDependencies} {
		dependencies = append(dependencies, refs...)
	}
	state.behaviors[address] = output
	state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: termParticipantBehavior, OrderingDependencies: []string{}, RefreshDependencies: dedupe(dependencies), Payload: state.payload(output)})
	return findings
}

func (state *compilerState) temporallyBoundActions(refs []string) []string {
	contracts := fieldValue(state.input.model.ActionContracts)
	addresses := []string{}
	for _, ref := range dedupe(refs) {
		contract, exists := contracts[ref]
		if !exists {
			continue
		}
		for _, temporal := range fieldValue(contract.TemporalContracts) {
			if temporal.SharedTimeBinding.Present() && !temporal.SharedTimeBinding.Null() {
				addresses = append(addresses, state.address(termParticipant, termActionContract, ref))
				break
			}
		}
	}

	return addresses
}
