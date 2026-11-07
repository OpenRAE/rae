package authoring

import (
	"encoding/json"
	"math/big"
)

func (a autonomousChecks) activity() bool {
	profile := text(a.policy["profile"])
	return profile == "participant-autonomous-execution/v2" || profile == "participant-autonomous-execution/v3"
}
func (a autonomousChecks) time() error {
	clockRef, progressionRef := text(a.policy["clock_ref"]), text(a.policy["progression_policy_ref"])
	if err := referencesPresent([]any{clockRef}, object(a.root.value["clocks"])); err != nil {
		return err
	}
	if err := referencesPresent([]any{progressionRef}, object(a.root.value["time_progression_policies"])); err != nil {
		return err
	}
	progression := object(object(a.root.value["time_progression_policies"])[progressionRef])
	if progression != nil && text(progression["clock_ref"]) != clockRef {
		return semanticInvalid()
	}
	refs := array(a.policy["temporal_constraint_refs"])
	if a.activity() {
		refs = append(append([]any{}, array(a.policy["work_window_refs"])...), array(a.policy["pause_window_refs"])...)
	}
	cadence, count := map[string]any(nil), 0
	for _, ref := range concreteRefs(refs) {
		constraint, err := a.constraint(ref, clockRef)
		if err != nil {
			return err
		}
		if constraint["constraint_kind"] == "cadence" {
			cadence = constraint
			count++
		}
	}
	if !a.activity() && count != 1 {
		return semanticInvalid()
	}
	return a.progression(progression, cadence, count)
}
func (a autonomousChecks) constraint(ref, clock string) (map[string]any, error) {
	registry := object(a.root.value["temporal_constraints"])
	name, ok := sectionRef(ref, "temporal_constraints", registry)
	if !ok {
		return nil, semanticInvalid()
	}
	constraint := object(registry[name])
	if text(constraint["clock_ref"]) != clock {
		return nil, semanticInvalid()
	}
	if a.activity() {
		if constraint["constraint_kind"] != "window" {
			return nil, semanticInvalid()
		}
		subjects := stringSet(array(constraint["subject_refs"]))
		if !subjects[a.name] {
			for participant := range a.participants {
				if !subjects[participant] {
					return nil, semanticInvalid()
				}
			}
		}
	}
	return constraint, nil
}
func (a autonomousChecks) progression(progression, cadence map[string]any, count int) error {
	start := object(cadence["start"])["tick"]
	if start == nil {
		start = json.Number("0")
	}
	if count == 1 {
		integer, ok := modelInteger(start)
		if !ok || integer.Sign() < 0 {
			return semanticInvalid()
		}
	}
	if progression["advancement_mode"] != "stepped" {
		return nil
	}
	step, valid := modelInteger(progression["step_ticks"])
	if a.activity() {
		return a.activityTiming(step, valid)
	} else if count == 1 {
		tick, ok := modelInteger(start)
		period, periodOK := modelInteger(cadence["cadence_ticks"])
		if !valid || !ok || !periodOK || !divisible(tick, step) || !divisible(period, step) {
			return semanticInvalid()
		}
	}
	return nil
}
func divisible(value, step *big.Int) bool {
	return step.Sign() != 0 && new(big.Int).Rem(value, step).Sign() == 0
}

func (a autonomousChecks) activityTiming(step *big.Int, valid bool) error {
	if !valid {
		return nil
	}
	for _, field := range []string{"minimum_ticks", "maximum_ticks"} {
		bound, ok := modelInteger(object(a.policy["timing"])[field])
		if ok && !divisible(bound, step) {
			return semanticInvalid()
		}
	}
	return nil
}
