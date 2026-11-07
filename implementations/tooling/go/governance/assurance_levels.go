package governance

import (
	"slices"
	"strconv"
	"strings"
)

func assuranceTop(raw *mapping) []Finding {
	findings := []Finding{}
	for _, field := range []string{policyField, requirementRefs, adrRefsField, "levels"} {
		if !raw.has(field) {
			findings = append(findings, assuranceFinding("field", "missing required top-level field: "+field))
		}
	}
	if raw.has(policyField) && raw.get(policyField) != "classification-based-assurance" {
		findings = append(findings, assuranceFinding("value", "policy field must be 'classification-based-assurance', got '"+pythonStr(raw.get(policyField))+"'"))
	}
	for _, field := range []string{requirementRefs, adrRefsField, "levels"} {
		if _, ok := raw.get(field).([]any); raw.has(field) && !ok {
			findings = append(findings, assuranceFinding("field-type", "top-level field '"+field+"' must be a YAML list; got "+pythonType(raw.get(field))))
		}
	}
	return findings
}
func assuranceReferences(raw *mapping) []Finding {
	findings := []Finding{}
	findings = append(findings, assuranceReferenceTypes(raw)...)
	if _, ok := raw.get(requirementRefs).([]any); ok && !slices.Contains(assuranceStrings(raw.get(requirementRefs)), "ASR-505") {
		findings = append(findings, assuranceFinding("requirement-ref", "requirement_refs must include ASR-505"))
	}
	if _, ok := raw.get(adrRefsField).([]any); ok {
		for _, id := range []string{"ADR-007", "ADR-018"} {
			if !slices.Contains(assuranceStrings(raw.get(adrRefsField)), id) {
				findings = append(findings, assuranceFinding("adr-ref", "adr_refs must include "+id))
			}
		}
	}
	return findings
}

func assuranceReferenceTypes(raw *mapping) []Finding {
	findings := []Finding{}
	for _, field := range []string{requirementRefs, adrRefsField} {
		values, ok := raw.get(field).([]any)
		if !ok {
			continue
		}
		for _, value := range values {
			if _, ok := value.(string); !ok {
				findings = append(findings, assuranceFinding("field-type", "top-level field '"+field+"' must contain only strings; got non-string element "+pythonRepr(value)))
			}
		}
	}
	return findings
}

func assuranceLevels(levels []any) []Finding {
	findings := assuranceLevelIDs(levels)
	for i, level := range levels {
		findings = append(findings, assuranceLevelShape(i, level)...)
	}
	findings = append(findings, assuranceCategories(levels)...)
	byID := assuranceByID(levels)
	if fm0, found := byID["FM0"]; found {
		if missing := stringDifference([]string{"Alloy", "TLA+"}, assuranceStrings(fm0.get("prohibited_artifacts"))); len(missing) > 0 {
			findings = append(findings, assuranceFinding("fm0-prohibited", "FM0 must list ['Alloy', 'TLA+'] in prohibited_artifacts; missing: "+pythonRepr(missing)))
		}
	}
	floors := [][]string{{unitTestsArtifact}, {invariantArtifact, unitTestsArtifact}, {invariantArtifact, unitTestsArtifact, contractCoverageArtifact, differentialArtifact}, {invariantArtifact, unitTestsArtifact, contractCoverageArtifact, differentialArtifact, "abstract_state_machine_model"}}
	for i, id := range assuranceCanonicalIDs() {
		if level, ok := byID[id]; ok {
			if missing := stringDifference(floors[i], assuranceStrings(level.get("required_artifacts"))); len(missing) > 0 {
				findings = append(findings, assuranceFinding("required-floor", id+"'s required_artifacts must include the ADR-007 floor; missing: "+pythonRepr(missing)))
			}
		}
	}
	findings = append(findings, assuranceArtifactOverlap(levels)...)
	return append(findings, assuranceProportionality(levels)...)
}

func assuranceLevelIDs(levels []any) []Finding {
	findings := []Finding{}
	if len(levels) == 0 {
		findings = append(findings, assuranceFinding("levels-empty", "levels list is empty; the policy must enumerate every canonical FM level"))
	}
	ids := []string{}
	for _, level := range levels {
		if id, ok := object(level).get("id").(string); ok {
			ids = append(ids, id)
		}
	}
	for _, expected := range assuranceCanonicalIDs() {
		if !slices.Contains(ids, expected) {
			findings = append(findings, assuranceFinding("level-missing", "levels list is missing canonical level "+expected))
		}
	}
	seen := map[string]bool{}
	duplicates := []string{}
	numbered := []string{}
	for _, id := range ids {
		if seen[id] {
			duplicates = append(duplicates, id)
		}
		seen[id] = true
		if _, ok := assuranceFMIndex(id); ok {
			numbered = append(numbered, id)
		}
	}
	duplicates = uniqueStrings(duplicates)
	slices.Sort(duplicates)
	if len(duplicates) > 0 {
		findings = append(findings, assuranceFinding("level-duplicate", "level ids must be unique; duplicates: "+pythonRepr(duplicates)))
	}
	ordered := slices.Clone(numbered)
	slices.SortStableFunc(ordered, assuranceFMCompare)
	if !slices.Equal(numbered, ordered) {
		findings = append(findings, assuranceFinding("level-order", "FM-numbered levels must appear in ascending numeric order; got "+pythonRepr(numbered)+", expected "+pythonRepr(ordered)))
	}
	return findings
}

