package admission

import (
	"encoding/json"
	"maps"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/internal/base/digest"
	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) authoringRules() map[string]definition {
	return map[string]definition{
		"authoring-vector-bound-inputs":       {check: authoringVector},
		"authoring-comparison-evidence-shape": {check: authoringComparison},
	}
}
func jsonDigest(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalid()
	}
	return digest.SHA256(canonical), nil
}
func authoringObservation(v any) bool {
	success := stringAt(v, messageOutcome) == outcomeSuccess
	return success == (at(v, "artifact_coordinate") != nil) && success == (at(v, "canonical_artifact_digest") != nil)
}
func authoringVector(i validation.Invocation) error {
	v := i.Instance
	source := []byte(stringAt(v, "input_source"))
	if len(source) > 65536 || len([]byte(stringAt(v, "contrast", "output_source"))) > 65536 || stringAt(v, "input_digest") != digest.SHA256(source) {
		return invalid()
	}
	operation := maps.Clone(object(at(v, "operation")))
	rename := stringAt(operation, termProfile) == "rename-sdl-declaration/v1"
	if rename != (at(operation, "target_address") != nil) || rename != (at(operation, "new_local_name") != nil) {
		return invalid()
	}
	for _, field := range []string{"target_address", "new_local_name"} {
		if _, present := operation[field]; !present {
			operation[field] = nil
		}
	}
	actual, err := jsonDigest(operation)
	if err != nil {
		return err
	}
	return require(actual == stringAt(v, "operation_digest") && authoringObservation(at(v, "expected")))
}
func authoringComparison(i validation.Invocation) error {
	v := i.Instance
	if !sortedUnique(stringsOf(at(v, "reason_codes"))) {
		return invalid()
	}
	left, right := at(v, "left"), at(v, "right")
	if (left == nil && boolean(at(v, "left_matches_expected"))) || (right == nil && boolean(at(v, "right_matches_expected"))) {
		return invalid()
	}
	if !optionalObservation(left) || !optionalObservation(right) {
		return invalid()
	}
	both := left != nil && right != nil
	if !both && !incomparableAxes(v) {
		return invalid()
	}
	hasArtifacts := both && stringAt(left, messageOutcome) == outcomeSuccess && stringAt(right, messageOutcome) == outcomeSuccess
	if hasArtifacts != (at(v, "semantic_result_digest") != nil) || (hasArtifacts && stringAt(v, "semantic_relation") == notApplicable) {
		return invalid()
	}
	if !both {
		return nil
	}
	return require(comparisonApplicability(v, left, right, hasArtifacts))
}
func optionalObservation(v any) bool { return v == nil || authoringObservation(v) }
func incomparableAxes(v any) bool {
	for _, axis := range []string{"artifact_relation", "diagnostic_relation", "provenance_relation", "semantic_relation"} {
		if stringAt(v, axis) != "incomparable" {
			return false
		}
	}
	return true
}
func comparisonApplicability(v, left, right any, hasArtifacts bool) bool {
	noArtifacts := stringAt(left, messageOutcome) == outcomeRefused && stringAt(right, messageOutcome) == outcomeRefused
	noProvenance := at(left, "transformation_digest") == nil && at(right, "transformation_digest") == nil
	return noArtifacts == (stringAt(v, "artifact_relation") == notApplicable) && stringAt(v, "diagnostic_relation") != notApplicable && noProvenance == (stringAt(v, "provenance_relation") == notApplicable) && (hasArtifacts || stringAt(v, "semantic_relation") == notApplicable)
}
