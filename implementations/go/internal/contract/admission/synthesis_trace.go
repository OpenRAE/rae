package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

func contributionKeys(rows any) (map[string]bool, error) {
	ranks := map[string]string{traceImportedAssertion: "0", traceTransformationAssumption: "1", contributionInferredStructure: "2", "transformation-default": "3", contributionAuthorDecision: "4", contributionPolicyDecision: "5"}
	keys := map[string]bool{}
	var previous string
	for index, row := range array(rows) {
		kind, ref := stringAt(row, termKind), stringAt(row, fieldRefID)
		rank, known := ranks[kind]
		if !known {
			return nil, invalid()
		}
		order := rank + ref
		if index > 0 && previous >= order {
			return nil, invalid()
		}
		previous = order
		keys[join(kind, ref)] = true
	}
	return keys, nil
}
func (e *Validator) synthesisProvenance(i validation.Invocation) error {
	v, err := e.defaulted("sdl-candidate-synthesis-record-v1", i.Instance)
	if err != nil {
		return err
	}
	if err := synthesisRecordBinding(v); err != nil {
		return err
	}
	if err := synthesisRecordOrder(v); err != nil {
		return err
	}
	if stringAt(v, "disposition") != outcomeSuccess {
		return nil
	}
	if at(v, termProfile) == nil {
		return invalid()
	}
	decisions := map[string]any{}
	for _, decision := range array(at(v, "input", "decisions")) {
		decisions[stringAt(decision, termTargetRef)] = decision
	}
	traces := array(at(v, "construct_traces"))
	if len(traces) != len(decisions) {
		return invalid()
	}
	owners := contributionOwners(v)
	for _, trace := range traces {
		decision := decisions[stringAt(trace, termTargetRef)]
		if decision == nil {
			return invalid()
		}
		if err := traceContributions(v, trace, decision, owners); err != nil {
			return err
		}
	}
	return nil
}
func contributionOwners(v any) map[string]map[string]bool {
	owners := map[string]map[string]bool{
		traceImportedAssertion:        rowSet(at(v, "input", "assertions"), "assertion_id"),
		traceTransformationAssumption: rowSet(at(v, "input", fieldAssumptions), "assumption_id"),
		contributionInferredStructure: set(at(v, termProfile, "rule_ids")),
		"transformation-default":      set(at(v, termProfile, "default_ids")),
		contributionAuthorDecision:    {}, contributionPolicyDecision: {},
	}
	for _, decision := range array(at(v, "input", "decisions")) {
		kind := contributionPolicyDecision
		if stringAt(decision, "actor_kind") == "author" {
			kind = contributionAuthorDecision
		}
		owners[kind][stringAt(decision, termDecisionID)] = true
	}
	return owners
}
func traceContributions(v, trace, decision any, owners map[string]map[string]bool) error {
	keys, err := contributionKeys(at(trace, "contributions"))
	if err != nil {
		return err
	}
	inferred := false
	for _, contribution := range array(at(trace, "contributions")) {
		kind := stringAt(contribution, termKind)
		if !owners[kind][stringAt(contribution, fieldRefID)] {
			return invalid()
		}
		inferred = inferred || kind == contributionInferredStructure
	}
	if !inferred {
		return invalid()
	}
	decisionKind := contributionPolicyDecision
	if stringAt(decision, "actor_kind") == "author" {
		decisionKind = contributionAuthorDecision
	}
	if !keys[join(decisionKind, stringAt(decision, termDecisionID))] {
		return invalid()
	}
	for _, assertion := range stringsOf(at(decision, "assertion_ids")) {
		if !keys[join(traceImportedAssertion, assertion)] {
			return invalid()
		}
	}
	for _, assumption := range array(at(v, "input", fieldAssumptions)) {
		if !disjoint(stringsOf(at(assumption, "assertion_ids")), set(at(decision, "assertion_ids"))) && !keys[join(traceTransformationAssumption, stringAt(assumption, "assumption_id"))] {
			return invalid()
		}
	}
	return nil
}