func assuranceLevelShape(index int, value any) []Finding {
	level := object(value)
	if level == nil {
		return []Finding{assuranceFinding("level-field", "level entry is not a mapping: "+pythonRepr(value))}
	}
	findings := []Finding{}
	if _, ok := assuranceFMIndex(level.get("id")); level.has("id") && !ok {
		findings = append(findings, assuranceFinding("level-id", "level "+strconv.Itoa(index)+" id must be FM followed by ASCII digits"))
	}
	id := "?"
	if level.has("id") {
		id = pythonStr(level.get("id"))
	}
	for _, field := range []string{"id", nameField, "scope", "change_categories", "required_artifacts"} {
		if !level.has(field) {
			findings = append(findings, assuranceFinding("level-field", "level '"+id+"' missing required field: "+field))
		}
	}
	return append(findings, assuranceLevelSequences(level, id)...)
}
func assuranceLevelSequences(level *mapping, id string) []Finding {
	findings := []Finding{}
	for _, field := range []string{"change_categories", "required_artifacts", "recommended_artifacts", "prohibited_artifacts"} {
		if !level.has(field) {
			continue
		}
		values, ok := level.get(field).([]any)
		if !ok {
			findings = append(findings, assuranceFinding("level-field-type", "level '"+id+"' field '"+field+"' must be a YAML list; got "+pythonType(level.get(field))))
			continue
		}
		for _, item := range values {
			if _, ok := item.(string); !ok {
				findings = append(findings, assuranceFinding("level-field-type", "level '"+id+"' field '"+field+"' must contain only strings; got non-string element "+pythonRepr(item)))
			}
		}
	}
	return findings
}

func assuranceCategories(levels []any) []Finding {
	findings := []Finding{}
	categories := []string{"structural", "semantic", "graph", "stateful"}
	byID := assuranceByID(levels)
	for i, id := range assuranceCanonicalIDs() {
		if level, ok := byID[id]; ok {
			values := assuranceStrings(level.get("change_categories"))
			if !slices.Contains(values, categories[i]) {
				findings = append(findings, assuranceFinding("categories", "level "+id+" must claim canonical change category '"+categories[i]+"' (per the ASR-505 statement); got "+pythonRepr(values)))
			}
		}
	}
	union := []string{}
	for _, level := range levels {
		union = append(union, assuranceStrings(object(level).get("change_categories"))...)
	}
	missing := []string{}
	for _, category := range categories {
		if !slices.Contains(union, category) {
			missing = append(missing, category)
		}
	}
	if len(missing) > 0 {
		findings = append(findings, assuranceFinding("categories", "change_categories union must include every word in the ASR-505 statement (('structural', 'semantic', 'graph', 'stateful')); missing: "+pythonRepr(missing)))
	}
	return findings
}

func assuranceArtifactOverlap(levels []any) []Finding {
	findings := []Finding{}
	for _, value := range levels {
		level := object(value)
		if level == nil {
			continue
		}
		prohibited := assuranceStrings(level.get("prohibited_artifacts"))
		overlap := []string{}
		for _, required := range stringSet(level.get("required_artifacts")) {
			if slices.Contains(prohibited, required) {
				overlap = append(overlap, required)
			}
		}
		id := "?"
		if level.has("id") {
			id = pythonStr(level.get("id"))
		}
		if len(overlap) > 0 {
			findings = append(findings, assuranceFinding("required-prohibited-overlap", "level '"+id+"' has artifacts in both required_artifacts and prohibited_artifacts: "+pythonRepr(overlap)))
		}
	}
	return findings
}

func assuranceProportionality(levels []any) []Finding {
	ordered := []*mapping{}
	for _, value := range levels {
		if _, ok := assuranceFMIndex(object(value).get("id")); ok {
			ordered = append(ordered, object(value))
		}
	}
	slices.SortStableFunc(ordered, func(a, b *mapping) int { return assuranceFMCompare(pythonStr(a.get("id")), pythonStr(b.get("id"))) })
	findings := []Finding{}
	for i := 1; i < len(ordered); i++ {
		parent, child := ordered[i-1], ordered[i]
		missing := stringDifference(assuranceStrings(parent.get("required_artifacts")), assuranceStrings(child.get("required_artifacts")))
		if len(missing) > 0 {
			parentID, childID := pythonStr(parent.get("id")), pythonStr(child.get("id"))
			findings = append(findings, assuranceFinding("proportionality", childID+"'s required_artifacts must be a superset of "+parentID+"'s; missing from "+childID+": "+pythonRepr(missing)))
		}
	}
	return findings
}
func assuranceFMIndex(value any) (string, bool) {
	text, ok := value.(string)
	if !ok || !strings.HasPrefix(text, "FM") || len(text) == 2 {
		return "", false
	}
	digits := text[2:]
	for _, digit := range []byte(digits) {
		if digit < '0' || digit > '9' {
			return "", false
		}
	}
	digits = strings.TrimLeft(digits, "0")
	if digits == "" {
		digits = "0"
	}
	return digits, true
}
func assuranceFMCompare(a, b string) int {
	left, _ := assuranceFMIndex(a)
	right, _ := assuranceFMIndex(b)
	if len(left) < len(right) {
		return -1
	}
	if len(left) > len(right) {
		return 1
	}
	return strings.Compare(left, right)
}
