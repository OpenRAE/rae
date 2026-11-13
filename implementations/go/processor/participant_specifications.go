package processor

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func (state *compilerState) compileBehaviorSpecifications() {
	specifications := fieldValue(state.input.model.BehaviorSpecifications)
	state.specifications = map[string]participantSpecification{}
	findings := []diagnostic.Diagnostic{}
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		source := specifications[name]
		address := state.address(termParticipant, termBehaviorSpecification, name)
		participants, local := state.selectParticipants(participantSelector{fieldValue(source.ParticipantRefs), fieldValue(source.ParticipantRoleRefs)}, address, false)
		findings = append(findings, local...)
		actions, local := state.participantReferences(fieldValue(source.ActionContractRefs), termActionContracts, termActionContract, address, "participant.behavior-specification-action-contract-ref-unbound", "participant action contract")
		findings = append(findings, local...)
		observations, local := state.participantReferences(fieldValue(source.ObservationBoundaryRefs), termObservationBoundaries, termObservationBoundary, address, "participant.behavior-specification-observation-boundary-ref-unbound", "participant observation boundary")
		findings = append(findings, local...)
		outcomes, local := state.participantReferences(fieldValue(source.OutcomeInterpretationRuleRefs), termOutcomeInterpretationRules, termOutcomeInterpretationRule, address, "participant.behavior-specification-outcome-rule-ref-unbound", "participant outcome interpretation rule")
		findings = append(findings, local...)
		scope := state.runtimeAddressesFor(fieldValue(source.AuthorityScopeRefs), "authority-scope")
		mixed := state.compileMixed(name, fieldValue(source.MixedControl))
		findings = append(findings, mixed.diagnostics...)
		context := state.contextByOwner["behavior_specifications."+name]
		if context == nil {
			context = []controlContextSelection{}
		}
		output := participantSpecification{Name: name, Spec: state.participantSpecificationSource(name), ControlContext: context, SpecName: name, SemanticVersion: fieldValue(source.SemanticVersion), LifecycleState: string(fieldValue(source.LifecycleState)), ParticipantAddresses: participants, ParticipantRoleRefs: nonNilStrings(fieldValue(source.ParticipantRoleRefs)), ActionContractAddresses: actions, ObservationBoundaryAddresses: observations, OutcomeInterpretationRuleAddresses: outcomes, AuthorityScopeRefs: nonNilStrings(fieldValue(source.AuthorityScopeRefs)), AuthorityScopeAddresses: scope, BehaviorMode: rawString(fieldValue(source.BehaviorMode)), AutonomousExecution: state.compileAutonomous(name, participants, fieldValue(source.AutonomousExecution)), MixedControlParticipantAddress: mixed.participant, MixedControlPolicyRevision: mixed.revision, MixedControlOrderStrategy: mixed.order, MixedControlInitialStateAddress: mixed.initial, MixedControlDispositions: mixed.dispositions, ControllerStates: mixed.states, ControlTransitions: mixed.transitions, MixedControlSemantics: mixed.semantics, MixedControlPolicy: mixed.policy, RealizationProfileRef: rawString(fieldValue(source.RealizationProfileRef)), BackendFeatureSupportRefs: nonNilStrings(fieldValue(source.BackendFeatureSupportRefs)), EvidenceContractRefs: nonNilStrings(fieldValue(source.EvidenceContractRefs)), ToolAffordanceAddresses: []string{}, ParticipantInjectDeliveryAddresses: []string{}, ExtensionPolicy: fieldValue(source.ExtensionPolicy), ExtensionKeys: nonNilStrings(slices.Sorted(maps.Keys(fieldValue(source.Extensions))))}
		for _, id := range slices.Sorted(maps.Keys(fieldValue(source.ToolAffordances))) {
			output.ToolAffordanceAddresses = append(output.ToolAffordanceAddresses, state.mixedAddress(name, "tool-affordance", id))
		}
		for _, id := range slices.Sorted(maps.Keys(fieldValue(source.ParticipantInjectDeliveries))) {
			output.ParticipantInjectDeliveryAddresses = append(output.ParticipantInjectDeliveryAddresses, state.mixedAddress(name, "inject-delivery", id))
		}
		dependencies := slices.Clone(participants)
		for _, refs := range [][]string{actions, observations, outcomes, scope, mixed.dependencies} {
			dependencies = append(dependencies, refs...)
		}
		state.specifications[address] = output
		state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: name, Domain: termParticipant, Kind: termBehaviorSpecification, OrderingDependencies: []string{}, RefreshDependencies: dedupe(dependencies), Payload: state.payload(output)})
	}
	state.addDiagnostics(findings)
}

func (state *compilerState) joinParticipantTools() {
	for i := range state.model.ParticipantResources {
		resource := &state.model.ParticipantResources[i]
		if resource.Kind != termBehaviorSpecification {
			continue
		}
		output := state.specifications[resource.Address]
		if output.AutonomousExecution == nil {
			continue
		}
		output.AutonomousExecution.InvocationToolBindings = state.participantInvocationTools(output.AutonomousExecution)
		state.specifications[resource.Address] = output
		resource.Payload = state.payload(output)
	}
}
