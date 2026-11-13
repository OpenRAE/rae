package processor

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

// CaptureInputs supplies explicit capture artifacts and their authored relation owner.
type CaptureInputs struct {
	CaptureSpecs      []binding.ExperimentCaptureSpecV1
	EvidenceRelations []admission.Fragment
	RelationScenario  sdl.Scenario
}

// CompileCaptureDemands conjoins supplied capture specifications with the
// scenario's mandatory evidence requirements without asserting capture.
// A nil scenario admits capture specifications only, without scoped relations.
func CompileCaptureDemands(scenario sdl.Scenario, inputs CaptureInputs) ([]CaptureDemand, error) {
	if scenario == nil && len(inputs.EvidenceRelations) > 0 {
		return nil, invalidCompiled()
	}
	sources := map[string]evidenceSource{}
	if scenario != nil {
		raw, err := sdl.ModelBytes(scenario)
		if err != nil {
			return nil, err
		}
		var document struct {
			Requirements map[string]evidenceSource `json:"evidence_requirements"`
		}
		if json.Unmarshal(raw, &document) != nil {
			return nil, invalidCompiled()
		}
		sources = document.Requirements
	}
	return conjoinCaptureDemandInputs(scenario, inputs, scenarioCaptureDemandValues(sources))
}

func conjoinCaptureDemandInputs(scenario sdl.Scenario, inputs CaptureInputs, base []CaptureDemand) ([]CaptureDemand, error) {
	owner, err := processorAdmissionOwner()
	if err != nil {
		return nil, err
	}
	contexts := []admission.EvidenceScenario{}
	if len(inputs.EvidenceRelations) > 0 {
		authored := inputs.RelationScenario
		if authored == nil {
			authored = scenario
		}
		context, contextErr := sdl.EvidenceScenario(authored)
		if contextErr != nil {
			return nil, contextErr
		}
		contexts = append(contexts, context)
	}
	if relationErr := admission.CheckEvidenceRequirementRelations(owner, inputs.EvidenceRelations, contexts, inputs.CaptureSpecs); relationErr != nil {
		return nil, relationErr
	}
	supplied, err := captureSpecDemandValues(inputs.CaptureSpecs)
	if err != nil {
		return nil, err
	}
	base = append(base, supplied...)
	result := base
	if err := value.ValidateProjected(result, value.Plan(), captureDemandWorkValue); err != nil {
		return nil, err
	}
	for index := range result {
		result[index].Payload = ResourcePayload{data: rawJSON(captureDemandProjection(result[index]))}
	}
	return result, nil
}

func captureDemandWorkValue(input any) (any, error) {
	switch item := input.(type) {
	case []CaptureDemand:
		if len(item) > value.Plan().MaxMembers {
			return nil, invalidCompiled()
		}
		result := make([]any, len(item))
		for index := range item {
			result[index] = &item[index]
		}
		return result, nil
	case *CaptureDemand:
		return captureDemandProjection(*item), nil
	case []string:
		if len(item) > value.Plan().MaxMembers {
			return nil, invalidCompiled()
		}
		result := make([]any, len(item))
		for index, text := range item {
			result[index] = text
		}
		return result, nil
	case *string:
		if item == nil {
			return nil, nil //nolint:nilnil // Null is an admitted JSON projection, not an absent result.
		}
		return *item, nil
	default:
		return input, nil
	}
}
