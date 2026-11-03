package admission

import (
	"slices"
	"strings"
)

func (e *Validator) backendManifestModel(v any) error {
	if err := e.manifestBindings(v, backendConceptScope); err != nil {
		return err
	}
	return backendManifestCoupling(v)
}
func backendConceptScope(scope string) bool {
	allowed := []string{
		"capabilities.provisioner.supported_node_types", "capabilities.provisioner.supported_os_families", "capabilities.provisioner.operating_systems.distribution", "capabilities.provisioner.supported_node_architectures", "capabilities.provisioner.supported_content_types", "capabilities.provisioner.supported_account_features", "capabilities.provisioner.supported_domain_profiles", "capabilities.provisioner.supported_service_materialization_profiles",
		"capabilities.orchestrator.supported_sections", "capabilities.evaluator.supported_sections", "capabilities.observation.supported_capture_kinds", "capabilities.observation.supported_channel_kinds", "capabilities.observation.supported_sealing_modes",
		"capabilities.participant_runtime.supported_participant_roles", "capabilities.participant_runtime.supported_behavior_features", "capabilities.participant_runtime.supported_interaction_features",
		"capabilities.time.supported_domain_kinds", "capabilities.time.supported_authority_kinds", "capabilities.time.supported_advancement_modes", "capabilities.time.supported_synchronization_modes", "capabilities.time.supported_constraint_kinds",
	}
	return slices.Contains(allowed, scope)
}

func manifestScopePresent(v any, scope string) bool {
	tokens := strings.Split(scope, ".")
	current := v
	for index, token := range tokens {
		if object(current) == nil {
			return false
		}
		child, present := object(current)[token]
		if index == len(tokens)-1 && !present {
			return true
		} // Governed terminal members have list factories.
		if child == nil {
			return false
		}
		current = child
	}
	return true
}
func (e *Validator) participantFeatureDeclaration(v any) error {
	feature := stringAt(v, "feature")
	return require((e.vocabularyTerm("participant-runtime-behavior-features", feature) || e.vocabularyTerm("participant-runtime-interaction-features", feature)) && fieldsUnique(v, "constraint_refs", "limitation_refs", "disclosure_refs", "evidence_refs"))
}
func participantEvidenceFeature(feature string) bool {
	switch feature {
	case "participant_declassification", "participant_directed_inject_delivery", "participant_egress_projection", "participant_ingress_admission", "participant_intervention", "participant_transformation", "participant_predicate_opacity", "participant_modular_control", "participant_boundary_flow_resolution", "participant_final_sink_mediation", "participant_quarantined_processing", "participant_processing_role_trust", "participant_monitor_topology", termToolAffordances, termScopedToolAffordances:
		return true
	default:
		return false
	}
}
func participantRuntimeFeatures(v any) error {
	declarations := array(at(v, "feature_support"))
	if len(rowSet(declarations, "feature")) != len(declarations) {
		return invalid()
	}
	supported := set(at(v, "supported_behavior_features"))
	for feature := range set(at(v, "supported_interaction_features")) {
		supported[feature] = true
	}
	declared := rowSet(declarations, "feature")
	for feature := range supported {
		if participantEvidenceFeature(feature) && !declared[feature] {
			return invalid()
		}
	}
	for _, entry := range declarations {
		feature := stringAt(entry, "feature")
		unsupported := stringAt(entry, "support_level") == statusUnsupported
		if unsupported && supported[feature] || participantEvidenceFeature(feature) && !unsupported && !supported[feature] {
			return invalid()
		}
	}
	return nil
}
func selectionDescriptorSet(selections []any) error {
	ids, points := map[string]bool{}, map[string]bool{}
	for _, selection := range selections {
		id := stringAt(selection, "selection_id")
		point := join(stringAt(selection, "target", "scenario_family_id"), stringAt(selection, "target", "variation_point_id"))
		if ids[id] || points[point] {
			return invalid()
		}
		ids[id], points[point] = true, true
	}
	return nil
}
