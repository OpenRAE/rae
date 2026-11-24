package processor

import (
	"encoding/json"
	"maps"
	"slices"
	"strings"
)

// Authored episode conditions map only to these participant episode terminal reasons.
const (
	episodeCompleted = "completed"
	episodeTimedOut  = "timed_out"
	episodeTruncated = "truncated"
	episodeLocal     = "episode_local_reset"
)

type episodePolicySource struct {
	Profile        string `json:"profile"`
	Initialization *struct {
		AssertionRefs []string `json:"assertion_refs"`
	} `json:"initialization"`
	InteractionStructure *struct {
		OrderBasis         string   `json:"order_basis"`
		ActionContractRefs []string `json:"action_contract_refs"`
	} `json:"interaction_structure"`
	TerminalConditions   map[string]episodeConditionSource `json:"terminal_conditions"`
	TruncationConditions map[string]episodeConditionSource `json:"truncation_conditions"`
	ResetPolicy          *struct {
		ControlActions          []string `json:"control_actions"`
		ParticipantMemoryScope  string   `json:"participant_memory_scope"`
		MemoryResetAuthorityRef *string  `json:"memory_reset_authority_ref"`
		EvidenceRequirementRefs []string `json:"evidence_requirement_refs"`
	} `json:"reset_policy"`
}

type episodeConditionSource struct {
	TerminalReason          string   `json:"terminal_reason"`
	AssertionRefs           []string `json:"assertion_refs"`
	TemporalConstraintRef   string   `json:"temporal_constraint_ref"`
	EvidenceRequirementRefs []string `json:"evidence_requirement_refs"`
}

type episodeCondition struct {
	ConditionID                  string   `json:"condition_id"`
	TerminalReason               string   `json:"terminal_reason"`
	EvidenceRequirementAddresses []string `json:"evidence_requirement_addresses"`
	AssertionAddresses           []string `json:"assertion_addresses"`
	TemporalConstraintAddress    string   `json:"temporal_constraint_address"`
}

type episodePolicy struct {
	Name                              string             `json:"name"`
	Spec                              json.RawMessage    `json:"spec"`
	BehaviorSpecificationAddress      string             `json:"behavior_specification_address"`
	ParticipantAddresses              []string           `json:"participant_addresses"`
	Profile                           string             `json:"profile"`
	InitializationAssertionAddresses  []string           `json:"initialization_assertion_addresses"`
	TurnOrderBasis                    string             `json:"turn_order_basis"`
	TurnActionContractAddresses       []string           `json:"turn_action_contract_addresses"`
	Conditions                        []episodeCondition `json:"conditions"`
	ResetControlActions               []string           `json:"reset_control_actions"`
	ParticipantMemoryScope            string             `json:"participant_memory_scope"`
	MemoryResetAuthorityAddress       string             `json:"memory_reset_authority_address"`
	ResetEvidenceRequirementAddresses []string           `json:"reset_evidence_requirement_addresses"`
}

// compileEpisodePolicies compiles each admitted behavior-specification episode
// policy as participant metadata. It creates no episode identity, state,
// history or terminal fact.
func (state *compilerState) compileEpisodePolicies() {
	specifications := fieldValue(state.input.model.BehaviorSpecifications)
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		raw := fieldValue(specifications[name].EpisodePolicy)
		if len(raw) == 0 || string(raw) == "null" {
			continue
		}
		var source episodePolicySource
		if err := json.Unmarshal(raw, &source); err != nil {
			state.err = invalidCompiled()
			return
		}
		owner := state.address(termParticipant, termBehaviorSpecification, name)
		participants, _ := state.selectParticipants(participantSelector{fieldValue(specifications[name].ParticipantRefs), fieldValue(specifications[name].ParticipantRoleRefs)}, owner, false)
		state.compileEpisodePolicy(name, raw, source, owner, participants)
		if state.err != nil {
			return
		}
	}
}

