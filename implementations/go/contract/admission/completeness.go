package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) completenessRules() map[string]definition {
	return map[string]definition{
		"scientific-completeness-taxonomy-assessment-join":   {check: e.completenessJoin, contextual: true, requiresContext: true},
		"scientific-completeness-taxonomy-rectangular":       {check: taxonomyRectangular},
		"scientific-completeness-assessment-status-evidence": {check: assessmentEvidence},
	}
}

func (e *Validator) completenessJoin(i validation.Invocation) error {
	context, ok := i.Context.(CompletenessContext)
	if !ok {
		return contextRequired()
	}
	taxonomy, err := e.contextDocument("scientific-completeness-taxonomy-v1", context.CompletenessTaxonomy())
	if err != nil {
		return err
	}
	return assessmentTaxonomy(i.Instance, taxonomy)
}
func assessmentTaxonomy(assessment, taxonomy any) error {
	const family = "scientific-scenario-completeness"
	if !equal(defaultMember(assessment, "profile_family", family), defaultMember(taxonomy, "profile_family", family)) || !equal(at(assessment, fieldTaxonomyRevision), at(taxonomy, termRevision)) {
		return invalid()
	}
	ids := rowIDs(at(assessment, "concerns"), "concern_id")
	expected := rowSet(at(taxonomy, "concerns"), "concern_id")
	return require(unique(ids) && len(ids) == len(expected) && subset(ids, expected))
}
func sameKeys(v any, expected map[string]bool) bool {
	if len(object(v)) != len(expected) {
		return false
	}
	for key := range object(v) {
		if !expected[key] {
			return false
		}
	}
	return true
}
func taxonomyRectangular(i validation.Invocation) error {
	v := i.Instance
	if !unique(rowIDs(at(v, "concerns"), "concern_id")) || !unique(rowIDs(at(v, "profiles"), termProfileID)) {
		return invalid()
	}
	concerns := rowSet(at(v, "concerns"), "concern_id")
	for _, profile := range array(at(v, "profiles")) {
		if !sameKeys(at(profile, "dispositions"), concerns) {
			return invalid()
		}
	}
	return nil
}
func repositoryPath(v string) bool {
	if strings.HasPrefix(v, "/") {
		return false
	}
	for part := range strings.SplitSeq(v, "/") {
		if part == ".." {
			return false
		}
	}
	return true
}
func assessmentEvidence(i validation.Invocation) error {
	if !unique(rowIDs(at(i.Instance, "concerns"), "concern_id")) {
		return invalid()
	}
	for _, concern := range array(at(i.Instance, "concerns")) {
		if err := concernEvidence(concern); err != nil {
			return err
		}
	}
	return nil
}
func concernEvidence(v any) error {
	executable := false
	contracts := map[string]bool{}
	for _, item := range array(at(v, termEvidence)) {
		kind := stringAt(item, termKind)
		executable = executable || kind == termImplementation || kind == "test" || kind == "conformance"
		contract := kind == "contract" || kind == "published-schema"
		if contract != (at(item, termContractID) != nil) || !repositoryPath(stringAt(item, "path")) {
			return invalid()
		}
		if contract {
			contracts[stringAt(item, termContractID)] = true
		}
	}
	status := stringAt(v, "status")
	if status == statusImplemented && !executable {
		return invalid()
	}
	if err := externalCompleteness(v, contracts); err != nil {
		return err
	}
	if (status == "deliberately-excluded") != (at(v, "exclusion_rationale") != nil) {
		return invalid()
	}
	return require((status != statusPartial && status != "missing") || len(array(at(v, "issue_refs"))) > 0)
}

func externalCompleteness(v any, contracts map[string]bool) error {
	refs := stringsOf(at(v, "external_contract_refs"))
	witnesses := object(at(v, "satisfiability_witness_refs"))
	for _, path := range witnesses {
		if !repositoryPath(text(path)) {
			return invalid()
		}
	}
	if stringAt(v, "status") == "external-contract" {
		if len(refs) == 0 || len(witnesses) == 0 || at(v, "binding_obligation") == nil || !subset(refs, contracts) || !sameKeys(witnesses, set(at(v, "external_contract_refs"))) {
			return invalid()
		}
	} else if len(refs) > 0 || len(witnesses) > 0 || at(v, "binding_obligation") != nil {
		return invalid()
	}
	return nil
}
