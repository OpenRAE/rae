package admission

import (
	"encoding/json"
	"maps"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) synthesisRules() map[string]definition {
	return map[string]definition{
		"candidate-synthesis-pinned-source-join":      {check: e.synthesisSource},
		"candidate-synthesis-stable-input-order":      {check: synthesisInputOrder},
		"candidate-synthesis-complete-profile-digest": {check: e.synthesisProfile},
		"candidate-synthesis-all-or-none":             {check: e.synthesisShape},
		"candidate-synthesis-provenance-separation":   {check: e.synthesisProvenance},
	}
}
func (e *Validator) defaulted(id string, instance any) (any, error) {
	data, err := json.Marshal(instance)
	if err != nil {
		return nil, invalid()
	}
	view, err := e.low.Defaulted(id, data, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
	if err != nil {
		return nil, err
	}
	if !eventFactoryDefaults(id, view) {
		return view, nil
	}
	encoded, err := json.Marshal(view)
	if err != nil || len(encoded) > 8*1048576 {
		return nil, invalid()
	}
	return view, nil
}
func synthesisCoordinateField(kind string) string {
	return map[string]string{"concept": "concept", "relationship": "relationship_term", "precondition": "predicate_term", "ordering": "ordering_term", "parameterization": "parameter_term", "example": "example_ref"}[kind]
}
func assertionReferences(assertion any) []string {
	fields := map[string][]string{"relationship": {"source_assertion_id", "target_assertion_id"}, "precondition": {fieldSubjectAssertionID}, "parameterization": {fieldSubjectAssertionID}, "example": {fieldSubjectAssertionID}, "ordering": {"left_assertion_id", "right_assertion_id"}}[stringAt(assertion, termKind)]
	var refs []string
	for _, field := range fields {
		refs = append(refs, stringAt(assertion, field))
	}
	return refs
}
func (e *Validator) synthesisSource(i validation.Invocation) error {
	v, err := e.defaulted("sdl-candidate-synthesis-input-v1", i.Instance)
	if err != nil {
		return err
	}
	assertions, source := at(v, "assertions"), at(v, termSource)
	actual, err := jsonDigest(assertions)
	if err != nil {
		return err
	}
	if actual != stringAt(source, "assertion_set_digest") {
		return invalid()
	}
	known := rowSet(assertions, "assertion_id")
	for _, assertion := range array(assertions) {
		if !subset(assertionReferences(assertion), known) {
			return invalid()
		}
		if err := assertionSourceCoordinate(assertion, source); err != nil {
			return err
		}
	}
	for _, field := range []string{fieldAssumptions, "decisions"} {
		for _, row := range array(at(v, field)) {
			if !subset(stringsOf(at(row, "assertion_ids")), known) {
				return invalid()
			}
		}
	}
	return nil
}
func assertionSourceCoordinate(assertion, source any) error {
	coordinate := at(assertion, synthesisCoordinateField(stringAt(assertion, termKind)))
	for _, field := range []string{termAuthority, "scheme_id", termRevision} {
		if !equal(at(coordinate, field), at(source, field)) {
			return invalid()
		}
	}
	return require(equal(at(coordinate, "source_digest"), at(source, "content_digest")))
}
func synthesisInputOrder(i validation.Invocation) error {
	v := i.Instance
	if !orderedRows(at(v, "assertions"), "assertion_id") || !orderedRows(at(v, fieldAssumptions), "assumption_id") || !orderedRows(at(v, "decisions"), termDecisionID) || !orderedRows(at(v, "decisions"), termTargetRef) {
		return invalid()
	}
	if !orderedRows(at(v, termSource, "information_flow_policy_refs"), termProfileID, "version", termDigest) {
		return invalid()
	}
	for _, assertion := range array(at(v, "assertions")) {
		if !sortedUnique(stringsOf(at(assertion, "candidate_values"))) {
			return invalid()
		}
	}
	for _, field := range []string{fieldAssumptions, "decisions"} {
		for _, row := range array(at(v, field)) {
			if !sortedUnique(stringsOf(at(row, "assertion_ids"))) {
				return invalid()
			}
		}
	}
	for _, decision := range array(at(v, "decisions")) {
		if len(strings.TrimPrefix(stringAt(decision, termTargetRef), "nodes.")) > 35 {
			return invalid()
		}
	}
	return nil
}
func (e *Validator) synthesisProfile(i validation.Invocation) error {
	v, err := e.defaulted("sdl-candidate-synthesis-profile-v1", i.Instance)
	if err != nil {
		return err
	}
	for _, field := range []string{"supported_assertion_kinds", "supported_node_types", "rule_ids", "default_ids", "refusal_reason_codes"} {
		if !sortedUnique(stringsOf(at(v, field))) {
			return invalid()
		}
	}
	profile := maps.Clone(object(v))
	delete(profile, "profile_digest")
	actual, err := jsonDigest(profile)
	if err != nil {
		return err
	}
	return require(actual == stringAt(v, "profile_digest"))
}
func (e *Validator) synthesisShape(i validation.Invocation) error {
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
	if stringAt(v, "disposition") == outcomeSuccess {
		return require(at(v, termProfile) != nil && at(v, "candidate_exact_digest") != nil && at(v, "candidate_canonical_digest") != nil && len(array(at(v, "unresolved_choices"))) == 0 && len(array(at(v, "construct_traces"))) > 0 && stringAt(v, "transformation_report", "status") == outcomeSuccess && equal(at(v, "candidate_canonical_digest"), at(v, "transformation_report", "target_digest")))
	}
	return require(at(v, "candidate_exact_digest") == nil && at(v, "candidate_canonical_digest") == nil && len(array(at(v, "unresolved_choices"))) > 0 && len(array(at(v, "construct_traces"))) == 0 && stringAt(v, "transformation_report", "status") == outcomeRefused)
}
func synthesisRecordBinding(v any) error {
	input := at(v, "input")
	actual, err := jsonDigest(input)
	if err != nil {
		return err
	}
	if actual != stringAt(v, "input_digest") || !equal(at(v, "input_id"), at(input, "input_id")) || !equal(at(v, "input_digest"), at(v, "transformation_report", "source_digest")) {
		return invalid()
	}
	for _, choice := range array(at(v, "unresolved_choices")) {
		if !subset(stringsOf(at(choice, "assertion_ids")), rowSet(at(input, "assertions"), "assertion_id")) {
			return invalid()
		}
	}
	profile := at(v, termProfile)
	if profile == nil {
		return nil
	}
	return require(equal(at(input, "transformation_profile", termProfileID), at(profile, termProfileID)) && equal(at(input, "transformation_profile", "version"), at(profile, "profile_version")) && equal(at(input, "transformation_profile", termDigest), at(profile, "profile_digest")))
}
func synthesisRecordOrder(v any) error {
	if !orderedRows(at(v, "unresolved_choices"), "choice_id") || !orderedRows(at(v, "construct_traces"), termTargetRef) {
		return invalid()
	}
	for _, choice := range array(at(v, "unresolved_choices")) {
		if !sortedUnique(stringsOf(at(choice, "assertion_ids"))) || !sortedUnique(stringsOf(at(choice, "alternatives"))) {
			return invalid()
		}
	}
	for _, trace := range array(at(v, "construct_traces")) {
		if _, err := contributionKeys(at(trace, "contributions")); err != nil {
			return err
		}
	}
	return nil
}