func (state *compilerState) compileEpisodePolicy(name string, raw json.RawMessage, source episodePolicySource, owner string, participants []string) {
	output := episodePolicy{Name: name, Spec: raw, BehaviorSpecificationAddress: owner, ParticipantAddresses: nonNilStrings(participants), Profile: source.Profile, InitializationAssertionAddresses: []string{}, TurnActionContractAddresses: []string{}, Conditions: []episodeCondition{}, ResetControlActions: []string{}, ResetEvidenceRequirementAddresses: []string{}}
	if source.Initialization != nil {
		output.InitializationAssertionAddresses = state.episodeAssertions(source.Initialization.AssertionRefs)
	}
	if structure := source.InteractionStructure; structure != nil {
		output.TurnOrderBasis = structure.OrderBasis
		for _, ref := range structure.ActionContractRefs {
			output.TurnActionContractAddresses = append(output.TurnActionContractAddresses, state.address(termParticipant, termActionContract, state.sectionName(ref, termActionContracts)))
		}
	}
	output.Conditions = state.episodeConditions(source)
	if reset := source.ResetPolicy; reset != nil {
		output.ResetControlActions = nonNilStrings(reset.ControlActions)
		output.ParticipantMemoryScope = reset.ParticipantMemoryScope
		output.ResetEvidenceRequirementAddresses = state.episodeEvidence(reset.EvidenceRequirementRefs)
		if reset.MemoryResetAuthorityRef != nil {
			output.MemoryResetAuthorityAddress = state.episodeResetAuthority(*reset.MemoryResetAuthorityRef)
			if output.MemoryResetAuthorityAddress == "" {
				return
			}
		}
	}
	if (output.ParticipantMemoryScope == episodeLocal) != (output.MemoryResetAuthorityAddress != "") {
		state.err = invalidCompiled()
		return
	}
	dependencies := []string{owner}
	dependencies = append(dependencies, output.ParticipantAddresses...)
	dependencies = append(dependencies, output.InitializationAssertionAddresses...)
	dependencies = append(dependencies, output.TurnActionContractAddresses...)
	for _, condition := range output.Conditions {
		dependencies = append(dependencies, condition.AssertionAddresses...)
		if condition.TemporalConstraintAddress != "" {
			dependencies = append(dependencies, condition.TemporalConstraintAddress)
		}
		dependencies = append(dependencies, condition.EvidenceRequirementAddresses...)
	}
	dependencies = append(dependencies, output.ResetEvidenceRequirementAddresses...)
	if output.MemoryResetAuthorityAddress != "" {
		dependencies = append(dependencies, output.MemoryResetAuthorityAddress)
	}
	address := state.address(termParticipant, "episode-policy", name)
	state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: "participant-episode-policy", RefreshDependencies: dedupe(dependencies), Payload: state.payload(output)})
}

func (state *compilerState) episodeConditions(source episodePolicySource) []episodeCondition {
	conditions := []episodeCondition{}
	for _, id := range slices.Sorted(maps.Keys(source.TerminalConditions)) {
		condition := source.TerminalConditions[id]
		compiled := episodeCondition{ConditionID: id, TerminalReason: condition.TerminalReason, EvidenceRequirementAddresses: state.episodeEvidence(condition.EvidenceRequirementRefs), AssertionAddresses: []string{}}
		if condition.TerminalReason == episodeTimedOut {
			compiled.TemporalConstraintAddress = state.address("time", "constraint", state.sectionName(condition.TemporalConstraintRef, "temporal_constraints"))
		} else {
			compiled.AssertionAddresses = state.episodeAssertions(condition.AssertionRefs)
		}
		conditions = append(conditions, compiled)
	}
	for _, id := range slices.Sorted(maps.Keys(source.TruncationConditions)) {
		condition := source.TruncationConditions[id]
		conditions = append(conditions, episodeCondition{ConditionID: id, TerminalReason: episodeTruncated, EvidenceRequirementAddresses: state.episodeEvidence(condition.EvidenceRequirementRefs), AssertionAddresses: state.episodeAssertions(condition.AssertionRefs)})
	}
	slices.SortFunc(conditions, func(a, b episodeCondition) int { return strings.Compare(a.ConditionID, b.ConditionID) })
	for _, condition := range conditions {
		timed := condition.TerminalReason == episodeTimedOut
		reasonKnown := condition.TerminalReason == episodeCompleted || timed || condition.TerminalReason == episodeTruncated
		if !reasonKnown || len(condition.EvidenceRequirementAddresses) == 0 || timed != (condition.TemporalConstraintAddress != "") || timed == (len(condition.AssertionAddresses) > 0) {
			state.err = invalidCompiled()
			return nil
		}
	}
	return conditions
}

func (state *compilerState) episodeAssertions(refs []string) []string {
	result := []string{}
	for _, ref := range refs {
		result = append(result, state.address("evaluation", "assertion", state.sectionName(ref, "assertions")))
	}
	return result
}

func (state *compilerState) episodeEvidence(refs []string) []string {
	result := []string{}
	for _, ref := range refs {
		result = append(result, state.address("sdl", "evidence-requirements", state.sectionName(ref, "evidence_requirements")))
	}
	return result
}

// episodeResetAuthority renders the one targetable declaration that semantic
// validation resolved as the memory reset authority.
func (state *compilerState) episodeResetAuthority(ref string) string {
	aliases, err := state.referenceAliases("targetable")
	if err != nil {
		state.err = err
		return ""
	}
	candidates := aliases[ref]
	if len(candidates) != 1 {
		state.err = invalidCompiled()
		return ""
	}
	section, name, found := strings.Cut(candidates[0], ".")
	if !found {
		state.err = invalidCompiled()
		return ""
	}
	return state.address("sdl", strings.ReplaceAll(section, "_", "-"), name)
}
