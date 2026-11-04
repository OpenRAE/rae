package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) profileRules() map[string]definition {
	rules := map[string]definition{
		"validation-profile-catalog-reference-integrity": {check: profileCatalog},
		"validation-basis-profile-join-resolves":         {check: func(i validation.Invocation) error { _, err := e.disclosureProfile(i.Instance); return err }},
		"validation-basis-gate-rows-declared":            {check: e.disclosureRows},
		"validation-basis-strength-ordering-valid":       {check: disclosureStrength},
		"validation-basis-claim-capped-and-disclosed":    {check: e.disclosureLimitations},
	}
	for _, kind := range []string{kindTask, kindRun, kindStudy} {
		rules[kind+"-validation-basis-disclosure-identity-matches"] = definition{check: func(i validation.Invocation) error {
			for _, disclosure := range array(at(i.Instance, "validation_basis_disclosures")) {
				if stringAt(disclosure, "subject_kind") != "experiment_"+kind || !equal(at(disclosure, "subject_ref", fieldRefID), at(i.Instance, kind+"_id")) || !equal(at(disclosure, "subject_ref", fieldRefVersion), at(i.Instance, kind+"_version")) {
					return invalid()
				}
			}
			return nil
		}}
	}
	return rules
}

func rowIDs(v any, field string) []string {
	ids := make([]string, 0, len(array(v)))
	for _, row := range array(v) {
		ids = append(ids, stringAt(row, field))
	}
	return ids
}
func rowSet(v any, field string) map[string]bool {
	result := map[string]bool{}
	for _, id := range rowIDs(v, field) {
		result[id] = true
	}
	return result
}
func disjoint(a []string, b map[string]bool) bool {
	for _, value := range a {
		if b[value] {
			return false
		}
	}
	return true
}

func profileCatalog(i validation.Invocation) error {
	v := i.Instance
	for field, id := range map[string]string{"strengths": "strength_id", "subject_kinds": "subject_kind", "gate_kinds": "gate_kind", "limitation_categories": "limitation_category"} {
		if !unique(rowIDs(at(v, field), id)) {
			return invalid()
		}
	}
	ranks := map[int]bool{}
	for _, strength := range array(at(v, "strengths")) {
		n, ok := number(at(strength, "rank"))
		if !ok || !n.IsInt() || !n.Num().IsInt64() {
			return invalid()
		}
		rank := int(n.Num().Int64())
		if rank < 1 || rank > len(array(at(v, "strengths"))) || ranks[rank] {
			return invalid()
		}
		ranks[rank] = true
	}
	identities := []string{}
	for _, profile := range array(at(v, "profiles")) {
		identities = append(identities, join(stringAt(profile, termProfileID), stringAt(profile, "profile_version")))
		if err := profileReferences(v, profile); err != nil {
			return err
		}
	}
	return require(unique(identities))
}

func profileReferences(catalog, profile any) error {
	if !fieldsUnique(profile, "intended_subject_kinds", "required_gate_kinds", "optional_gate_kinds", "limitation_categories") || !disjoint(stringsOf(at(profile, "required_gate_kinds")), set(at(profile, "optional_gate_kinds"))) {
		return invalid()
	}
	checks := map[string]map[string]bool{
		"intended_subject_kinds": rowSet(at(catalog, "subject_kinds"), "subject_kind"),
		"required_gate_kinds":    rowSet(at(catalog, "gate_kinds"), "gate_kind"),
		"optional_gate_kinds":    rowSet(at(catalog, "gate_kinds"), "gate_kind"),
		"limitation_categories":  rowSet(at(catalog, "limitation_categories"), "limitation_category"),
	}
	terms := []string{stringAt(profile, "minimum_strength")}
	if !rowSet(at(catalog, "strengths"), "strength_id")[terms[0]] {
		return invalid()
	}
	for field, allowed := range checks {
		values := stringsOf(at(profile, field))
		if !subset(values, allowed) {
			return invalid()
		}
		terms = append(terms, values...)
	}
	return require(boolean(at(profile, "extension_terms_allowed")) || !extensionTerms(terms))
}
func extensionTerms(terms []string) bool {
	for _, term := range terms {
		if strings.HasPrefix(term, "x-") {
			return true
		}
	}
	return false
}

