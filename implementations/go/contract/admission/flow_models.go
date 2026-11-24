package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func flowCanonical(v any, fields ...string) error {
	for _, field := range fields {
		if !sortedUnique(stringsOf(at(v, field))) {
			return invalid()
		}
	}
	return nil
}

func flowModel(name string, v any) (bool, error) {
	switch name {
	case "ParticipantEffectiveFlowLabelModel":
		return true, flowCanonical(v, "confidentiality_obligation_refs", "integrity_obligation_refs", "provenance_refs", "influence_refs", "evidence_refs")
	case "ParticipantFlowNonInfluenceAssertionModel":
		return true, flowCanonical(v, "excluded_input_refs", "evidence_refs")
	case "ParticipantFlowDerivationModel":
		if err := flowCanonical(v, "predecessor_refs", "provenance_refs", "influence_refs", "evidence_refs"); err != nil {
			return true, err
		}
		return true, flowInputOrder(v)
	case "ParticipantFlowDeclassificationModel", "ParticipantFlowEndorsementModel":
		if err := flowCanonical(v, "predecessor_refs", "evidence_refs", "limitation_refs"); err != nil {
			return true, err
		}
		if stringAt(v, termKind) == termDeclassification {
			return true, flowCanonical(v, "removed_confidentiality_obligation_refs")
		}
		return true, require(flowOrderedRows(at(v, "integrity_obligation_replacements"), "source_obligation_ref", "result_obligation_ref") && len(rowSet(at(v, "integrity_obligation_replacements"), "source_obligation_ref")) == len(array(at(v, "integrity_obligation_replacements"))))
	case "ParticipantFlowSinkDecisionModel":
		if err := flowCanonical(v, "release_refs", "expected_history_head_refs", "evidence_refs", "limitation_refs"); err != nil {
			return true, err
		}
		return true, require(stringAt(v, "final_disposition") != termPermit || flowDisposition(stringAt(v, "confidentiality_result"), stringAt(v, "integrity_result")) == termPermit)
	case "ParticipantRuntimeFactFlowBindingModel", "ParticipantActionArgumentFlowBindingModel", "ParticipantControlOccurrenceFlowBindingModel", "ParticipantCrossingOccurrenceFlowBindingModel":
		return true, flowCarrierLocal(v)
	default:
		return false, nil
	}
}

func flowInputOrder(v any) error {
	if !flowOrderedRows(at(v, "inputs"), "subject/subject_kind", "subject/subject_ref", "label_ref") {
		return invalid()
	}
	for _, input := range array(at(v, "inputs")) {
		if set(at(v, "non_influence_assertion", "excluded_input_refs"))[stringAt(input, "subject", "subject_ref")] {
			return invalid()
		}
	}
	return nil
}

func flowOrderedRows(rows any, fields ...string) bool {
	var previous []string
	for _, row := range array(rows) {
		key := make([]string, len(fields))
		for index, field := range fields {
			key[index] = stringAt(row, strings.Split(field, "/")...)
		}
		if previous != nil && flowCompareTuple(previous, key) >= 0 {
			return false
		}
		previous = key
	}
	return true
}

func flowCompareTuple(a, b []string) int {
	for index := range a {
		if comparison := strings.Compare(a[index], b[index]); comparison != 0 {
			return comparison
		}
	}
	return 0
}

func flowCarrierLocal(v any) error {
	if err := flowCanonical(v, "crossing_refs", "memory_predecessor_refs"); err != nil {
		return err
	}
	cross := !equal(at(v, "source_participant_address"), at(v, "target_participant_address")) || !equal(at(v, "source_episode_id"), at(v, "target_episode_id"))
	if cross && (len(array(at(v, "crossing_refs"))) == 0 || len(array(at(v, "memory_predecessor_refs"))) == 0) {
		return invalid()
	}
	switch stringAt(v, termKind) {
	case "participant-control":
		return flowCanonical(v, termAuthorityBasisRefs, "related_occurrence_refs", "predecessor_event_refs")
	case termParticipantCrossing:
		if at(v, "subject_revision") == nil && at(v, "subject_digest") == nil {
			return invalid()
		}
		return flowCanonical(v, "related_stage_refs", "predecessor_event_refs")
	default:
		return nil
	}
}

func flowDisposition(values ...string) string {
	seen := map[string]bool{}
	for _, value := range values {
		seen[value] = true
	}
	for _, candidate := range []string{termDeny, statusUnsupported, termStale} {
		if seen[candidate] {
			return candidate
		}
	}
	if seen[termUnresolved] || seen[statusUnknown] || seen["ambiguous"] {
		return termUnresolved
	}
	return termPermit
}

func (e *Validator) flowLocalInstances(id string, root any) error {
	value, err := e.defaulted(id, root)
	if err != nil {
		return err
	}
	return flowRelation(value)
}

// Keep the model dispatcher aligned with the compiled schema names.
func flowNeedsDefaults(instance validation.SchemaInstance) bool {
	name := strings.TrimPrefix(instance.SchemaPointer, schemaDefinitionsPrefix)
	return strings.HasPrefix(name, "ParticipantFlow") || name == "ParticipantEffectiveFlowLabelModel" || name == "ParticipantRuntimeFactFlowBindingModel" || name == "ParticipantActionArgumentFlowBindingModel" || name == "ParticipantControlOccurrenceFlowBindingModel" || name == "ParticipantCrossingOccurrenceFlowBindingModel"
}
