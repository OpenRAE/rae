package processor

import (
	"encoding/json"
	"maps"
	"slices"
)

type participantDeliverySource struct {
	ParticipantRef string `json:"participant_ref"`
	InjectRef      string `json:"inject_ref"`
	Occurrence     struct {
		EventRef  string `json:"event_ref"`
		ScriptRef string `json:"script_ref"`
		StoryRef  string `json:"story_ref"`
	} `json:"occurrence"`
	SourceItemRef          string `json:"source_item_ref"`
	ResultItemRef          string `json:"result_item_ref"`
	ObservationBoundaryRef string `json:"observation_boundary_ref"`
	DeliveryKind           string `json:"delivery_kind"`
	DeliveryPolicy         struct {
		PolicyRef          string `json:"policy_ref"`
		PolicyRevision     string `json:"policy_revision"`
		ExposurePolicyRef  string `json:"exposure_policy_ref"`
		AudienceScopeRef   string `json:"audience_scope_ref"`
		VisibilityBasisRef string `json:"visibility_basis_ref"`
		DisclosureBasisRef string `json:"disclosure_basis_ref"`
	} `json:"delivery_policy"`
	OrderBasis                string       `json:"order_basis"`
	TemporalConstraintRefs    []string     `json:"temporal_constraint_refs"`
	EvidenceRequirementRefs   []string     `json:"evidence_requirement_refs"`
	FailureDisposition        string       `json:"failure_disposition"`
	ControlTransitionRef      *string      `json:"control_transition_ref"`
	ControllerRef             *string      `json:"controller_ref"`
	ControlAuthorityScopeRefs []string     `json:"control_authority_scope_refs"`
	ControlEffectiveOrder     *json.Number `json:"control_effective_order"`
	ControlValidFromOrder     *json.Number `json:"control_valid_from_order"`
	ControlValidUntilOrder    *json.Number `json:"control_valid_until_order"`
	ControlEvidenceRefs       []string     `json:"control_evidence_refs"`
	Control                   *struct {
		Semantics              string   `json:"semantics"`
		PolicyRevision         string   `json:"policy_revision"`
		PermittedTransitionRef string   `json:"permitted_transition_ref"`
		ControllerRef          string   `json:"controller_ref"`
		AuthorityScopeRefs     []string `json:"authority_scope_refs"`
		EvidenceRefs           []string `json:"evidence_refs"`
	} `json:"control"`
}

func (state *compilerState) timeConstraintAddresses(refs []string) []string {
	result := []string{}
	for _, ref := range refs {
		result = append(result, state.address("time", "constraint", state.sectionName(ref, "temporal_constraints")))
	}
	return result
}

func (state *compilerState) compileParticipantDeliveries() {
	state.deliveries = map[string]participantDelivery{}
	specifications := fieldValue(state.input.model.BehaviorSpecifications)
	for _, name := range orderedNames(specifications, state.names(termBehaviorSpecifications)) {
		bindings := fieldValue(specifications[name].ParticipantInjectDeliveries)
		for _, id := range slices.Sorted(maps.Keys(bindings)) {
			var source participantDeliverySource
			if err := json.Unmarshal(bindings[id], &source); err != nil {
				state.err = invalidCompiled()
				return
			}
			state.compileParticipantDelivery(name, id, bindings[id], source)
		}
	}
}

