package sdlrules

import (
	"fmt"
	"slices"
)

// TemporalBindings reports the shared clock, constraint, dwell, and policy joins
// in constructed normalized SDL. Mapping order uses JSON pointers; absent
// entries use lexical order. Neither caller input nor order is changed.
func TemporalBindings(data []byte, order map[string][]string) ([]Finding, error) {
	m, err := decodeTemporal(data, order)
	if err != nil {
		return nil, err
	}
	for _, action := range m.actions {
		for _, temporal := range action.contracts {
			m.checkBinding(action, temporal)
		}
	}
	return m.findings, nil
}
func (m *temporalModel) report(action temporalAction, row temporalContract, message string) {
	m.findings = append(m.findings, Finding{Owner{actionsSection, action.name}, fmt.Sprintf("Action '%s' temporal binding '%s' %s", action.name, row.id, message)})
}
func (m *temporalModel) checkBinding(action temporalAction, row temporalContract) {
	clock, hasClock := sectionReference(row.binding.Clock, "clocks", fieldValue(m.input.Clocks))
	constraint, hasConstraint := sectionReference(row.binding.Constraint, constraintsSection, fieldValue(m.input.TemporalConstraints))
	if !hasClock && !unresolved(row.binding.Clock) {
		m.report(action, row, "clock_ref is not declared")
	}
	if !hasConstraint && !unresolved(row.binding.Constraint) {
		m.report(action, row, "constraint_ref is not declared")
	}
	if !hasClock || !hasConstraint {
		return
	}
	m.sharedClock(action, row, clock, constraint)
	if row.kind == "dwell" {
		m.dwell(action, row, constraint)
	}
	m.policyClock(action, row, clock)
}
func (m *temporalModel) sharedClock(action temporalAction, row temporalContract, clockName, constraintName string) {
	constraint := fieldValue(m.input.TemporalConstraints)[constraintName]
	if fieldValue(constraint.ClockRef) != clockName {
		m.report(action, row, "constraint uses another clock")
	}
	clock := fieldValue(m.input.Clocks)[clockName]
	domainName, known := sectionReference(fieldValue(clock.TimeDomainRef), "time_domains", fieldValue(m.input.TimeDomains))
	if known {
		domain := fieldValue(m.input.TimeDomains)[domainName]
		expected := map[string]string{"simulated": "simulation_time", "wall_clock": "wall_clock_time", "logical": "scenario_time", "monotonic": "scenario_time", "external": "backend_time"}[string(fieldValue(domain.Kind))]
		if row.domain != expected {
			m.report(action, row, "time domain contradicts its shared clock declaration")
		}
	}
	kind := "window"
	if row.kind == "deadline" {
		kind = "deadline"
	}
	if string(fieldValue(constraint.ConstraintKind)) != kind {
		m.report(action, row, "requires a "+kind+" constraint")
	}
	subjects := fieldValue(constraint.SubjectRefs)
	if !slices.Contains(subjects, action.name) && !slices.Contains(subjects, actionsSection+"."+action.name) {
		m.report(action, row, "constraint must name the bound action as a subject")
	}
}
func (m *temporalModel) policyClock(action temporalAction, row temporalContract, clockName string) {
	for _, policy := range m.policies {
		if !referencesName(policy.Actions, action.name, actionsSection, fieldValue(m.input.ActionContracts)) {
			continue
		}
		name, known := sectionReference(policy.Clock, "clocks", fieldValue(m.input.Clocks))
		if known && name != clockName {
			m.report(action, row, "must use its autonomous policy's shared clock")
		}
	}
}
func (m *temporalModel) dwell(action temporalAction, row temporalContract, constraintName string) {
	var condition *temporalCondition
	for _, candidate := range action.conditions {
		if candidate.id == row.binding.Condition {
			copyCondition := candidate
			condition = &copyCondition
			break
		}
	}
	if condition == nil {
		m.report(action, row, "condition_precondition_id must name a precondition of the bound action")
	}
	boundary, known := sectionReference(row.binding.Boundary, boundariesSection, fieldValue(m.input.ObservationBoundaries))
	if !known && !unresolved(row.binding.Boundary) {
		m.report(action, row, "observation_boundary_ref is not declared")
	}
	if known {
		if condition != nil {
			m.dwellObservation(action, row, boundary, *condition)
		}
		m.dwellBoundaryOwners(action, row, boundary)
	}
	if m.coordinates[constraintName].invalid() {
		m.report(action, row, "dwell requires a nonempty interval within one clock segment")
	}
}
func (m *temporalModel) dwellObservation(action temporalAction, row temporalContract, name string, condition temporalCondition) {
	boundary := fieldValue(m.input.ObservationBoundaries)[name]
	observable := map[string]bool{}
	for _, ref := range fieldValue(boundary.ObservableRefs) {
		observable[ref] = true
	}
	for _, rule := range fieldValue(boundary.ViewRules) {
		ref := fieldValue(rule.InformationRef)
		observable[ref] = slices.Contains([]string{"observable", "disclosed", "discovered", "inferred", "deceptive"}, string(fieldValue(rule.Disposition)))
	}
	for _, ref := range condition.support {
		if !observable[ref] && !unresolved(ref) {
			m.report(action, row, "condition support must be observable through its boundary")
			break
		}
	}
	for _, ref := range condition.evidence {
		if !slices.Contains(fieldValue(boundary.EvidenceRefs), ref) && !unresolved(ref) {
			m.report(action, row, "condition evidence must be declared by its boundary")
			break
		}
	}
}
func (m *temporalModel) dwellBoundaryOwners(action temporalAction, row temporalContract, boundary string) {
	agents := fieldValue(m.input.Agents)
	for _, name := range orderedKeys(agents, m.order, "agents") {
		agent := agents[name]
		if referencesName(fieldValue(agent.Actions), action.name, actionsSection, fieldValue(m.input.ActionContracts)) && !referencesName(fieldValue(agent.ObservationBoundaries), boundary, boundariesSection, fieldValue(m.input.ObservationBoundaries)) {
			m.report(action, row, "observation boundary is outside participant '"+name+"'")
		}
	}
	m.dwellBehaviorBoundaryOwners(action, row, boundary)
}
func (m *temporalModel) dwellBehaviorBoundaryOwners(action temporalAction, row temporalContract, boundary string) {
	specs := fieldValue(m.input.BehaviorSpecifications)
	for _, name := range orderedKeys(specs, m.order, behaviorSection) {
		spec := specs[name]
		if !referencesName(fieldValue(spec.ActionContractRefs), action.name, actionsSection, fieldValue(m.input.ActionContracts)) {
			continue
		}
		if !referencesName(fieldValue(spec.ObservationBoundaryRefs), boundary, boundariesSection, fieldValue(m.input.ObservationBoundaries)) {
			m.report(action, row, "observation boundary is outside its behavior specification")
		}
		if policy, active := m.policyBySpec[name]; active {
			selected, known := sectionReference(policy.Boundary, boundariesSection, fieldValue(m.input.ObservationBoundaries))
			if known && selected != boundary {
				m.report(action, row, "must use its autonomous policy's observation boundary")
			}
		}
	}
}
