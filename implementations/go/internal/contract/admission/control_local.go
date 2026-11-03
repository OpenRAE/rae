package admission

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) controlLocalRules() map[string]definition {
	return map[string]definition{
		"participant-control-occurrence-not-lifecycle-evidence": {check: controlOccurrenceLocal},
		"participant-crossing-stage-separation":                 {check: crossingLocal},
		"participant-control-selection-graph":                   {check: e.controlSelection},
	}
}
func effectiveInterval(v any) bool {
	return !numericGreater(at(v, termValidFromOrder), at(v, termValidUntilOrder)) && !numericGreater(at(v, termValidFromOrder), at(v, "effective_order")) && !numericGreater(at(v, "effective_order"), at(v, termValidUntilOrder))
}
func controlOccurrenceLocal(i validation.Invocation) error {
	v := at(i.Instance, "occurrence")
	if !fieldsUnique(v, "authority_basis_refs", "controlled_scope_refs", "limitation_refs") || !effectiveInterval(v) {
		return invalid()
	}
	switch stringAt(v, termKind) {
	case termProposal:
		if (at(v, "payload_ref") == nil) == (at(v, "payload_digest") == nil) {
			return invalid()
		}
		count := 0
		for _, field := range []string{"source_proposal_ref", "source_proposal_revision", termTransformationRef} {
			if at(v, field) != nil {
				count++
			}
		}
		return require((count == 0 || count == 3) && !equal(at(v, "source_proposal_ref"), at(v, "proposal_id")))
	case termHandoff:
		return require(numericSuccessor(at(v, "resulting_state_revision"), at(v, termExpectedStateRevision)))
	default:
		return nil
	}
}
func crossingLocal(i validation.Invocation) error {
	root := i.Instance
	v := at(root, "occurrence")
	policy := at(v, termPolicy)
	if !matchingFields(root, at(v, "subject"), fieldParticipantAddress, fieldEpisodeID) || !fieldsUnique(v, "authority_basis_refs", "loss_and_limitations", "required_evidence_refs") || !effectiveInterval(policy) {
		return invalid()
	}
	if numericGreater(at(policy, termValidFromOrder), at(v, "effective_order")) || numericGreater(at(v, "effective_order"), at(policy, termValidUntilOrder)) || numericGreater(at(policy, "effective_order"), at(v, "effective_order")) {
		return invalid()
	}
	switch stringAt(v, "stage") {
	case termDecided:
		return crossingDecision(v)
	case termTransformed:
		if matchingFields(at(v, "source_subject"), at(v, "result_subject"), "subject_kind", "subject_ref") || !equal(at(v, "subject"), at(v, "result_subject")) {
			return invalid()
		}
		return crossingMarkings(v)
	case termDisclosed:
		return crossingMarkings(v)
	case termAudited:
		return require(fieldsUnique(v, "retained_evidence_refs"))
	default:
		return nil
	}
}
func crossingDecision(v any) error {
	failed, unresolved := false, false
	for _, value := range object(at(v, "gates")) {
		failed = failed || text(value) == termDeny
		unresolved = unresolved || text(value) == statusUnknown || text(value) == statusUnsupported
	}
	disposition := stringAt(v, "disposition")
	if (disposition == termPermit || disposition == termTransform) && (failed || unresolved) || disposition == termDeny && !failed || disposition == statusUnsupported && !unresolved {
		return invalid()
	}
	if disposition == termTransform {
		return require(slices.Contains([]string{"projection", "masking", termRedaction, termTransformation, termDeclassification}, stringAt(v, "required_operation")))
	}
	return require(at(v, "required_operation") == nil)
}
func crossingMarkings(v any) error {
	if (stringAt(v, "operation") == termDeclassification) != (at(v, "declassification_basis_ref") != nil) {
		return invalid()
	}
	return require(at(v, "declassification_basis_ref") != nil || subset(stringsOf(at(v, "source_marking_refs")), set(at(v, "result_marking_refs"))))
}
