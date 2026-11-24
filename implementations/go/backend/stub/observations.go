package stub

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	runtimecontract "github.com/OpenRAE/rae/implementations/go/contract/runtime"
)

// Stub driver claims cannot establish independent native evidence. Preserve
// unrelated disclosures and reuse only selected, apparatus-bound prior evidence.
func retainedObservations(plan, snapshot, envelope map[string]any) ([]runtimecontract.RealizationObservationDisclosure, error) {
	previous, result, err := priorDisclosures(snapshot)
	if err != nil {
		return nil, err
	}

	var demands []admission.ObservationDemandSelection
	raw, err := json.Marshal(plan["observation_demands"])
	if err != nil || json.Unmarshal(raw, &demands) != nil {
		return nil, invalid()
	}
	operations, err := observationActions(plan)
	if err != nil {
		return nil, err
	}

	for _, item := range array(plan["realization_constraints"]) {
		constraint, ok := item.(map[string]any)
		if !ok {
			return nil, invalid()
		}
		selected, err := admission.SelectObservationDemand(demands, text(constraint, "governing_scope"), text(constraint, "address"), text(constraint, "concern"), "collection")
		if err != nil {
			return nil, err
		}
		prior := previous[text(constraint, "address")]
		if !selected || operations[text(constraint, "address")] != termUnchanged || !reusableDisclosure(prior, constraint, envelope) {
			continue
		}
		native, err := disclosureValue(prior)
		if err != nil {
			return nil, err
		}
		result = append(result, native)
	}
	return result, nil
}

func reusableDisclosure(prior, constraint, envelope map[string]any) bool {
	if prior == nil || prior["field_path"] != constraint["field_path"] || prior["envelope_digest"] != envelope["digest"] || prior[termConfigurationDigest] != object(envelope, "configuration")[termConfigurationDigest] || !slices.Contains([]string{"presence", "configuration"}, text(prior, "verification_scope")) || !slices.Contains([]string{"daemon-observed", "guest-observed"}, text(prior, "observation_strength")) {
		return false
	}
	domain := object(constraint, "value_domain")
	if domain == nil {
		return true
	}
	value := text(prior, "observed_value")
	switch text(domain, "kind") {
	case "exact":
		return domain["value"] == value
	case "governed-reference":
		for _, member := range array(domain["allowed_refs"]) {
			if member == value {
				return true
			}
		}
	case "enum":
		for _, member := range array(domain["values"]) {
			if member == value {
				return true
			}
		}
	}
	return false
}

func disclosureValue(input map[string]any) (runtimecontract.RealizationObservationDisclosure, error) {
	result := runtimecontract.RealizationObservationDisclosure{}
	owner, err := schemas()
	if err != nil {
		return result, err
	}
	raw, err := json.Marshal(input)
	if err != nil || owner.CheckModelFragment("runtime-snapshot-v1", "#/$defs/RealizationObservationDisclosureModel", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return result, invalid()
	}
	result.Address = text(input, "address")
	result.FieldPath = text(input, "field_path")
	result.Domain = text(input, "domain")
	result.RequirementKind = text(input, "requirement_kind")
	result.VerificationScope = text(input, "verification_scope")
	result.ObservationStrength = text(input, "observation_strength")
	for _, field := range []struct {
		key    string
		target **string
	}{{"observed_value", &result.ObservedValue}, {"operation_id", &result.OperationID}, {"envelope_digest", &result.EnvelopeDigest}, {termConfigurationDigest, &result.ConfigurationDigest}, {"observer_version", &result.ObserverVersion}} {
		if input[field.key] != nil {
			value := text(input, field.key)
			*field.target = &value
		}
	}
	if input["sequence"] != nil {
		sequence, ok := input["sequence"].(json.Number)
		if !ok {
			return result, invalid()
		}
		number, err := sequence.Int64()
		if err != nil {
			return result, invalid()
		}
		result.Sequence = &number
	}
	if operating := object(input, "operating_system"); operating != nil {
		result.OperatingSystem = &runtimecontract.ObservedOperatingSystemIdentity{Family: text(operating, "family"), Distribution: text(operating, "distribution"), Version: text(operating, "version")}
	}
	result.BindingVerified = input["binding_verified"] == true
	return result, nil
}

func priorDisclosures(snapshot map[string]any) (map[string]map[string]any, []runtimecontract.RealizationObservationDisclosure, error) {
	previous := map[string]map[string]any{}
	result := []runtimecontract.RealizationObservationDisclosure{}
	for _, item := range array(snapshot["realization_observations"]) {
		disclosure, ok := item.(map[string]any)
		if !ok {
			return nil, nil, invalid()
		}
		native, err := disclosureValue(disclosure)
		if err != nil {
			return nil, nil, err
		}
		if native.RequirementKind != "compute-substrate" {
			result = append(result, native)
		} else {
			previous[native.Address] = disclosure
		}
	}
	return previous, result, nil
}

func observationActions(plan map[string]any) (map[string]string, error) {
	operations := map[string]string{}
	for _, item := range array(plan["operations"]) {
		operation, ok := item.(map[string]any)
		if !ok {
			return nil, invalid()
		}
		operations[text(operation, "address")] = text(operation, "action")
	}
	return operations, nil
}
