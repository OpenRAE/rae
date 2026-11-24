package processor

import "encoding/json"

type participantOutcomeRule struct {
	sources               []participantOutcomeSourceDeclaration
	targets               []participantOutcomeTargetDeclaration
	Name                  string          `json:"name"`
	Spec                  json.RawMessage `json:"spec"`
	RuleName              string          `json:"rule_name"`
	SemanticVersion       string          `json:"semantic_version"`
	ParticipantScope      string          `json:"participant_scope"`
	ObservationPointBasis string          `json:"observation_point_basis"`
	InterpretationBasis   string          `json:"interpretation_basis"`
	SourceLayers          []string        `json:"source_layers"`
	SourceRefs            []string        `json:"source_refs"`
	TargetLayers          []string        `json:"target_layers"`
	TargetRefs            []string        `json:"target_refs"`
	EvidenceRefs          []string        `json:"evidence_refs"`
	Limitations           []string        `json:"limitations"`
}

func (state *compilerState) outcomeReference(layer, ref string, source bool) string {
	switch layer {
	case "participant_action_outcome":
		if source {
			return state.address(termParticipant, termActionContract, ref)
		}
	case "objective_result":
		return state.address(termEvaluation, termObjective, ref)
	case "workflow_result":
		return state.address(termOrchestration, termWorkflow, ref)
	case "evaluation_result":
		return state.address(termEvaluation, termEvaluation, ref)
	}
	return ref
}
func (state *compilerState) compileOutcomeRules() {
	rules := fieldValue(state.input.model.OutcomeInterpretationRules)
	state.outcomes = map[string]participantOutcomeRule{}
	for _, name := range orderedNames(rules, state.names(termOutcomeInterpretationRules)) {
		source := rules[name]
		output := participantOutcomeRule{Name: name, Spec: rawJSON(source), RuleName: name, SemanticVersion: fieldValue(source.SemanticVersion), ParticipantScope: string(fieldValue(source.ParticipantScope)), ObservationPointBasis: fieldValue(source.ObservationPointBasis), InterpretationBasis: fieldValue(source.InterpretationBasis), SourceLayers: []string{}, SourceRefs: []string{}, TargetLayers: []string{}, TargetRefs: []string{}, EvidenceRefs: nonNilStrings(fieldValue(source.EvidenceRefs)), Limitations: nonNilStrings(fieldValue(source.Limitations))}
		for _, binding := range fieldValue(source.SourceBindings) {
			layer := string(fieldValue(binding.SourceLayer))
			output.SourceLayers = append(output.SourceLayers, layer)
			output.SourceRefs = append(output.SourceRefs, state.outcomeReference(layer, fieldValue(binding.Ref), true))
			output.sources = append(output.sources, participantOutcomeSourceDeclaration{ID: fieldValue(binding.SourceId), Layer: layer, Ref: output.SourceRefs[len(output.SourceRefs)-1], EvidenceRefs: fieldValue(binding.EvidenceRefs), ProvenanceRefs: fieldValue(binding.ProvenanceRefs)})
		}
		for _, binding := range fieldValue(source.TargetBindings) {
			layer := string(fieldValue(binding.TargetLayer))
			output.TargetLayers = append(output.TargetLayers, layer)
			output.TargetRefs = append(output.TargetRefs, state.outcomeReference(layer, fieldValue(binding.Ref), false))
			output.targets = append(output.targets, participantOutcomeTargetDeclaration{ID: fieldValue(binding.TargetId), Layer: layer, Ref: output.TargetRefs[len(output.TargetRefs)-1], EvidenceRefs: fieldValue(binding.EvidenceRefs), Limitations: fieldValue(binding.Limitations), Governance: participantOptionalString(fieldValue(binding.GovernanceRef))})
		}
		address := state.address(termParticipant, termOutcomeInterpretationRule, name)
		state.outcomes[address] = output
		state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: termOutcomeInterpretationRule, Payload: state.payload(output)})
	}
}
