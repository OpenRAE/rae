package authoring

import (
	"encoding/json"
	"math/big"
	"slices"
)

type semanticCadence struct {
	start, period *big.Int
	count         int
}

func (a semanticAutonomousCheck) activity() bool {
	return a.policy.Profile == "participant-autonomous-execution/v2" || a.policy.Profile == "participant-autonomous-execution/v3"
}
func (a semanticAutonomousCheck) time() {
	m, p := a.model, a.policy
	if _, known := fieldValue(m.transport.Clocks)[p.Clock]; !known && !variable(p.Clock) {
		a.reportf("autonomous clock_ref '%s' is not declared", p.Clock)
	}
	progression, known := fieldValue(m.transport.TimeProgressionPolicies)[p.Progression]
	if !known && !variable(p.Progression) {
		a.reportf("autonomous progression_policy_ref '%s' is not declared", p.Progression)
	} else if known && fieldValue(progression.ClockRef) != p.Clock {
		a.reportf("autonomous progression policy '%s' uses another clock", p.Progression)
	}
	cadence := a.constraints()
	if cadence.count == 1 && (cadence.start == nil || cadence.start.Sign() < 0) {
		a.reportf("cadence points are unreachable by stepped progression '%s'", p.Progression)
	}
	if string(fieldValue(progression.AdvancementMode)) != "stepped" {
		return
	}
	step, _ := modelInteger(json.Number(fieldValue(progression.StepTicks)))
	if a.activity() {
		a.activityTiming(step)
	} else if cadence.count == 1 && !cadence.reachable(step) {
		a.reportf("cadence points are unreachable by stepped progression '%s'", p.Progression)
	}
}
func (cadence semanticCadence) reachable(step *big.Int) bool {
	return step != nil && cadence.start != nil && cadence.period != nil && cadence.start.Sign() >= 0 && divisible(cadence.start, step) && divisible(cadence.period, step)
}
func (a semanticAutonomousCheck) constraints() semanticCadence {
	refs := a.policy.Constraints
	if a.activity() {
		refs = append(slices.Clone(a.policy.Work), a.policy.Pause...)
	}
	var cadence semanticCadence
	for _, ref := range refs {
		a.constraint(ref, &cadence)
	}
	if !a.activity() && cadence.count != 1 {
		a.reportf("autonomous execution requires exactly one cadence constraint")
	}
	return cadence
}
func (a semanticAutonomousCheck) constraint(ref string, cadence *semanticCadence) {
	if variable(ref) {
		return
	}
	name, known := a.model.sectionReference(ref, temporalConstraintsSection)
	if !known {
		a.reportf("autonomous temporal constraint '%s' is not declared", ref)
		return
	}
	row := fieldValue(a.model.transport.TemporalConstraints)[name]
	kind := string(fieldValue(row.ConstraintKind))
	if a.activity() {
		a.windowSubject(ref, kind, fieldValue(row.SubjectRefs))
	}
	if fieldValue(row.ClockRef) != a.policy.Clock {
		a.reportf("autonomous temporal constraint '%s' uses another clock", ref)
	}
	if kind != "cadence" {
		return
	}
	cadence.count++
	cadence.start, cadence.period = a.model.cadenceValues[name].start, a.model.cadenceValues[name].period
}
func (a semanticAutonomousCheck) windowSubject(ref, kind string, subjects []string) {
	if kind != "window" {
		a.reportf("activity work and pause refs must resolve to window constraints; '%s' does not", ref)
		return
	}
	if slices.Contains(subjects, a.row.name) {
		return
	}
	for _, name := range a.participants {
		if !slices.Contains(subjects, name) {
			a.reportf("activity window '%s' must name the behavior specification or every governed participant as a subject", ref)
			return
		}
	}
}
func (a semanticAutonomousCheck) activityTiming(step *big.Int) {
	if step == nil {
		return
	}
	for _, raw := range []json.RawMessage{a.policy.Timing.Minimum, a.policy.Timing.Maximum} {
		bound, ok := modelInteger(json.Number(raw))
		if ok && !divisible(bound, step) {
			a.reportf("activity timing bounds are unreachable by stepped progression '%s'", a.policy.Progression)
			return
		}
	}
}
func (m *semanticModel) cadenceFacts() error {
	m.cadenceValues = map[string]semanticCadence{}
	m.timeCoordinates = map[string]semanticInterval{}
	for name, row := range fieldValue(m.transport.TemporalConstraints) {
		start, err := decodeSemanticCoordinate(fieldValue(row.Start))
		if err != nil {
			return err
		}
		end, err := decodeSemanticCoordinate(fieldValue(row.End))
		if err != nil {
			return err
		}
		m.timeCoordinates[name] = semanticInterval{start, end}
		if fieldValue(row.ConstraintKind) != "cadence" {
			continue
		}
		tickValue := json.Number("0")
		if start != nil {
			tickValue = start.Tick
		}
		tick, _ := modelInteger(tickValue)
		period, _ := modelInteger(json.Number(fieldValue(row.CadenceTicks)))
		m.cadenceValues[name] = semanticCadence{start: tick, period: period}
	}
	return nil
}
func divisible(value, step *big.Int) bool {
	return step.Sign() != 0 && new(big.Int).Rem(value, step).Sign() == 0
}
