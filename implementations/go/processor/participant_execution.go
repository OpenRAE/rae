package processor

import (
	"encoding/json"
	"maps"
	"slices"
)

func (state *compilerState) participantActionTargets(actionName string) []string {
	action := fieldValue(state.input.model.ActionContracts)[actionName]
	effects, supports := []string{}, []string{}
	for _, effect := range fieldValue(action.Effects) {
		effects = append(effects, fieldValue(effect.TargetRefs)...)
	}
	for _, condition := range fieldValue(action.Preconditions) {
		supports = append(supports, fieldValue(condition.SupportRefs)...)
	}
	return dedupe(append(state.runtimeAddressesFor(effects, "action-target"), state.runtimeAddresses(supports)...))
}

func (state *compilerState) participantExecutionBindings(policy participantExecutionSource, refs []string) ([]participantExecutionBinding, []string) {
	bindings := []participantExecutionBinding{}
	targets := []string{}
	seen := map[string]bool{}
	for _, ref := range refs {
		name := state.sectionName(ref, termActionContracts)
		address := state.address(termParticipant, termActionContract, name)
		if seen[address] {
			continue
		}
		seen[address] = true
		_, exists := fieldValue(state.input.model.ActionContracts)[name]
		if !exists {
			state.err = invalidCompiled()
			return nil, nil
		}
		output := participantExecutionBinding{ActionContractAddress: address, TargetAddresses: state.participantActionTargets(name), ParticipantImplementationRef: policy.ParticipantImplementationRef, MaxActionAttempts: policy.MaxActionAttempts, MaxInFlight: policy.MaxInFlight, InteractionClasses: []string{}, SharedStateRefs: []string{}, RelatedActionContractAddresses: []string{}, CommutativeSharedStateRefs: []string{}, CommutativeRelatedActionContractAddresses: []string{}, MergeRuleRefs: []string{}, SharedStateMergeRules: [][2]string{}, RelatedActionMergeRules: [][2]string{}}
		state.compileExecutionInteractions(name, &output)
		output.uniqueTerms()
		bindings = append(bindings, output)
		targets = append(targets, output.TargetAddresses...)
	}
	return bindings, dedupe(targets)
}

func (state *compilerState) compileExecutionInteractions(name string, output *participantExecutionBinding) {
	action := fieldValue(state.input.model.ActionContracts)[name]
	for _, interaction := range fieldValue(action.Interactions) {
		output.InteractionClasses = append(output.InteractionClasses, string(fieldValue(interaction.InteractionClass)))
		shared := fieldValue(interaction.SharedStateRefs)
		related := []string{}
		for _, actionRef := range fieldValue(interaction.RelatedActions) {
			related = append(related, state.address(termParticipant, termActionContract, state.sectionName(actionRef, termActionContracts)))
		}
		output.SharedStateRefs = append(output.SharedStateRefs, shared...)
		output.RelatedActionContractAddresses = append(output.RelatedActionContractAddresses, related...)
		if fieldValue(interaction.Commutative) {
			output.CommutativeSharedStateRefs = append(output.CommutativeSharedStateRefs, shared...)
			output.CommutativeRelatedActionContractAddresses = append(output.CommutativeRelatedActionContractAddresses, related...)
		}
		if rule := rawString(fieldValue(interaction.MergeRuleRef)); rule != "" {
			output.MergeRuleRefs = append(output.MergeRuleRefs, rule)
			for _, ref := range shared {
				output.SharedStateMergeRules = append(output.SharedStateMergeRules, [2]string{ref, rule})
			}
			for _, ref := range related {
				output.RelatedActionMergeRules = append(output.RelatedActionMergeRules, [2]string{ref, rule})
			}
		}
	}
}
func (output *participantExecutionBinding) uniqueTerms() {
	output.InteractionClasses = dedupe(output.InteractionClasses)
	output.SharedStateRefs = dedupe(output.SharedStateRefs)
	output.RelatedActionContractAddresses = dedupe(output.RelatedActionContractAddresses)
	output.CommutativeSharedStateRefs = dedupe(output.CommutativeSharedStateRefs)
	output.CommutativeRelatedActionContractAddresses = dedupe(output.CommutativeRelatedActionContractAddresses)
	output.MergeRuleRefs = dedupe(output.MergeRuleRefs)
	output.SharedStateMergeRules = uniquePairs(output.SharedStateMergeRules)
	output.RelatedActionMergeRules = uniquePairs(output.RelatedActionMergeRules)
}

