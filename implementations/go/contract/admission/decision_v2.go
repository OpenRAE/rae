package admission

import (
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) decisionV2(i validation.Invocation) error {
	v, err := e.defaulted(termParticipantDecisionSurfaceV2, invocationRoot(i))
	if err != nil {
		return err
	}
	view, assurance, delivery := at(v, "participant_view"), at(v, "assurance"), at(v, termDelivery)
	if checkErr := decisionView(view); checkErr != nil {
		return checkErr
	}
	if !matchingFields(view, assurance, fieldParticipantAddress, fieldEpisodeID, "decision_epoch") {
		return invalid()
	}
	digest, err := jsonDigest(view)
	if err != nil {
		return err
	}
	if digest != stringAt(assurance, "participant_view_digest") {
		return invalid()
	}
	if !fieldsUnique(assurance, fieldEvidenceRefs, "provenance_refs") || (stringAt(assurance, "participant_memory_scope") == "episode_local_reset") != (at(assurance, "memory_reset_authority_ref") != nil) {
		return invalid()
	}
	anchor := at(assurance, "derivation_anchor")
	if err := decisionAnchor(anchor); err != nil {
		return err
	}
	if !matchingFields(anchor, assurance, fieldParticipantAddress, fieldEpisodeID, "decision_epoch") || !exposureCarried(anchor, assurance) {
		return invalid()
	}
	if checkErr := decisionBindingsV2(view, assurance, anchor); checkErr != nil {
		return checkErr
	}
	return decisionDeliveryV2(v, view, assurance, delivery)
}

func decisionCut(v any) error {
	if stringAt(v, "cut_kind") == termSequencePrefix {
		if !fieldsUnique(v, "predecessor_event_refs") || set(at(v, "predecessor_event_refs"))[stringAt(v, "anchor_event_ref")] {
			return invalid()
		}
		return require(numericSuccessor(at(v, "history_prefix_length"), at(v, "anchor_order")))
	}
	return require(fieldsUnique(v, "frontier_event_refs"))
}
func decisionAnchor(v any) error {
	if !fieldsUnique(v, fieldEvidenceRefs, "provenance_refs") || !set(at(v, "provenance_refs"))[stringAt(v, "event_ref")] {
		return invalid()
	}
	cut := at(v, "state_cut")
	if err := decisionCut(cut); err != nil {
		return err
	}
	readiness := stringAt(v, "anchor_kind") == "episode_readiness"
	if readiness && countAt(v, "decision_epoch") != 0 || !readiness && countAt(v, "decision_epoch") < 1 {
		return invalid()
	}
	if stringAt(cut, "cut_kind") == termSequencePrefix {
		domain := "participant_behavior_history"
		if readiness {
			domain = "participant_episode_lifecycle"
		}
		return require(equal(at(v, "event_ref"), at(cut, "anchor_event_ref")) && stringAt(cut, "history_domain") == domain)
	}
	return require(set(at(cut, "frontier_event_refs"))[stringAt(v, "event_ref")])
}

func decisionBindingsV2(view, assurance, anchor any) error {
	bindings := array(at(assurance, "exposure_bindings"))
	if len(rowSet(bindings, termItemRef)) != len(bindings) || !equalSet(rowSet(bindings, termItemRef), decisionExposed(view)) {
		return invalid()
	}
	for _, binding := range bindings {
		if err := exposureBasis(binding); err != nil {
			return err
		}
		if !matchingFields(binding, view, fieldParticipantAddress, fieldEpisodeID, "decision_epoch") || !matchingFields(binding, assurance, "audience_scope_ref", "projection_policy_ref", "projection_policy_revision", "projection_policy_decision_ref", "exposure_policy_ref") || !equal(at(binding, "decision_cut_ref"), at(anchor, "state_cut", "cut_ref")) || !exposureCarried(binding, assurance) {
			return invalid()
		}
	}

	return nil
}
func decisionDeliveryV2(v, view, assurance, delivery any) error {
	if (stringAt(v, "surface_state") == termDelivered) != (delivery != nil) {
		return invalid()
	}
	if delivery != nil {
		if !matchingFields(delivery, view, termSurfaceID, fieldParticipantAddress, fieldEpisodeID, "decision_epoch") || !equal(at(delivery, "participant_view_digest"), at(assurance, "participant_view_digest")) || !fieldsUnique(delivery, fieldEvidenceRefs, "provenance_refs", "limitations") {
			return invalid()
		}
		if stringAt(delivery, "delivery_basis") == statusUnknown || stringAt(delivery, "delivery_basis") == statusUnsupported {
			return invalid()
		}
	}
	return nil
}
