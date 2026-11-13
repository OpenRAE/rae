package sdl

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// NormalizeConcernValue uses native SDL construction for one admitted descriptor.
// It grants no scenario, reference, execution or disclosure authority.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func NormalizeConcernValue(descriptor, value admission.Fragment) (admission.Fragment, error) {
	if admission.CheckFragment(descriptor, admission.RealizationConcern) != nil || admission.CheckFragment(value, admission.RealizationValue) != nil {
		return nil, invalidScenario()
	}
	document, ok := descriptor.Document().(map[string]any)
	if !ok {
		return nil, invalidScenario()
	}
	section, ok := document["section"].(string)
	if !ok {
		return nil, invalidScenario()
	}
	authored, ok := document["authored_path"].([]any)
	if !ok {
		return nil, invalidScenario()
	}
	path := make([]string, len(authored))
	for i, token := range authored {
		var valid bool
		path[i], valid = token.(string)
		if !valid {
			return nil, invalidScenario()
		}
	}
	return normalizeFieldValue(section, path, value)
}

// NormalizeCapabilityValue applies the native scalar constructor to a capability domain.
//
//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func NormalizeCapabilityValue(concern string, value admission.Fragment) (admission.Fragment, error) {
	if admission.CheckFragment(value, admission.RealizationValue) != nil {
		return nil, invalidScenario()
	}
	section := "nodes"
	var field string
	switch concern {
	case "nodes.os":
		field = "os"
	case "nodes.os_distribution":
		field = "os_distribution"
	case "nodes.os_version":
		field = "os_version"
	case "nodes.architecture":
		field = "architecture"
	case "infrastructure.count":
		section, field = "infrastructure", "count"
	default:
		return nil, invalidScenario()
	}
	return normalizeFieldValue(section, []string{field}, value)
}

//nolint:ireturn // The declared consumer API returns an opaque handle from its native owner.
func normalizeFieldValue(section string, path []string, value admission.Fragment) (admission.Fragment, error) {
	raw, err := json.Marshal(value.Document())
	if err != nil {
		return nil, invalidScenario()
	}
	parser, err := scenarioParser(DefaultLimits())
	if err != nil {
		return nil, err
	}
	normalized, err := parser.NormalizeConcern(section, path, raw)
	if err != nil {
		return nil, err
	}
	decoder := json.NewDecoder(bytes.NewReader(normalized))
	decoder.UseNumber()
	var result any
	if checkErr := decoder.Decode(&result); checkErr != nil {
		return nil, invalidScenario()
	}
	validator, err := fragmentOwner()
	if err != nil {
		return nil, err
	}
	return admission.AdmitFragment(validator, admission.RealizationValue, result, ingress.Limits{MaxBytes: len(normalized) + 1, MaxDepth: DefaultLimits().MaxDepth})
}

// ObservationScopes returns native semantic scopes for explicit source inputs.
func ObservationScopes(scenario Scenario, pointers, references []string, profiles []admission.RealizationCollectionProfile) (map[string]string, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	return input.document.ObservationScopes(pointers, references, profiles)
}
