package admission

import (
	"encoding/json"
	"regexp"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

// AvailableControlTarget adds the participant-wide position after which an
// owner-supplied target exists. It does not grant control authority by itself.
type AvailableControlTarget struct {
	Target      ControlTarget
	AvailableAt json.Number
}

// ControlOccurrenceHistoryContext supplies pinned policy projections and
// external target positions for complete mixed-lineage control prefixes.
type ControlOccurrenceHistoryContext interface {
	ControlOccurrenceContext
	ControlOccurrencePolicies() [][]byte
	ControlAvailableTargets() []AvailableControlTarget
}

var controlReferencePattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9._:/@-]*$`)

func controlReference(v any) bool {
	value, ok := v.(string)
	return ok && len(value) <= 256 && controlReferencePattern.MatchString(value)
}

func controlCount(v any) bool {
	value, ok := number(v)
	return ok && value.IsInt() && value.Sign() >= 0 && !numericGreater(v, json.Number("1000000"))
}

func closedControlObject(v any, required, optional []string) bool {
	if object(v) == nil {
		return false
	}
	allowed := map[string]bool{}
	for _, field := range required {
		if _, exists := object(v)[field]; !exists {
			return false
		}
		allowed[field] = true
	}
	for _, field := range optional {
		allowed[field] = true
	}
	for field := range object(v) {
		if !allowed[field] {
			return false
		}
	}
	return true
}

func controlReferenceList(v any, minimum int) bool {
	rows, ok := v.([]any)
	if !ok || len(rows) < minimum || len(rows) > 256 {
		return false
	}
	for _, row := range rows {
		if !controlReference(row) {
			return false
		}
	}
	return true
}

func (e *Validator) controlPolicy(raw []byte) (any, error) {
	limits := ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}
	v, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		return nil, invalid()
	}
	required := []string{"semantics", fieldParticipantAddress, fieldEpisodeID, "pin", "order_strategy", "initial_state_ref", "behavior_scope_refs", "states", termTransitions}
	if !closedControlObject(v, required, []string{"script_steps"}) || stringAt(v, "semantics") != "mixed-control-policy-occurrence/rev1" || !controlReference(at(v, fieldParticipantAddress)) || !controlReference(at(v, fieldEpisodeID)) || !controlReference(at(v, "initial_state_ref")) || stringAt(v, "order_strategy") == "" || !controlReferenceList(at(v, "behavior_scope_refs"), 1) {
		return nil, invalid()
	}
	pinRaw, err := json.Marshal(at(v, "pin"))
	if err != nil {
		return nil, invalid()
	}
	if _, err := e.low.DecodeObjectFragment(termParticipantControlOccurrenceV2, "#/$defs/ParticipantControlPolicyPinModel", pinRaw, limits); err != nil {
		return nil, err
	}
	if _, present := object(v)["script_steps"]; !present {
		object(v)["script_steps"] = []any{}
	}
	if err := controlPolicyRows(v); err != nil {
		return nil, err
	}
	return v, nil
}

func controlPolicyRows(v any) error {
	states, transitions, steps := array(at(v, "states")), array(at(v, termTransitions)), array(at(v, "script_steps"))
	if _, ok := at(v, "script_steps").([]any); !ok {
		return invalid()
	}
	if len(states) == 0 || len(transitions) == 0 || len(states)+len(transitions)+len(steps) > 100000 {
		return invalid()
	}
	if len(rowSet(states, "state_ref")) != len(states) || len(rowSet(transitions, termTransitionRef)) != len(transitions) || len(rowSet(steps, "step_ref")) != len(steps) {
		return invalid()
	}
	knownStates, knownTransitions := rowSet(states, "state_ref"), rowSet(transitions, termTransitionRef)
	if !knownStates[stringAt(v, "initial_state_ref")] || (stringAt(v, "pin", "form") == termFiniteScript) != (len(steps) > 0) {
		return invalid()
	}
	return controlPolicyChildren(states, transitions, steps, knownStates, knownTransitions)
}

func controlPolicyState(v any) error {
	if !closedControlObject(v, []string{"state_ref", "controller_ref", "authority_basis_refs", "scope_refs", "authority_status", termValidFromOrder, termValidUntilOrder}, nil) || !controlReference(at(v, "state_ref")) || !controlReference(at(v, "controller_ref")) || !controlReferenceList(at(v, "authority_basis_refs"), 1) || !controlReferenceList(at(v, "scope_refs"), 1) || !controlCount(at(v, termValidFromOrder)) || !controlCount(at(v, termValidUntilOrder)) {
		return invalid()
	}
	return require(stringAt(v, "authority_status") == termActive || stringAt(v, "authority_status") == termRevoked)
}

func controlPolicyTransition(v any, states map[string]bool) error {
	if !closedControlObject(v, []string{termTransitionRef, termKind, "from_state_ref", "to_state_ref", termValidFromOrder, termValidUntilOrder}, []string{"target_kinds"}) || !controlReference(at(v, termTransitionRef)) || !controlTransitionKind(stringAt(v, termKind)) || !states[stringAt(v, "from_state_ref")] || !states[stringAt(v, "to_state_ref")] || !controlCount(at(v, termValidFromOrder)) || !controlCount(at(v, termValidUntilOrder)) {
		return invalid()
	}
	if _, present := object(v)["target_kinds"]; !present {
		object(v)["target_kinds"] = []any{}
	}
	rows, ok := at(v, "target_kinds").([]any)
	if !ok {
		return invalid()
	}
	for _, kind := range rows {
		if !controlTargetKind(text(kind)) {
			return invalid()
		}
	}
	return nil
}

func controlTargetKind(kind string) bool {
	return map[string]bool{"proposal": true, "action": true, messageControl: true, termDecision: true, "admitted-action": true, termAttempt: true}[kind]
}

func controlPolicyStep(v any, transitions map[string]bool) error {
	optional := []string{termExpectedStateRevision, termValidFromOrder, termValidUntilOrder, "target_kind", "target_step_ref"}
	if !closedControlObject(v, []string{"step_ref", termTransitionRef}, optional) || !controlReference(at(v, "step_ref")) || !transitions[stringAt(v, termTransitionRef)] {
		return invalid()
	}
	for _, field := range []string{termExpectedStateRevision, termValidFromOrder, termValidUntilOrder} {
		if at(v, field) != nil && !controlCount(at(v, field)) {
			return invalid()
		}
	}
	if at(v, "target_kind") != nil && !controlTargetKind(stringAt(v, "target_kind")) || at(v, "target_step_ref") != nil && !controlReference(at(v, "target_step_ref")) {
		return invalid()
	}
	for _, field := range optional {
		if _, exists := object(v)[field]; !exists {
			object(v)[field] = nil
		}
	}
	return nil
}

func controlPolicyChildren(states, transitions, steps []any, knownStates, knownTransitions map[string]bool) error {
	for _, state := range states {
		if err := controlPolicyState(state); err != nil {
			return err
		}
	}
	for _, transition := range transitions {
		if err := controlPolicyTransition(transition, knownStates); err != nil {
			return err
		}
	}
	for _, step := range steps {
		if err := controlPolicyStep(step, knownTransitions); err != nil {
			return err
		}
	}
	return nil
}
