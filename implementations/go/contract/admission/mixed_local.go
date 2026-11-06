package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) mixedLocalRules() map[string]definition {
	return map[string]definition{
		"mixed-composition-root-local-graph-valid": {check: e.mixedCompositionLocal},
		"mixed-backend-local-consistency":          {check: mixedBackendLocal},
	}
}
func (e *Validator) mixedCompositionLocal(i validation.Invocation) error {
	v, err := e.defaulted(termMixedParticipantCompositionProfileV1, i.Instance)
	if err != nil {
		return err
	}
	if err = mixedIdentityMaps(v); err != nil {
		return err
	}
	if err = mixedPhases(v); err != nil {
		return err
	}
	if err = mixedMode(v); err != nil {
		return err
	}
	payload := maps.Clone(object(v))
	delete(payload, "profile_digest")
	digest, err := jsonDigest(payload)
	if err != nil {
		return err
	}
	return require(digest == stringAt(v, "profile_digest"))
}
func mixedIdentityMaps(v any) error {
	for section, field := range map[string]string{termComponents: "component_id", termAllocations: "allocation_id", termEdges: "edge_id", termPhases: "phase_id", termTransitions: "transition_id"} {
		if !keyed(at(v, section), field) {
			return invalid()
		}
	}
	identities := make([]string, 0, len(object(at(v, termComponents))))
	for _, component := range object(at(v, termComponents)) {
		identities = append(identities, stringAt(component, "apparatus_identity_ref"))
		if at(component, "manifest_ref", "ref_digest") == nil {
			return invalid()
		}
	}
	if !unique(identities) || stringAt(v, "scenario_snapshot_ref", fieldRefKind) != kindScenarioSnapshot || at(v, "scenario_snapshot_ref", "ref_digest") == nil || at(v, "scenario_snapshot_ref", "ref_path") != nil {
		return invalid()
	}
	for _, allocation := range object(at(v, termAllocations)) {
		if err := mixedAllocationRequirements(allocation); err != nil {
			return err
		}
	}
	return mixedGraphIdentities(v)
}

func mixedEvidenceUnique(v any) bool {
	return len(rowSet(at(v, "evidence_bindings"), "obligation_ref")) == len(array(at(v, "evidence_bindings")))
}
func mixedFeatureRequirement(v any) error {
	level, policy, provenance := at(v, "allowed_downgrade_level"), at(v, "downgrade_policy_ref"), at(v, "downgrade_provenance_ref")
	if level == nil && policy == nil && provenance == nil {
		return nil
	}
	if level == nil || policy == nil || provenance == nil {
		return invalid()
	}
	rank := map[string]int{statusUnsupported: 0, termDisclosedWeak: 1, assuranceBounded: 2, postureExact: 3}
	return require(text(level) != statusUnsupported && rank[text(level)] < rank[text(defaultMember(v, "required_level", postureExact))])
}
func mixedMode(v any) error {
	memberships := map[string]bool{}
	mixed := false
	for _, phase := range object(at(v, termPhases)) {
		ids := stringsOf(at(phase, "active_component_ids"))
		slices.Sort(ids)
		memberships[join(ids...)] = true
		forms := map[string]bool{}
		for _, id := range ids {
			forms[stringAt(v, termComponents, id, "realization_form")] = true
		}
		mixed = mixed || len(forms) >= 2
		if stringAt(v, "composition_mode") == "alternative" && len(ids) != 1 {
			return invalid()
		}
	}
	if stringAt(v, "federation_membership") == conditionFixed && len(memberships) != 1 {
		return invalid()
	}
	switch stringAt(v, "composition_mode") {
	case "alternative":
		return require(len(object(at(v, termComponents))) == 1 && len(object(at(v, termEdges))) == 0)
	case "simultaneous-mixed":
		return require(mixed)
	case "staged":
		return require(len(object(at(v, termPhases))) >= 2 && len(memberships) >= 2)
	default:
		return invalid()
	}
}

func mixedBackendLocal(i validation.Invocation) error {
	v := i.Instance
	if i.Key.ContractID == termMixedBackendStageReportV1 {
		if err := backendBinding(at(v, "binding")); err != nil {
			return err
		}
		stage := at(v, "stage")
		if !fieldsUnique(stage, fieldEvidenceRefs, "mapping_evidence_refs", "timing_evidence_refs", "mapping_loss_refs", "cessation_evidence_refs") {
			return invalid()
		}
		if stringAt(stage, "stage") != termExecution {
			return nil
		}
		status := stringAt(stage, "status")
		if (status == outcomeSucceeded || status == statusPartial) && len(array(at(stage, fieldEvidenceRefs))) == 0 {
			return invalid()
		}
		return require(status != outcomeFailed || len(array(at(stage, "cessation_evidence_refs"))) > 0)
	}
	return mixedBackendSubject(v)
}

func mixedAllocationRequirements(allocation any) error {
	if !fieldsUnique(allocation, "phase_ids") || len(rowSet(at(allocation, "feature_requirements"), "feature")) != len(array(at(allocation, "feature_requirements"))) {
		return invalid()
	}
	for _, requirement := range array(at(allocation, "feature_requirements")) {
		if err := mixedFeatureRequirement(requirement); err != nil {
			return err
		}
	}

	return nil
}

func mixedBackendSubject(v any) error {
	subject := at(v, "subject")
	kind := stringAt(subject, termKind)
	services := []any{at(subject, "time", "coordinator")}
	if kind == "edge" {
		if !equal(at(subject, "source_action_address"), at(subject, "destination_action_address")) {
			return invalid()
		}
		services = append(services, at(subject, "bridge"), at(subject, "delivery_reader"), at(subject, "observation_reader"))
	} else {
		if equal(at(subject, "source_component_id"), at(subject, "destination_component_id")) {
			return invalid()
		}
		services = append(services, at(subject, "transfer"), at(subject, "owner_reader"))
	}
	refs, digests := []string{}, []string{}
	for _, service := range services {
		if service != nil {
			refs = append(refs, stringAt(service, "service_ref"))
			digests = append(digests, stringAt(service, termDigest))
		}
	}
	return require(unique(refs) && unique(digests) && fieldsUnique(subject, "required_evidence_refs"))
}

func mixedGraphIdentities(v any) error {
	for _, edge := range object(at(v, termEdges)) {
		if equal(at(edge, "source_component_id"), at(edge, "target_component_id")) || !fieldsUnique(edge, "phase_ids") || !mixedEvidenceUnique(edge) {
			return invalid()
		}
	}
	for _, transition := range object(at(v, termTransitions)) {
		if equal(at(transition, "source_phase_id"), at(transition, "target_phase_id")) || !mixedEvidenceUnique(transition) {
			return invalid()
		}
	}
	return nil
}