func (state *compilerState) compileParticipantDelivery(name, id string, raw json.RawMessage, source participantDeliverySource) {
	address := state.mixedAddress(name, "inject-delivery", id)
	sourceItems := state.runtimeAddressesFor([]string{source.SourceItemRef}, "targetable")
	resultItems := state.runtimeAddressesFor([]string{source.ResultItemRef}, "targetable")
	invalid := false
	for _, item := range []struct {
		name      string
		addresses []string
	}{{"source_item_ref", sourceItems}, {"result_item_ref", resultItems}} {
		if len(item.addresses) != 1 {
			state.model.Diagnostics = append(state.model.Diagnostics, compileDiagnostic("participant.inject-delivery-item-unaddressable", termParticipant, address, "Delivery "+item.name+" must project to exactly one runtime address; no delivery is compiled."))
			invalid = true
		}
	}
	if invalid {
		return
	}
	policy := source.DeliveryPolicy
	output := participantDelivery{Name: id, Spec: raw, BindingID: id, BehaviorSpecificationAddress: state.address(termParticipant, termBehaviorSpecification, name), ParticipantAddress: state.address(termParticipant, "behavior", state.sectionName(source.ParticipantRef, "agents")), InjectAddress: state.address(termOrchestration, termInject, state.sectionName(source.InjectRef, termInjects)), EventAddress: state.address(termOrchestration, termEvent, state.sectionName(source.Occurrence.EventRef, termEvents)), ScriptAddress: state.address(termOrchestration, termScript, state.sectionName(source.Occurrence.ScriptRef, termScripts)), StoryAddress: state.address(termOrchestration, termStory, state.sectionName(source.Occurrence.StoryRef, termStories)), SourceItemRef: source.SourceItemRef, SourceItemAddress: sourceItems[0], ResultItemRef: source.ResultItemRef, ResultItemAddress: resultItems[0], ObservationBoundaryAddress: state.address(termParticipant, termObservationBoundary, state.sectionName(source.ObservationBoundaryRef, termObservationBoundaries)), DeliveryKind: source.DeliveryKind, PolicyRef: policy.PolicyRef, PolicyRevision: policy.PolicyRevision, ExposurePolicyRef: policy.ExposurePolicyRef, AudienceScopeRef: policy.AudienceScopeRef, VisibilityBasisRef: policy.VisibilityBasisRef, DisclosureBasisRef: policy.DisclosureBasisRef, OrderBasis: source.OrderBasis, TemporalConstraintAddresses: state.timeConstraintAddresses(source.TemporalConstraintRefs), EvidenceRequirementAddresses: []string{}, FailureDisposition: source.FailureDisposition, ControlAuthorityScopeRefs: nonNilStrings(source.ControlAuthorityScopeRefs), ControlAuthorityScopeAddresses: []string{}, ControlEffectiveOrder: source.ControlEffectiveOrder, ControlValidFromOrder: source.ControlValidFromOrder, ControlValidUntilOrder: source.ControlValidUntilOrder, ControlEvidenceRefs: nonNilStrings(source.ControlEvidenceRefs), ControlEvidenceAddresses: []string{}}
	for _, ref := range source.EvidenceRequirementRefs {
		output.EvidenceRequirementAddresses = append(output.EvidenceRequirementAddresses, state.address("sdl", "evidence-requirements", state.sectionName(ref, "evidence_requirements")))
	}
	ordering := []string{output.InjectAddress, output.EventAddress, output.ScriptAddress, output.StoryAddress}
	dependencies := []string{output.BehaviorSpecificationAddress, output.ParticipantAddress}
	dependencies = append(dependencies, ordering...)
	dependencies = append(dependencies, output.SourceItemAddress, output.ResultItemAddress, output.ObservationBoundaryAddress)
	dependencies = append(dependencies, output.TemporalConstraintAddresses...)
	dependencies = append(dependencies, output.EvidenceRequirementAddresses...)
	if source.ControlTransitionRef != nil {
		output.ControlTransitionAddress = state.mixedAddress(name, "control-transition", *source.ControlTransitionRef)
		output.ControllerAddress = output.ParticipantAddress
		if source.ControllerRef != nil && *source.ControllerRef != termSelf {
			output.ControllerAddress = state.address(termParticipant, "behavior", state.sectionName(*source.ControllerRef, "agents"))
		}
		output.ControlAuthorityScopeAddresses = state.runtimeAddressesFor(source.ControlAuthorityScopeRefs, "authority-scope")
		output.ControlEvidenceAddresses = state.runtimeAddressesFor(source.ControlEvidenceRefs, "targetable")
		dependencies = append(dependencies, output.ControlTransitionAddress, output.ControllerAddress)
		dependencies = append(dependencies, output.ControlAuthorityScopeAddresses...)
		dependencies = append(dependencies, output.ControlEvidenceAddresses...)
	}
	if control := source.Control; control != nil {
		controller := output.ParticipantAddress
		if control.ControllerRef != termSelf {
			controller = state.address(termParticipant, "behavior", state.sectionName(control.ControllerRef, "agents"))
		}
		output.Control = &participantDeliveryControl{Semantics: control.Semantics, PolicyRevision: control.PolicyRevision, PermittedTransitionAddress: state.mixedAddress(name, "permitted-transition", control.PermittedTransitionRef), ControllerAddress: controller, AuthorityScopeRefs: nonNilStrings(control.AuthorityScopeRefs), AuthorityScopeAddresses: state.runtimeAddressesFor(control.AuthorityScopeRefs, "authority-scope"), EvidenceRefs: nonNilStrings(control.EvidenceRefs), EvidenceAddresses: state.runtimeAddressesFor(control.EvidenceRefs, "targetable")}
		dependencies = append(dependencies, output.Control.PermittedTransitionAddress, output.Control.ControllerAddress)
		dependencies = append(dependencies, output.Control.AuthorityScopeAddresses...)
		dependencies = append(dependencies, output.Control.EvidenceAddresses...)
	}
	if state.deliveries == nil {
		state.deliveries = map[string]participantDelivery{}
	}
	state.deliveries[address] = output
	state.model.ParticipantResources = append(state.model.ParticipantResources, Resource{Address: address, Name: id, Domain: termParticipant, Kind: "participant-inject-delivery", OrderingDependencies: ordering, RefreshDependencies: dedupe(dependencies), Payload: state.payload(output)})
}
