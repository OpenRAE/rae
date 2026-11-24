package admission

import (
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) participantLocalRules() map[string]definition {
	return map[string]definition{
		"manifest-reference-digest-scope-valid":               {check: manifestReference},
		"participant-control-occurrence-v2-acting-controller": {check: occurrenceActor},
		"participant-control-occurrence-v2-revision-advance": {check: func(i validation.Invocation) error {
			return occurrenceIncrement(i.Instance, "resulting_state_revision", termExpectedStateRevision)
		}},
		"participant-control-occurrence-v2-history-head": {check: func(i validation.Invocation) error {
			return occurrenceIncrement(i.Instance, "occurrence_revision", "expected_history_head")
		}},
		"participant-control-occurrence-v2-validity-bounds": {check: occurrenceBounds},
		"context-view-sem216-archival-source-mediated":      {check: contextMediated},
		"context-view-sem216-payload-not-raw-archival":      {check: contextPayload},
	}
}

func manifestReference(i validation.Invocation) error {
	v := i.Instance
	if at(v, "ref_path") != nil || at(v, "subject_ref", "ref_digest") != nil || at(v, "subject_ref", "ref_path") != nil {
		return invalid()
	}
	kind := stringAt(v, "subject_ref", fieldRefKind)
	if kind == kindProcessor || kind == kindBackend {
		if !equal(at(v, fieldRefID), at(v, "subject_ref", fieldRefID)) {
			return invalid()
		}
	}
	if at(v, "ref_digest") == nil {
		return nil
	}
	return require((kind == kindProcessor || kind == kindBackend) && stringAt(v, fieldRefVersion) == kind+manifestV2Suffix)
}

func occurrenceActor(i validation.Invocation) error {
	acting := at(i.Instance, "occurrence")
	if stringAt(acting, "disposition") == termRejected {
		acting = at(acting, "attempted")
	}
	return require(equal(at(i.Instance, "actor_ref"), at(acting, "controller_ref")))
}
func occurrenceIncrement(v any, successor, predecessor string) error {
	occurrence := at(v, "occurrence")
	if stringAt(occurrence, "disposition") != dispositionAccepted {
		return nil
	}
	next, ok := number(at(occurrence, successor))
	if !ok {
		return invalid()
	}
	previous, ok := number(at(occurrence, predecessor))
	if !ok {
		return invalid()
	}
	return require(next.Cmp(new(big.Rat).Add(previous, big.NewRat(1, 1))) == 0)
}
func occurrenceBounds(i validation.Invocation) error {
	occurrence := at(i.Instance, "occurrence")
	if stringAt(occurrence, "disposition") != dispositionAccepted {
		return nil
	}
	from, ok := number(at(occurrence, termValidFromOrder))
	if !ok {
		return invalid()
	}
	until, ok := number(at(occurrence, termValidUntilOrder))
	if !ok {
		return invalid()
	}
	order, ok := number(at(occurrence, "effective_order"))
	if !ok {
		return invalid()
	}
	return require(from.Cmp(order) <= 0 && order.Cmp(until) <= 0)
}
func archivalLayers(v any) []any {
	if stringAt(v, "audience_scope") != "participant_visible" {
		return nil
	}
	var result []any
	for _, layer := range array(at(v, "source_layers")) {
		if kind := stringAt(layer, "source_layer"); kind == "evidence_record" || kind == "derived_measure" {
			result = append(result, layer)
		}
	}
	return result
}
func contextMediated(i validation.Invocation) error {
	layers := archivalLayers(i.Instance)
	if len(layers) == 0 {
		return nil
	}
	if at(i.Instance, "derivation_basis_ref") == nil || at(i.Instance, "redaction_policy_ref") == nil {
		return invalid()
	}
	return require(subset(rowIDs(layers, termSourceID), set(at(i.Instance, termTransformation, "input_source_ids"))))
}
func contextPayload(i validation.Invocation) error {
	if at(i.Instance, "payload_ref") == nil {
		return nil
	}
	payload := stringAt(i.Instance, "payload_ref")
	for _, layer := range archivalLayers(i.Instance) {
		if payload == stringAt(layer, "ref") || set(at(layer, fieldEvidenceRefs))[payload] {
			return invalid()
		}
	}
	return nil
}