func uniquePairs(input [][2]string) [][2]string {
	result := make([][2]string, 0, len(input))
	seen := map[[2]string]bool{}
	for _, pair := range input {
		if !seen[pair] {
			seen[pair] = true
			result = append(result, pair)
		}
	}
	return result
}

func (state *compilerState) compileAutonomous(name string, participants []string, raw json.RawMessage) *participantAutonomous {
	if len(raw) == 0 || string(raw) == termNull {
		return nil
	}
	var source participantExecutionSource
	if err := json.Unmarshal(raw, &source); err != nil {
		state.err = invalidCompiled()
		return nil
	}
	refs := nonNilStrings(source.ActionOrder)
	candidateIDs := slices.Sorted(maps.Keys(source.ActionCandidates))
	if len(candidateIDs) > 0 {
		refs = []string{}
		for _, id := range candidateIDs {
			refs = append(refs, source.ActionCandidates[id].ActionRef)
		}
	}
	profile := source.Profile
	if profile == "" {
		profile = "participant-autonomous-execution/v1"
	}
	constraints := source.TemporalConstraintRefs
	if profile == "participant-autonomous-execution/v2" || profile == termParticipantAutonomousExecutionV3 {
		constraints = append(slices.Clone(source.WorkWindowRefs), source.PauseWindowRefs...)
	}
	bindings, targets := state.participantExecutionBindings(source, refs)
	owners, demands, fairness := state.participantBudget(source, participants)
	boundaryName := state.sectionName(source.ObservationBoundaryRef, termObservationBoundaries)
	boundary := fieldValue(state.input.model.ObservationBoundaries)[boundaryName]
	authority := source.EvaluationAuthority
	output := &participantAutonomous{Address: state.address(termParticipant, "autonomous-execution", name), Name: name, Spec: raw, OrderingDependencies: []string{}, RefreshDependencies: slices.Clone(participants), BehaviorSpecificationAddress: state.address(termParticipant, termBehaviorSpecification, name), ParticipantAddresses: participants, ParticipantImplementationRef: source.ParticipantImplementationRef, ClockAddress: state.address("time", "clock", state.sectionName(source.ClockRef, "clocks")), ProgressionPolicyAddress: state.address("time", "policy", state.sectionName(source.ProgressionPolicyRef, "time_progression_policies")), TemporalConstraintAddresses: state.timeConstraintAddresses(constraints), ActionContractAddresses: []string{}, TargetAddresses: targets, ExecutionBindings: bindings, ObservationBoundaryAddress: state.address(termParticipant, termObservationBoundary, boundaryName), ObservationBoundaryEvidenceRefs: nonNilStrings(fieldValue(boundary.EvidenceRefs)), SelectionStrategy: source.SelectionStrategy, MaxActionAttempts: source.MaxActionAttempts, MaxInFlight: source.MaxInFlight, FailurePolicy: source.FailurePolicy, EvaluationAuthorityMode: authority.Mode, ObjectiveRefs: []string{}, ProofProducerRefs: nonNilStrings(authority.ProofProducerRefs), ScoreAuthorityRefs: nonNilStrings(authority.ScoreAuthorityRefs), ReceiptAuthorityRefs: nonNilStrings(authority.ReceiptAuthorityRefs), Profile: profile, WorkWindowAddresses: state.timeConstraintAddresses(source.WorkWindowRefs), PauseWindowAddresses: state.timeConstraintAddresses(source.PauseWindowRefs), StochasticControlRef: source.StochasticControlRef, TimingMinimumTicks: "0", TimingMaximumTicks: "0", OutsideWindowDisposition: source.OutsideWindowDisposition, EmptyEligibleDisposition: source.EmptyEligibleDisposition, ActionCandidateIDs: nonNilStrings(candidateIDs), ActionCandidateWeights: []json.Number{}, ActionCandidateDependencies: [][]string{}, ActionCandidateRetryFailureClasses: [][]string{}, ActionCandidateMaxRetries: []json.Number{}, ActionCandidateCooldownTicks: []json.Number{}, MaxOccurrences: numberDefault(source.MaxOccurrences, "0"), MaxBurstSize: numberDefault(source.MaxBurstSize, "1"), ResourceOwners: owners, ResourceDemands: demands, ResourceFairness: fairness, TemporalBindings: state.participantTemporalBindings(refs), InvocationToolBindings: []participantInvocationTool{}}
	for _, ref := range refs {
		output.ActionContractAddresses = append(output.ActionContractAddresses, state.address(termParticipant, termActionContract, state.sectionName(ref, termActionContracts)))
	}
	for _, ref := range authority.ObjectiveRefs {
		output.ObjectiveRefs = append(output.ObjectiveRefs, state.address(termEvaluation, termObjective, state.sectionName(ref, termObjectives)))
	}
	output.RefreshDependencies = append(output.RefreshDependencies, output.ActionContractAddresses...)
	output.RefreshDependencies = append(output.RefreshDependencies, output.ObjectiveRefs...)
	output.RefreshDependencies = append(output.RefreshDependencies, targets...)
	if source.Timing != nil {
		output.TimingMinimumTicks, output.TimingMaximumTicks = source.Timing.MinimumTicks, source.Timing.MaximumTicks
	}
	for _, id := range candidateIDs {
		candidate := source.ActionCandidates[id]
		output.ActionCandidateWeights = append(output.ActionCandidateWeights, candidate.Weight)
		output.ActionCandidateDependencies = append(output.ActionCandidateDependencies, nonNilStrings(candidate.DependsOn))
		output.ActionCandidateRetryFailureClasses = append(output.ActionCandidateRetryFailureClasses, nonNilStrings(candidate.RetryableFailureClasses))
		output.ActionCandidateMaxRetries = append(output.ActionCandidateMaxRetries, candidate.MaxRetries)
		output.ActionCandidateCooldownTicks = append(output.ActionCandidateCooldownTicks, candidate.CooldownTicks)
	}
	return output
}

