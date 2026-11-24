package admission

import (
	"encoding/json"
	"reflect"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

type captureRelationContext struct {
	scenarios []EvidenceScenario
	specs     [][]byte
}

func (c captureRelationContext) EvidenceScenarios() []EvidenceScenario { return c.scenarios }
func (c captureRelationContext) CaptureSpecs() [][]byte                { return c.specs }

// CheckEvidenceRequirementRelations resolves only the supplied native
// artifacts. It reuses the existing relation and refinement owner and grants
// no capture, runtime execution, or evidence publication authority.
func CheckEvidenceRequirementRelations(v *Validator, relations []Fragment, scenarios []EvidenceScenario, specs []binding.ExperimentCaptureSpecV1) error {
	if v == nil || v.low == nil || max(len(relations), len(scenarios), len(specs)) > 16384 {
		return invalid()
	}
	for _, relation := range relations {
		if CheckFragment(relation, ExperimentEvidenceRequirementRelation) != nil {
			return fragmentInvalid()
		}
	}
	inputs := captureRelationInputs{relations, scenarios, specs}
	work := value.Plan()
	projection := captureRelationProjection{transport: transportProjection{limits: work, bytes: work.MaxTotalScalarBytes}}
	if err := value.ValidateProjected(inputs, work, projection.project); err != nil {
		return err
	}
	context, err := captureRelationArtifacts(v, scenarios, specs)
	if err != nil {
		return err
	}
	known := map[string]bool{}
	for _, input := range relations {
		owned, err := nativeFragment(input, ExperimentEvidenceRequirementRelation)
		if err != nil {
			return err
		}
		document := owned.Document()
		id := stringAt(document, "relation_id")
		if known[id] {
			return invalid()
		}
		known[id] = true
		if err := v.evidenceRelation(validation.Invocation{Instance: document, Context: context}); err != nil {
			return err
		}
	}
	return nil
}

func captureRelationArtifacts(v *Validator, scenarios []EvidenceScenario, specs []binding.ExperimentCaptureSpecV1) (captureRelationContext, error) {
	result := captureRelationContext{scenarios: slices.Clone(scenarios), specs: make([][]byte, len(specs))}
	for index := range specs {
		raw, err := json.Marshal(specs[index])
		if err != nil {
			return captureRelationContext{}, invalid()
		}
		if err := v.CheckPortable("experiment-capture-spec-v1", raw, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
			return captureRelationContext{}, err
		}
		result.specs[index] = raw
	}
	return result, nil
}

type captureRelationInputs struct {
	relations []Fragment
	scenarios []EvidenceScenario
	specs     []binding.ExperimentCaptureSpecV1
}
type captureScenarioBatch []EvidenceScenario
type captureScenarioValue struct{ value *EvidenceScenario }
type captureRelationProjection struct{ transport transportProjection }

func (p *captureRelationProjection) project(input any) (any, error) {
	switch item := input.(type) {
	case captureRelationInputs:
		relations := make([]json.RawMessage, len(item.relations))
		for index, relation := range item.relations {
			owned, err := nativeFragment(relation, ExperimentEvidenceRequirementRelation)
			if err != nil {
				return nil, err
			}
			relations[index] = owned.data
		}
		return []any{transportValue{reflect.ValueOf(item.specs), true}, transportValue{reflect.ValueOf(relations), true}, captureScenarioBatch(item.scenarios)}, nil
	case captureScenarioBatch:
		result := make([]any, len(item))
		for index := range item {
			result[index] = captureScenarioValue{&item[index]}
		}
		return result, nil
	case captureScenarioValue:
		if item.value == nil || item.value.Value.ContractID() != termSdlAuthoringInputV1 {
			return nil, invalid()
		}
		return map[string]any{
			termDigest: transportValue{reflect.ValueOf(item.value.Digest), true},
			"scenario": transportValue{reflect.ValueOf(json.RawMessage(item.value.Value.JSON())), true},
		}, nil
	case transportValue:
		return p.transport.project(item)
	default:
		return nil, invalid()
	}
}
