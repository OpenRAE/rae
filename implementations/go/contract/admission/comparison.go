package admission

import (
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) comparisonRules() map[string]definition {
	return map[string]definition{
		"semantic-comparison-governed-scope":             {check: e.comparisonRequest},
		"semantic-comparison-independent-change-axes":    {check: e.comparisonResult},
		"semantic-projection-exact-frame-partition":      {check: e.projectionPartition},
		"semantic-projection-evidence-bounded-witnesses": {check: e.projectionWitnesses},
		"exploit-path-evidence-digest-joins":             {check: e.exploitEvidence},
	}
}

func (e *Validator) comparisonRequest(i validation.Invocation) error {
	v, err := e.defaulted("semantic-comparison-request-v1", i.Instance)
	if err != nil {
		return err
	}
	if err := comparisonScope(v); err != nil {
		return err
	}
	if !equal(at(v, sideBefore, "artifact_kind"), at(v, sideAfter, "artifact_kind")) {
		return invalid()
	}
	for _, side := range []string{sideBefore, sideAfter} {
		found := false
		for _, coordinate := range array(at(v, "impact_scope", side+"_artifacts")) {
			if compareTuple(coordinateKey(at(v, side)), coordinateKey(coordinate)) == 0 {
				found = true
			}
		}
		if !found {
			return invalid()
		}
	}
	return nil
}

func coordinateKey(v any) []string {
	return []string{stringAt(v, "artifact_kind"), stringAt(v, "canonical_identity"), stringAt(v, "canonical_digest")}
}
func comparisonCoordinate(v any) error {
	kind := stringAt(v, "artifact_kind")
	prefix, field := kind, kind+"_id"
	switch kind {
	case "evidence-specification":
		prefix, field = "capture-spec", "capture_spec_id"
	case "external-concept-bindings":
		field = "binding_set_id"
	}
	return require(stringAt(v, "canonical_identity") == prefix+":"+stringAt(v, field))
}

func comparisonScope(v any) error {
	for _, side := range []string{sideBefore, sideAfter} {
		if err := comparisonCoordinate(at(v, side)); err != nil {
			return err
		}
	}
	return comparisonImpactScope(at(v, "impact_scope"))
}
func comparisonImpactScope(scope any) error {
	if !sortedUnique(stringsOf(at(scope, "traversal_roots"))) {
		return invalid()
	}
	for _, side := range []string{sideBefore, sideAfter} {
		rows := at(scope, side+"_artifacts")
		if !orderedRows(rows, "artifact_kind", "canonical_identity", "canonical_digest") {
			return invalid()
		}
		for _, coordinate := range array(rows) {
			if err := comparisonCoordinate(coordinate); err != nil {
				return err
			}
		}
	}
	payload := maps.Clone(object(scope))
	delete(payload, "scope_digest")
	actual, err := jsonDigest(payload)
	if err != nil {
		return err
	}
	return require(actual == stringAt(scope, "scope_digest"))
}

func (e *Validator) comparisonResult(i validation.Invocation) error {
	v, err := e.defaulted("semantic-comparison-result-v1", i.Instance)
	if err != nil {
		return err
	}
	if err := comparisonScope(v); err != nil {
		return err
	}
	if !equal(at(v, "impact_scope_digest"), at(v, "impact_scope", "scope_digest")) || !orderedRows(at(v, "changes"), termIdentity, "before_identity", "after_identity") || !sortedUnique(stringsOf(at(v, "reason_codes"))) || !sortedUnique(stringsOf(at(v, "context_digests"))) {
		return invalid()
	}
	reasons := set(at(v, "reason_codes"))
	for _, change := range array(at(v, "changes")) {
		if !sortedUnique(stringsOf(at(change, "reason_codes"))) || !subset(stringsOf(at(change, "reason_codes")), reasons) {
			return invalid()
		}
		if err := comparisonSides(change, "identity_relation", "before_identity", "after_identity", false); err != nil {
			return err
		}
	}
	if err := comparisonDependencies(at(v, "dependencies"), reasons); err != nil {
		return err
	}
	if err := comparisonPaths(at(v, "impact_paths")); err != nil {
		return err
	}
	return require(stringAt(v, "completeness") != statusComplete || len(reasons) == 0)
}

func comparisonSides(v any, relationField, beforeField, afterField string, dependent bool) error {
	before, after := at(v, beforeField), at(v, afterField)
	switch stringAt(v, relationField) {
	case termAdded:
		return require(before == nil && after != nil)
	case termRemoved:
		return require(before != nil && after == nil)
	case "same", "renamed":
		return require(before != nil && after != nil)
	case termUnchanged, "changed":
		if dependent {
			return require(before != nil && after != nil && equal(before, after) == (stringAt(v, relationField) == termUnchanged))
		}
	}
	return nil
}

func comparisonDependencies(rows any, reasons map[string]bool) error {
	var previous []string
	for _, v := range array(rows) {
		key := []string{stringAt(v, "dependent_identity"), stringAt(v, "rule_id"), stringAt(v, sideBefore, "dependency_identity"), stringAt(v, sideAfter, "dependency_identity")}
		if previous != nil && compareTuple(previous, key) >= 0 {
			return invalid()
		}
		previous = key
		if err := comparisonSides(v, "relation", sideBefore, sideAfter, true); err != nil {
			return err
		}
		for _, side := range []string{sideBefore, sideAfter} {
			state := at(v, side)
			if state == nil {
				continue
			}
			codes := stringsOf(at(state, "reason_codes"))
			if !sortedUnique(codes) || !subset(codes, reasons) || !sortedUnique(stringsOf(at(state, "provenance_digests"))) || (stringAt(state, "resolution_status") == termResolved) != (len(codes) == 0) {
				return invalid()
			}
		}
	}
	return nil
}

func comparisonPaths(rows any) error {
	var previous []string
	for _, path := range array(rows) {
		key := []string{stringAt(path, "source_identity"), stringAt(path, "affected_identity")}
		current := stringAt(path, "source_identity")
		for _, step := range array(at(path, "steps")) {
			if stringAt(step, "dependency_identity") != current {
				return invalid()
			}
			current = stringAt(step, "dependent_identity")
			key = append(key, stringAt(step, "dependency_identity"), current, stringAt(step, "rule_id"))
		}
		if current != stringAt(path, "affected_identity") || previous != nil && slices.Compare(previous, key) >= 0 {
			return invalid()
		}
		previous = key
	}
	return nil
}
