package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (e *Validator) temporalRules() map[string]definition {
	return map[string]definition{
		"participant-shared-time-binding-shape":       {check: e.temporalBindings},
		"participant-shared-time-source-bindings":     {check: temporalSource},
		"participant-shared-time-history-consistency": {check: e.temporalHistory},
	}
}

func temporalBinding(i validation.Invocation) error {
	v := i.Instance
	start, end := at(v, termStart), at(v, termEnd)
	if stringAt(v, "temporal_kind") == termDwell {
		if start == nil || at(v, "condition_precondition_id") == nil || at(v, "observation_boundary_address") == nil {
			return invalid()
		}
		if stringAt(v, "evidence_mode") != termContinuous || stringAt(v, "event_point") != termStart {
			return invalid()
		}
		order, ok := coordinateCompare(start, end)
		if !ok || order >= 0 {
			return invalid()
		}
	} else if stringAt(v, "evidence_mode") != termEvent || at(v, "condition_precondition_id") != nil || at(v, "observation_boundary_address") != nil {
		return invalid()
	}
	if !set(at(v, "event_points"))[stringAt(v, "event_point")] {
		return invalid()
	}
	return require(numericEqual(at(end, "segment"), json.Number("0")) && (start == nil || numericEqual(at(start, "segment"), json.Number("0"))))
}
func coordinateCompare(a, b any) (int, bool) {
	a, b = coordinateView(a), coordinateView(b)
	if object(a) == nil || object(b) == nil {
		return 0, false
	}
	for _, field := range []string{"tick", termMicrostep} {
		left, ok := number(at(a, field))
		if !ok {
			return 0, false
		}
		right, ok := number(at(b, field))
		if !ok {
			return 0, false
		}
		if order := left.Cmp(right); order != 0 {
			return order, true
		}
	}
	return 0, true
}

// This annotation is attached to each containing contract root. Inspect only
// schema-owned binding instances; an arbitrary payload with similar keys does
// not become a temporal binding.
func (e *Validator) temporalBindings(i validation.Invocation) error {
	if i.Key.ContractID == "" {
		return temporalBinding(i)
	}
	raw, err := json.Marshal(i.Instance)
	if err != nil {
		return invalid()
	}
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	return e.low.CheckInstances(i.Key.ContractID, raw, limits, func(instance validation.SchemaInstance) error {
		if instance.SchemaPointer != "#/$defs/ParticipantTemporalBindingModel" {
			return nil
		}
		return e.defaultedTemporalBinding(instance)
	})
}

// defaultedTemporalBinding checks one binding instance with its published
// defaults applied.
func (e *Validator) defaultedTemporalBinding(instance validation.SchemaInstance) error {
	encoded, err := json.Marshal(instance.Value)
	if err != nil {
		return invalid()
	}
	normalized, err := e.low.DefaultedObjectFragment(instance.ContractID, instance.SchemaPointer, encoded, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
	if err != nil {
		return err
	}
	return temporalBinding(validation.Invocation{Instance: normalized})
}
