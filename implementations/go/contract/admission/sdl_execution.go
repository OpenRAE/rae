package admission

import (
	"slices"
	"unicode/utf8"
)

func sdlEvaluationAuthority(v any) error {
	fields := []string{"objective_refs", "proof_producer_refs", "score_authority_refs", "receipt_authority_refs"}
	if !nonblankSDLRefs(v, fields...) {
		return invalid()
	}
	count := 0
	for _, field := range fields {
		count += len(array(at(v, field)))
	}
	return require((stringAt(v, "mode") == assuranceDeclared) == (count > 0))
}
func sdlOptionalInterval(v any, low, high string) error {
	minimum, minOK := number(at(v, low))
	maximum, maxOK := number(at(v, high))
	return require(!minOK || !maxOK || maximum.Cmp(minimum) >= 0)
}
func sdlActivityCandidate(v any) error {
	if !fieldsUnique(v, "depends_on", "retryable_failure_classes") {
		return invalid()
	}
	count, ok := number(defaultMember(v, "max_retries", jsonZero))
	return require(!ok || (count.Sign() > 0) == (len(array(at(v, "retryable_failure_classes"))) > 0))
}
func sdlSharedTimeBinding(v any) error {
	condition, boundary := at(v, "condition_precondition_id") != nil, at(v, "observation_boundary_ref") != nil
	if stringAt(v, "evidence_mode") == termContinuous {
		return require(condition && boundary)
	}
	return require(!condition && !boundary)
}
func sdlTimingDisclosure(v any) error {
	if !nonblankSDLRefs(v, "affected_temporal_ids", "limitations") {
		return invalid()
	}
	limited := slices.Contains([]string{"disclosed_limitation", "bounded", statusUnsupported}, stringAt(v, "support_mode"))
	return require(!limited || len(array(at(v, "limitations"))) > 0)
}
func sdlControllerState(v any) error {
	if !nonblankSDLRefs(v, termAuthorityBasisRefs, termScopeRefs, fieldEvidenceRefs) {
		return invalid()
	}
	for _, field := range []string{termAuthorityBasisRefs, termScopeRefs, fieldEvidenceRefs} {
		if len(array(at(v, field))) == 0 {
			return invalid()
		}
	}
	return sdlOptionalInterval(v, "valid_from_order", "valid_until_order")
}
func sdlRandomFormat(v any) error {
	for _, field := range []string{"prefix", "suffix"} {
		value := stringAt(v, field)
		if utf8.RuneCountInString(value) > 256 {
			return invalid()
		}
		for _, r := range value {
			if r < 32 || r == 127 {
				return invalid()
			}
		}
	}
	return nil
}
