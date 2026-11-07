package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) evidenceRelationRules() map[string]definition {
	return map[string]definition{"evidence-requirement-relation-lineage-valid": {check: e.evidenceRelation, contextual: true, requiresContext: true}}
}
func evidenceRelationShape(v any) error {
	name, ok := strings.CutPrefix(stringAt(v, "base_requirement_address"), "evidence_requirements.")
	if !ok || !address.Valid("sdl."+name) {
		return invalid()
	}
	authority := at(v, "authority_ref")
	kind := stringAt(authority, fieldRefKind)
	allowed := map[string]map[string]bool{kindTask: {kindTask: true}, kindRun: {termAuthoringInput: true, kindRun: true}, kindStudy: {kindStudy: true}}[stringAt(v, "scope")]
	if !allowed[kind] || at(authority, fieldRefVersion) == nil || at(authority, "ref_digest") != nil || at(authority, "ref_path") != nil {
		return invalid()
	}
	base := at(v, "base_scenario_ref")
	if at(base, fieldRefVersion) == nil || at(base, "ref_digest") == nil || at(base, "ref_path") != nil || at(v, "capture_spec_ref", fieldRefVersion) == nil || !fieldsUnique(v, "refinement_dimensions") {
		return invalid()
	}
	return require((stringAt(v, "relation_kind") == "refine") == (len(array(at(v, "refinement_dimensions"))) > 0))
}
func (e *Validator) evidenceRelation(i validation.Invocation) error {
	v := i.Instance
	if err := evidenceRelationShape(v); err != nil {
		return err
	}
	c, ok := i.Context.(EvidenceRelationContext)
	if !ok {
		return contextRequired()
	}
	base, err := relationScenario(v, c)
	if err != nil {
		return err
	}
	specs, err := e.experimentDocuments("experiment-capture-spec-v1", c.CaptureSpecs())
	if err != nil {
		return err
	}
	scoped, err := relationCapture(v, specs)
	if err != nil {
		return err
	}
	if equal(at(base, "capture_spec_ref"), at(v, "capture_spec_ref", fieldRefID)) && equal(at(base, "capture_requirement_ref"), at(v, "capture_requirement_ref")) {
		return invalid()
	}
	if stringAt(v, "relation_kind") == "extend" {
		return nil
	}
	strict := false
	for _, dimension := range stringsOf(at(v, "refinement_dimensions")) {
		stronger, err := refinementDimension(dimension, base, scoped)
		if err != nil {
			return err
		}
		strict = strict || stronger
	}
	return require(strict)
}
func relationCapture(v any, specs []any) (any, error) {
	matches := 0
	var selected any
	for _, spec := range specs {
		if equal(at(spec, "capture_spec_id"), at(v, "capture_spec_ref", fieldRefID)) && equal(at(spec, "spec_version"), at(v, "capture_spec_ref", fieldRefVersion)) {
			matches++
			selected = spec
		}
	}
	if matches != 1 {
		return nil, invalid()
	}
	found := false
	for _, ref := range array(at(selected, termScopeRefs)) {
		if matchingFields(ref, at(v, "authority_ref"), fieldRefKind, fieldRefID, fieldRefVersion, "ref_digest", "ref_path") {
			found = true
		}
	}
	scoped := at(selected, "capture_requirements", stringAt(v, "capture_requirement_ref"))
	if !found || scoped == nil {
		return nil, invalid()
	}
	return scoped, nil
}
func refinementDimension(dimension string, base, scoped any) (bool, error) {
	left := map[string]bool{}
	var right map[string]bool
	alternatives := false
	switch dimension {
	case "field-selectors":
		left, right = set(at(base, "field_selectors")), set(at(scoped, "field_selectors"))
	case "artifact-roles":
		if role := stringAt(base, "artifact_role"); role != "" {
			left[role] = true
		}
		right = set(at(scoped, "required_artifact_roles"))
		alternatives = true
	case "integrity-requirements":
		if integrity := stringAt(base, "integrity"); integrity != postureNone && integrity != "" {
			left[integrity] = true
		}
		right = set(at(scoped, "integrity_requirements"))
	case "loss-disclosure":
		required := stringAt(base, "loss_disclosure") == requirementRequired
		provided := boolean(at(scoped, "loss_disclosure_required"))
		if required && !provided {
			return false, invalid()
		}
		return provided && !required, nil
	default:
		return false, invalid()
	}
	return refinementSetComparison(left, right, alternatives)
}

func refinementSetComparison(left, right map[string]bool, alternatives bool) (bool, error) {
	if alternatives && len(left) > 0 {
		if len(right) == 0 || !subsetSet(right, left) {
			return false, invalid()
		}
	} else if !subsetSet(left, right) {
		return false, invalid()
	}
	return !equalSet(left, right), nil
}

func subsetSet(left, right map[string]bool) bool {
	for key := range left {
		if !right[key] {
			return false
		}
	}
	return true
}

func relationScenario(v any, c EvidenceRelationContext) (any, error) {
	scenarios := c.EvidenceScenarios()
	if len(scenarios) > 4096 {
		return nil, invalid()
	}
	var base any
	matches := 0
	for _, entry := range scenarios {
		if entry.Value.ContractID() != termSdlAuthoringInputV1 {
			return nil, invalid()
		}
		raw := entry.Value.JSON()
		if len(raw) > 8*1048576 {
			return nil, invalid()
		}
		scenario, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
		if err != nil {
			return nil, invalid()
		}
		ref := at(v, "base_scenario_ref")
		if stringAt(ref, fieldRefKind) == kindScenarioSnapshot && equal(at(ref, fieldRefID), at(scenario, termName)) && equal(at(ref, fieldRefVersion), at(scenario, "version")) && stringAt(ref, "ref_digest") == entry.Digest {
			matches++
			base = at(scenario, "evidence_requirements", strings.TrimPrefix(stringAt(v, "base_requirement_address"), "evidence_requirements."))
		}
	}
	if matches != 1 || base == nil {
		return nil, invalid()
	}
	return base, nil
}
