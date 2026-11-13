package processor

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type participantSelector struct {
	ParticipantRefs     []string `json:"participant_refs"`
	ParticipantRoleRefs []string `json:"participant_role_refs"`
}

func (state *compilerState) selectParticipants(selector participantSelector, owner string, roles bool) ([]string, []diagnostic.Diagnostic) {
	selected := map[string]bool{}
	findings := []diagnostic.Diagnostic{}
	participantCode := "participant.behavior-specification-participant-ref-unbound"
	if roles {
		participantCode = "participant.tool-affordance-participant-ref-unbound"
	}
	for _, ref := range dedupe(selector.ParticipantRefs) {
		if state.known("agents")[ref] {
			selected[ref] = true
			continue
		}
		if ref != "" {
			findings = append(findings, compileDiagnostic(participantCode, termParticipant, owner, "Reference '"+ref+"' does not resolve to a declared agent."))
		}
	}
	byRole := state.participantsByRole()
	for _, role := range dedupe(selector.ParticipantRoleRefs) {
		matches := byRole[role]
		for _, participant := range matches {
			selected[participant] = true
		}
		if roles && len(matches) == 0 {
			findings = append(findings, compileDiagnostic("participant.tool-affordance-participant-role-ref-unbound", termParticipant, owner, "Role '"+role+"' matches no declared agent's role."))
		}
	}
	result := []string{}
	for _, participant := range slices.Sorted(maps.Keys(selected)) {
		result = append(result, state.address(termParticipant, "behavior", participant))
	}
	return result, findings
}

func (state *compilerState) participantsByRole() map[string][]string {
	byRole := map[string][]string{}
	for participant, role := range state.participantRoles {
		if role != "" {
			byRole[role] = append(byRole[role], participant)
		}
	}
	return byRole
}

type participantToolSource struct {
	participantSelector

	ToolRef                 string   `json:"tool_ref"`
	ActionContractRefs      []string `json:"action_contract_refs"`
	ObservationBoundaryRefs []string `json:"observation_boundary_refs"`
}
type participantTool struct {
	Name                         string          `json:"name"`
	Spec                         json.RawMessage `json:"spec"`
	AffordanceID                 string          `json:"affordance_id"`
	BehaviorSpecificationAddress string          `json:"behavior_specification_address"`
	ToolRef                      string          `json:"tool_ref"`
	ToolAddress                  string          `json:"tool_address"`
	ActionContractRefs           []string        `json:"action_contract_refs"`
	ActionContractAddresses      []string        `json:"action_contract_addresses"`
	ObservationBoundaryRefs      []string        `json:"observation_boundary_refs"`
	ObservationBoundaryAddresses []string        `json:"observation_boundary_addresses"`
	ParticipantRefs              []string        `json:"participant_refs"`
	ParticipantRoleRefs          []string        `json:"participant_role_refs"`
	ParticipantAddresses         []string        `json:"participant_addresses"`
}

func (state *compilerState) compileToolAffordance(name, id string, raw json.RawMessage, parent []string) []diagnostic.Diagnostic {
	findings := []diagnostic.Diagnostic{}
	owner := state.address(termParticipant, termBehaviorSpecification, name)
	var source participantToolSource
	if err := json.Unmarshal(raw, &source); err != nil {
		state.err = invalidCompiled()
		return findings
	}
	address := state.address(termParticipant, termBehaviorSpecification, name, "tool-affordance", id)
	participants := []string{}
	if len(source.ParticipantRefs) > 0 || len(source.ParticipantRoleRefs) > 0 {
		var local []diagnostic.Diagnostic
		participants, local = state.selectParticipants(source.participantSelector, address, true)
		findings = append(findings, local...)
		for _, participant := range participants {
			if !slices.Contains(parent, participant) {
				findings = append(findings, compileDiagnostic("participant.tool-affordance-participant-widens-parent", termParticipant, address, "Participant '"+participant+"' is outside the owning behavior specification."))
			}
		}
	}
	actions, local := state.participantReferences(source.ActionContractRefs, termActionContracts, termActionContract, address, "participant.tool-affordance-action-contract-ref-unbound", "participant action contract")
	findings = append(findings, local...)
	observations, local := state.participantReferences(source.ObservationBoundaryRefs, termObservationBoundaries, termObservationBoundary, address, "participant.tool-affordance-observation-boundary-ref-unbound", "participant observation boundary")
	findings = append(findings, local...)
	toolAddress := ""
	dependencies := []string{owner}
	if source.ToolRef != "" {
		toolAddress = state.address(termProvision, termContent, state.sectionName(source.ToolRef, termContent))
		dependencies = append(dependencies, toolAddress)
	}
	dependencies = append(dependencies, actions...)
	dependencies = append(dependencies, observations...)
	dependencies = append(dependencies, participants...)
	output := participantTool{Name: id, Spec: raw, AffordanceID: id, BehaviorSpecificationAddress: owner, ToolRef: source.ToolRef, ToolAddress: toolAddress, ActionContractRefs: nonNilStrings(source.ActionContractRefs), ActionContractAddresses: actions, ObservationBoundaryRefs: nonNilStrings(source.ObservationBoundaryRefs), ObservationBoundaryAddresses: observations, ParticipantRefs: nonNilStrings(source.ParticipantRefs), ParticipantRoleRefs: nonNilStrings(source.ParticipantRoleRefs), ParticipantAddresses: participants}
	state.tools[address] = output
	state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: id, Domain: termParticipant, Kind: "tool-affordance", OrderingDependencies: []string{}, RefreshDependencies: dedupe(dependencies), Payload: state.payload(output)})
	return findings
}

func (state *compilerState) compileToolAffordances() {
	specifications := fieldValue(state.input.model.BehaviorSpecifications)
	findings := []diagnostic.Diagnostic{}
	state.tools = map[string]participantTool{}
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		specification := specifications[name]
		owner := state.address(termParticipant, termBehaviorSpecification, name)
		parent, _ := state.selectParticipants(participantSelector{fieldValue(specification.ParticipantRefs), fieldValue(specification.ParticipantRoleRefs)}, owner, false)
		bindings := fieldValue(specification.ToolAffordances)
		for _, id := range slices.Sorted(maps.Keys(bindings)) {
			findings = append(findings, state.compileToolAffordance(name, id, bindings[id], parent)...)
			if state.err != nil {
				return
			}
		}
	}
	state.addDiagnostics(findings)
}
