package authoring

import (
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
)

// ResolveBindingTarget uses the admitted variation and declaration indexes.
func (d *Document) ResolveBindingTarget(scenarioFamilyID, pointID, suppliedTargetID string) (admission.ScenarioBindingResolution, error) {
	if d == nil || !d.Validated() || d.contract != expandedContract || scenarioFamilyID != text(d.semantic.root[nameField]) {
		return admission.ScenarioBindingResolution{}, selectionInvalid()
	}
	for _, point := range d.semantic.variations {
		if point.name != pointID {
			continue
		}
		if point.Target.Kind == termStructural || point.Kind == termSubset || point.Kind == termOrder {
			return admission.ScenarioBindingResolution{}, selectionInvalid()
		}
		target, err := d.semantic.trialTarget(point)
		if err != nil {
			return admission.ScenarioBindingResolution{}, err
		}
		kind := stringType
		if point.Target.Kind == termVariable {
			kind = d.semantic.variationVariables[point.Target.Variable].Type
		} else if point.Kind == termLogicalTiming {
			_, kind, _ = variationTimingSlot(point.Target.Slot)
		}

		if target != suppliedTargetID {
			return admission.ScenarioBindingResolution{}, selectionInvalid()
		}
		return admission.ScenarioBindingResolution{CanonicalTargetID: target, ValueType: kind, AllowedValueKinds: []string{termLiteral}, Sensitivity: "public", Owner: admission.BindingOwner{ContractID: "sdl-authoring-input-v1", ContractVersion: "1", ValidatorID: "raes-selected-scenario", ValidatorVersion: "1"}}, nil
	}
	return admission.ScenarioBindingResolution{}, selectionInvalid()
}