func (e *Validator) disclosureProfile(v any) (any, error) {
	kinds := map[string]string{kindScenario: kindScenario, "scenario_snapshot": kindScenarioSnapshot, "experiment_task": kindTask, "experiment_run": kindRun, "experiment_study": kindStudy, "backend_conformance_claim": kindBackend, "participant_conformance_claim": kindParticipantImplementation, "published_claim": "result"}
	kind := stringAt(v, "subject_kind")
	if kinds[kind] == "" || kinds[kind] != stringAt(v, "subject_ref", fieldRefKind) {
		return nil, invalid()
	}
	for _, profile := range e.profiles {
		if stringAt(profile, termProfileID) == stringAt(v, termProfileID) && stringAt(profile, "profile_version") == stringAt(v, "profile_version") && set(at(profile, "intended_subject_kinds"))[kind] {
			return profile, nil
		}
	}
	return nil, invalid()
}

func (e *Validator) disclosureRows(i validation.Invocation) error {
	profile, err := e.disclosureProfile(i.Instance)
	if err != nil {
		return err
	}
	rows := at(i.Instance, "gate_results")
	allowed := set(at(profile, "required_gate_kinds"))
	for _, id := range stringsOf(at(profile, "optional_gate_kinds")) {
		allowed[id] = true
	}
	ids := rowIDs(rows, "gate_kind")
	return require(unique(ids) && subset(ids, allowed) && subset(stringsOf(at(profile, "required_gate_kinds")), rowSet(rows, "gate_kind")))
}

func strengthGates(strength string) []string {
	structural := []string{"syntax_validation", "schema_validation", "vocabulary_validation"}
	if strength == strengthStructural {
		return structural
	}
	semantic := []string{"syntax_validation", "schema_validation", "vocabulary_validation", "semantic_invariant_validation", "reference_resolution"}
	switch strength {
	case strengthSemantic:
		return semantic
	case "behavioral":
		return append(semantic, "behavioral_execution")
	case strengthEvidence:
		return append(semantic, "evidence_preservation", "provenance_validation", "limitation_disclosure")
	case strengthFalsification:
		return append(semantic, "evidence_preservation", "provenance_validation", "limitation_disclosure", "falsification_protocol", "evidence_status")
	default:
		return nil
	}
}
func disclosureStrength(i validation.Invocation) error {
	strength := stringAt(i.Instance, "achieved_strength")
	required := strengthGates(strength)
	if len(required) == 0 {
		return invalid()
	}
	passed := map[string]bool{}
	for _, row := range array(at(i.Instance, "gate_results")) {
		passed[stringAt(row, "gate_kind")] = stringAt(row, messageOutcome) == "passed"
	}
	return require(subset(required, passed) && ((strength != strengthEvidence && strength != strengthFalsification) || len(array(at(i.Instance, fieldEvidenceRefs))) > 0))
}
func strengthRank(strength string) int {
	for index, term := range []string{strengthStructural, strengthSemantic, "behavioral", strengthEvidence, strengthFalsification} {
		if term == strength {
			return index + 1
		}
	}
	return 0
}
func (e *Validator) disclosureLimitations(i validation.Invocation) error {
	v := i.Instance
	profile, err := e.disclosureProfile(v)
	if err != nil {
		return err
	}
	if err := timestamps(v, "recorded_at"); err != nil {
		return err
	}
	limitations := array(at(v, "limitations"))
	needs := strengthRank(stringAt(v, "achieved_strength")) < strengthRank(stringAt(profile, "minimum_strength"))
	passed := map[string]bool{}
	for _, row := range array(at(v, "gate_results")) {
		passed[stringAt(row, "gate_kind")] = stringAt(row, messageOutcome) == "passed"
		needs = needs || stringAt(row, messageOutcome) == termNotApplicable
	}
	needs = needs || !subset(stringsOf(at(profile, "required_gate_kinds")), passed)
	if needs && len(limitations) == 0 {
		return invalid()
	}
	categories := rowIDs(limitations, "limitation_category")
	if !subset(categories, set(at(profile, "limitation_categories"))) {
		return invalid()
	}
	audience := stringAt(v, "audience")
	if audience == "public" || audience == "audience-restricted" {
		return require(rowSet(limitations, "limitation_category")["audience_restricted"])
	}
	return nil
}
