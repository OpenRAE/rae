package governance

import (
	"errors"
	"slices"
)

const unitTestsArtifact = "unit_tests"
const invariantArtifact = "invariant_list"
const contractCoverageArtifact = "typed_ir_or_contract_coverage"
const differentialArtifact = "property_based_or_differential_tests"

const assurancePolicy = "specs/formal/assurance-policy.yaml"
const assuranceADR = adrDirectory + "/adr-007-lightweight-formal-methods-policy.md"
const assuranceCoding = "docs/explain/reference/coding-standards.md"
const assuranceOverview = "docs/specs/formal.md"
const assuranceTemplate = adrDirectory + "/TEMPLATE.md"
const assuranceLedger = "docs/explain/reference/fm-classification-ledger.yaml"
const assuranceFulfillment = "specs/formal/assurance-fulfillment.yaml"

func assuranceFinding(rule, message string) Finding {
	return finding("assurance-policy-"+rule, message, assurancePolicy)
}
func assuranceCanonicalIDs() []string { return []string{"FM0", "FM1", "FM2", "FM3"} }

func (c *checker) assurance(r *repository) (Report, error) {
	raw, findings, err := assuranceYAML(r, assurancePolicy, "assurance-policy", "assurance policy")
	if err != nil {
		return Report{}, err
	}
	if raw == nil {
		return c.finish(r, findings)
	}
	findings = append(findings, assuranceTop(raw)...)
	findings = append(findings, assuranceReferences(raw)...)
	levels, _ := raw.get("levels").([]any)
	findings = append(findings, assuranceLevels(levels)...)
	drift, err := assuranceDrift(r, levels)
	if err != nil {
		return Report{}, err
	}
	findings = append(findings, drift...)
	classification, err := assuranceADRClassifications(r, assuranceByID(levels))
	if err != nil {
		return Report{}, err
	}
	findings = append(findings, classification...)
	ledger, err := assuranceLedgerFindings(r, levels)
	if err != nil {
		return Report{}, err
	}
	findings = append(findings, ledger...)
	fulfillment, err := assuranceFulfillmentFindings(r, levels)
	if err != nil {
		return Report{}, err
	}
	return c.finish(r, append(findings, fulfillment...))
}

func assuranceYAML(r *repository, name, rule, label string) (*mapping, []Finding, error) {
	if !r.file(name) {
		return nil, []Finding{finding(rule+"-missing", label+" not found: "+name, name)}, nil
	}
	text, err := r.text(name)
	if err != nil {
		if !errors.Is(err, errNotUTF8) {
			return nil, nil, err
		}
		return nil, []Finding{finding(rule+"-parse", "failed to parse "+name, name)}, nil
	}
	value, err := yamlValue([]byte(text), false)
	if err != nil {
		return nil, []Finding{finding(rule+"-parse", "failed to parse "+name+": "+yamlFailureText([]byte(text), err), name)}, nil
	}
	if object(value) == nil {
		return nil, []Finding{finding(rule+"-shape", name+" must be a YAML mapping at the top level", name)}, nil
	}
	return object(value), []Finding{}, nil
}

func assuranceStrings(value any) []string {
	entries, _ := value.([]any)
	result := []string{}
	for _, item := range entries {
		if text, ok := item.(string); ok {
			result = append(result, text)
		}
	}
	return result
}
func assuranceByID(levels []any) map[string]*mapping {
	result := map[string]*mapping{}
	for _, value := range levels {
		row := object(value)
		if id, ok := row.get("id").(string); ok {
			result[id] = row
		}
	}
	return result
}
func assuranceRequired(levels []any) (map[string][]string, []string) {
	required := map[string][]string{}
	kinds := []string{}
	for id, level := range assuranceByID(levels) {
		required[id] = stringSet(level.get("required_artifacts"))
	}
	// The union includes earlier duplicate-id entries, as the reference does.
	for _, value := range levels {
		kinds = append(kinds, assuranceStrings(object(value).get("required_artifacts"))...)
	}
	kinds = uniqueStrings(kinds)
	slices.Sort(kinds)
	return required, kinds
}
func stringDifference(required []string, provided ...[]string) []string {
	present := map[string]bool{}
	for _, group := range provided {
		for _, value := range group {
			present[value] = true
		}
	}
	missing := []string{}
	for _, value := range uniqueStrings(required) {
		if !present[value] {
			missing = append(missing, value)
		}
	}
	slices.Sort(missing)
	return missing
}