func (state *compilerState) participantInvocationTools(policy *participantAutonomous) []participantInvocationTool {
	result := []participantInvocationTool{}
	source := participantExecutionSource{ParticipantImplementationRef: policy.ParticipantImplementationRef, MaxActionAttempts: policy.MaxActionAttempts, MaxInFlight: policy.MaxInFlight}
	for _, address := range slices.Sorted(maps.Keys(state.tools)) {
		tool := state.tools[address]
		if tool.BehaviorSpecificationAddress != policy.BehaviorSpecificationAddress {
			continue
		}
		participants := invocationToolParticipants(policy.ParticipantAddresses, tool.ParticipantAddresses)
		if len(participants) == 0 {
			continue
		}
		for _, action := range tool.ActionContractAddresses {
			binding := state.participantInvocationToolAction(source, tool, action, address, participants)
			if state.err != nil {
				return nil
			}
			if binding != nil {
				result = append(result, *binding)
			}
		}
	}
	return result
}

func invocationToolParticipants(policy, tool []string) []string {
	result := []string{}
	for _, participant := range policy {
		if len(tool) == 0 || slices.Contains(tool, participant) {
			result = append(result, participant)
		}
	}
	return result
}

func (state *compilerState) participantInvocationToolAction(source participantExecutionSource, tool participantTool, action, address string, participants []string) *participantInvocationTool {
	ref := state.actions[action].ActionName
	if ref == "" {
		return nil
	}
	bindings, targets := state.participantExecutionBindings(source, []string{ref})
	if len(bindings) != 1 {
		state.err = invalidCompiled()
		return nil
	}
	pairs := []participantEvidencePair{}
	for _, boundary := range tool.ObservationBoundaryAddresses {
		pairs = append(pairs, participantEvidencePair{boundary, nonNilStrings(state.boundaries[boundary].EvidenceRefs)})
	}
	return &participantInvocationTool{ToolAffordanceAddress: address, ToolAddress: tool.ToolAddress, ActionContractAddress: action, ObservationBoundaryAddresses: tool.ObservationBoundaryAddresses, ParticipantAddresses: participants, TargetAddresses: targets, SharedTimeBound: len(state.participantTemporalBindings([]string{ref})) > 0, ObservationBoundaryEvidenceRefs: pairs, Interaction: &bindings[0]}
}
