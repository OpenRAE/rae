package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) artifactRules() map[string]definition {
	return map[string]definition{
		"exact-source-artifact-id-match":              {check: func(i validation.Invocation) error { return exactArtifact(i.Instance, false) }},
		"exact-source-version-match":                  {check: func(i validation.Invocation) error { return exactArtifact(i.Instance, true) }},
		"materialization-locked-input-join":           {check: materializationInputs},
		"artifact-transformation-all-or-none":         {check: transformationStatus},
		"artifact-transformation-deterministic-order": {check: transformationOrder},
	}
}

func exactArtifact(v any, version bool) error {
	return exactSourceArtifact(at(v, termSource), version)
}
func exactSourceArtifact(source any, version bool) error {
	requirement := at(source, "artifact_requirement")
	if stringAt(requirement, "explicitness") != postureExact {
		return nil
	}
	if !version {
		return require(stringAt(source, termName) == stringAt(requirement, "exact_artifact", termArtifactID))
	}
	selected, present := object(source)["version"]
	if !present {
		selected = "*"
	}
	return require(equal(selected, at(requirement, "exact_artifact", "version")))
}

func materializationInputs(i validation.Invocation) error {
	return materializationRequirementInputs(at(i.Instance, termSource, "artifact_requirement"))
}
func materializationRequirementInputs(requirement any) error {
	declared := map[string]bool{}
	for _, input := range array(at(requirement, "locked_inputs")) {
		declared[stringAt(input, "input_id")] = true
	}
	for _, spec := range array(at(requirement, "materialization_specifications")) {
		mechanism := stringAt(spec, termProfile, "mechanism")
		if mechanism != termMaterializationSpecification && !strings.HasPrefix(mechanism, "x-") {
			return invalid()
		}
		if !subset(stringsOf(at(spec, "locked_input_ids")), declared) {
			return invalid()
		}
	}
	return nil
}

func sourceArtifactIdentity(source any) error {
	if err := exactSourceArtifact(source, false); err != nil {
		return err
	}
	return exactSourceArtifact(source, true)
}

func transformationStatus(i validation.Invocation) error {
	v := i.Instance
	if stringAt(v, "status") == outcomeSuccess {
		return require(at(v, "target_digest") != nil && stringAt(v, "preservation", messageOutcome) != outcomeFailed)
	}
	return require(at(v, "target_digest") == nil && len(array(at(v, "diagnostics"))) > 0)
}

// orderedRows compares fields separately so separators inside fields cannot
// make distinct tuples equal. Tuple comparison preserves Python ordering.
func orderedRows(rows any, fields ...string) bool {
	var previous []string
	for _, row := range array(rows) {
		current := make([]string, len(fields))
		for index, field := range fields {
			current[index] = stringAt(row, field)
		}
		if previous != nil && compareTuple(previous, current) >= 0 {
			return false
		}
		previous = current
	}
	return true
}

func compareTuple(a, b []string) int {
	for index := range a {
		if c := strings.Compare(a[index], b[index]); c != 0 {
			return c
		}
	}
	return 0
}

func transformationOrder(i validation.Invocation) error {
	v := i.Instance
	if !sortedUnique(stringsOf(at(v, "affected_identities"))) || !orderedRows(at(v, "identity_map"), sideBefore, sideAfter, "declaration_kind") || !orderedRows(at(v, "losses"), termKind, "affected_identity") || !orderedRows(at(v, "diagnostics"), "code", "address", "severity", "message") {
		return invalid()
	}
	for _, field := range []string{termPreconditions, "postconditions"} {
		if !orderedRows(at(v, field), "check_id") {
			return invalid()
		}
		for _, check := range array(at(v, field)) {
			if !sortedUnique(stringsOf(at(check, "diagnostic_codes"))) {
				return invalid()
			}
		}
	}
	preservation := at(v, "preservation")
	if stringAt(preservation, messageOutcome) == statusVerified && len(array(at(preservation, "evidence_digests"))) == 0 {
		return invalid()
	}
	return require(sortedUnique(stringsOf(at(preservation, "evidence_digests"))) && sortedUnique(stringsOf(at(preservation, "limitations"))))
}
