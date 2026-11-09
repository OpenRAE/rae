package authoring

import (
	"fmt"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (m *semanticModel) checkTime(c *semanticCollector) {
	clocks, _ := m.transport.Clocks.Value()
	for _, name := range m.keys("clocks") {
		reference := fieldValue(clocks[name].TimeDomainRef)
		if !m.definitions["time_domains"][reference] {
			c.report(semanticOwner{"clocks", name}, fmt.Sprintf("Clock '%s' time_domain_ref '%s' does not reference a declared time domain", name, reference))
		}
	}
	m.checkTimeMappings(c)
	m.checkTimePolicies(c)
	constraints, _ := m.transport.TemporalConstraints.Value()
	workflowSteps := map[string]bool{}
	for _, workflow := range m.keys(workflowsSection) {
		for _, step := range m.keys(workflowsSection, workflow, "steps") {
			workflowSteps[workflow+"."+step] = true
		}
	}
	for _, name := range m.keys(temporalConstraintsSection) {
		constraint := constraints[name]
		clock := fieldValue(constraint.ClockRef)
		owner, label := semanticOwner{temporalConstraintsSection, name}, "Temporal constraint '"+name+"'"
		if !m.definitions["clocks"][clock] {
			c.report(owner, fmt.Sprintf("%s clock_ref '%s' does not reference a declared clock", label, clock))
		}
		for _, reference := range fieldValue(constraint.SubjectRefs) {
			if !workflowSteps[reference] {
				m.namedReference(c, owner, label, "subject_ref", reference, referenceDeclared)
			}
		}
	}
}

func (m *semanticModel) checkTimeMappings(c *semanticCollector) {
	domains, _ := m.transport.TimeDomains.Value()
	edges := map[string][]string{}
	for name := range domains {
		edges[name] = nil
	}
	pairs := map[[2]string]bool{}
	for _, name := range m.keys("time_domain_mappings") {
		m.checkTimeMapping(c, name, pairs, edges)
	}
	if graph.HasCycle(edges) {
		c.report(semanticOwner{}, "Time-domain mapping graph contains a cycle")
	}
}

func (m *semanticModel) checkTimeMapping(c *semanticCollector, name string, pairs map[[2]string]bool, edges map[string][]string) {
	domains := fieldValue(m.transport.TimeDomains)
	mapping := fieldValue(m.transport.TimeDomainMappings)[name]
	source, target := fieldValue(mapping.SourceDomainRef), fieldValue(mapping.TargetDomainRef)
	owner := semanticOwner{"time_domain_mappings", name}
	left, hasLeft := domains[source]
	right, hasRight := domains[target]
	if !hasLeft {
		c.report(owner, fmt.Sprintf("Time-domain mapping '%s' references undefined source domain '%s'", name, source))
	}
	if !hasRight {
		c.report(owner, fmt.Sprintf("Time-domain mapping '%s' references undefined target domain '%s'", name, target))
	}
	pair := [2]string{source, target}
	if pairs[pair] {
		c.report(owner, fmt.Sprintf("Time-domain mapping '%s' duplicates the mapping from '%s' to '%s'", name, source, target))
	}
	pairs[pair] = true
	if !hasLeft || !hasRight {
		return
	}
	edges[source] = append(edges[source], target)
	if fieldValue(mapping.MappingKind) != "identity" {
		return
	}
	leftPeriod, rightPeriod := fieldValue(left.TickPeriodSeconds), fieldValue(right.TickPeriodSeconds)
	if fieldValue(left.Epoch) != fieldValue(right.Epoch) || fieldValue(leftPeriod.Numerator) != fieldValue(rightPeriod.Numerator) || fieldValue(leftPeriod.Denominator) != fieldValue(rightPeriod.Denominator) {
		c.report(owner, fmt.Sprintf("Time-domain mapping '%s' identity endpoints must have the same tick period and epoch", name))
	}
}

func (m *semanticModel) checkTimePolicies(c *semanticCollector) {
	clocks, _ := m.transport.Clocks.Value()
	policies, _ := m.transport.TimeProgressionPolicies.Value()
	owners := map[string]string{}
	for _, name := range m.keys("time_progression_policies") {
		policy := policies[name]
		reference := fieldValue(policy.ClockRef)
		owner := semanticOwner{"time_progression_policies", name}
		if previous, present := owners[reference]; present {
			c.report(owner, fmt.Sprintf("Time progression policy '%s' duplicates clock_ref '%s' already owned by '%s'", name, reference, previous))
		}
		owners[reference] = name
		clock, present := clocks[reference]
		if !present {
			c.report(owner, fmt.Sprintf("Time progression policy '%s' clock_ref '%s' does not reference a declared clock", name, reference))
			continue
		}
		if fieldValue(policy.ResetBehavior) != "unsupported" && !fieldValue(clock.SupportsReset) {
			c.report(owner, fmt.Sprintf("Time progression policy '%s' requires reset behavior but clock '%s' does not support reset", name, reference))
		}
		if fieldValue(policy.ReplayBehavior) != "unsupported" && !fieldValue(clock.SupportsReset) {
			c.report(owner, fmt.Sprintf("Time progression policy '%s' requires replay behavior but clock '%s' cannot establish a reset segment", name, reference))
		}
	}
}
