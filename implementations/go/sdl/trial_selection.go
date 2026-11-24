package sdl

import (
	"bytes"
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// ResolveBindingTarget projects one canonical scalar target from its native owner.
func ResolveBindingTarget(family Scenario, scenarioFamilyID, pointID, suppliedTargetID string) (admission.ScenarioBindingResolution, error) {
	owned, err := nativeScenario(family)
	if err != nil {
		return admission.ScenarioBindingResolution{}, err
	}
	return owned.document.ResolveBindingTarget(scenarioFamilyID, pointID, suppliedTargetID)
}

// Select applies recorded outcomes through the original native SDL owner.
// Trial provenance is optional; this operation never generates a random draw.
//
//nolint:ireturn // The declared public operation returns the native sealed phase handle.
func Select(family Scenario, outcomes admission.Fragment, trialProvenance admission.Fragment) (InstantiatedScenario, error) {
	s, err := nativeScenario(family)
	if err != nil {
		return nil, err
	}
	if admission.CheckFragment(outcomes, admission.RealizationValue) != nil {
		return nil, invalidScenario()
	}
	raw, err := json.Marshal(outcomes.Document())
	if err != nil {
		return nil, invalidScenario()
	}
	var provenance []byte
	if trialProvenance != nil {
		if admission.CheckFragment(trialProvenance, admission.RealizationValue) != nil {
			return nil, invalidScenario()
		}
		provenance, err = json.Marshal(trialProvenance.Document())
		if err != nil {
			return nil, invalidScenario()
		}
	}
	document, err := s.parser.Select(s.document, raw, provenance)
	if err != nil {
		return nil, err
	}
	return &instantiated{newScenario(document, s.parser)}, nil
}

// VariationOutcomes returns independent admitted outcomes from one finite domain.
func VariationOutcomes(family Scenario, pointID string, maximum int) ([]admission.Fragment, error) {
	s, err := nativeScenario(family)
	if err != nil {
		return nil, err
	}
	raw, err := s.parser.FiniteVariationOutcomes(s.document, pointID, maximum)
	if err != nil {
		return nil, err
	}
	var rows []json.RawMessage
	if json.Unmarshal(raw, &rows) != nil {
		return nil, invalidScenario()
	}
	owner, err := admission.New()
	if err != nil {
		return nil, err
	}
	output := make([]admission.Fragment, 0, len(rows))
	for _, row := range rows {
		decoder := json.NewDecoder(bytes.NewReader(row))
		decoder.UseNumber()
		var document any
		if decoder.Decode(&document) != nil {
			return nil, invalidScenario()
		}
		fragment, err := admission.AdmitFragment(owner, admission.RealizationValue, document, ingress.Limits{MaxBytes: len(row), MaxDepth: 64})
		if err != nil {
			return nil, err
		}
		output = append(output, fragment)
	}
	return output, nil
}

// ValidateTreatment checks typed target, pin, owner and outcome through native SDL.
func ValidateTreatment(family Scenario, treatment admission.Fragment) error {
	owned, err := nativeScenario(family)
	if err != nil {
		return err
	}
	if admission.CheckFragment(treatment, admission.RealizationValue) != nil {
		return invalidScenario()
	}
	raw, err := json.Marshal(treatment.Document())
	if err != nil {
		return invalidScenario()
	}
	return owned.parser.ValidateTreatment(owned.document, raw)
}
