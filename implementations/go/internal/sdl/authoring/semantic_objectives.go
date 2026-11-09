package authoring

import (
	"encoding/json"
	"fmt"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

type semanticObjective struct {
	name         string
	Participant  string   `json:"assigned_participant"`
	Owner        string   `json:"owner"`
	Actions      []string `json:"actions"`
	Targets      []string `json:"targets"`
	Dependencies []string `json:"depends_on"`
	Success      struct {
		Assertions []string `json:"assertions"`
	} `json:"success"`
	Window *semanticObjectiveWindow `json:"window"`
}
type semanticObjectiveWindow struct {
	Stories   []string `json:"stories"`
	Scripts   []string `json:"scripts"`
	Events    []string `json:"events"`
	Workflows []string `json:"workflows"`
	Steps     []string `json:"steps"`
}

func (m *semanticModel) objectiveFacts() error {
	values := fieldValue(m.transport.Objectives)
	for _, name := range m.keys(objectivesSection) {
		row := semanticObjective{name: name}
		if err := json.Unmarshal(values[name], &row); err != nil {
			return invalid()
		}
		m.objectives = append(m.objectives, row)
	}
	return nil
}
func (m *semanticModel) checkObjectives(c *semanticCollector) {
	dependencies := map[string][]string{}
	for _, row := range m.objectives {
		owner := semanticOwner{objectivesSection, row.name}
		m.checkObjectiveRelations(c, row)
		seen := map[string]bool{}
		for _, ref := range row.Actions {
			if seen[ref] {
				continue
			}
			seen[ref] = true
			if !variable(ref) && !m.definitions[actionsSection][ref] {
				c.report(owner, fmt.Sprintf("Objective '%s' action '%s' must reference a declared action_contract", row.name, ref))
			}
		}
		for _, ref := range row.Targets {
			m.namedReference(c, owner, "Objective '"+row.name+"'", "target", ref, referenceObjectiveSubject)
		}
		m.checkObjectiveSuccessReferences(c, row)
		if row.Window != nil {
			m.checkObjectiveWindow(c, row.name, *row.Window)
		}
		dependencies[row.name] = m.checkObjectiveDependencies(c, row)
	}
	if graph.HasCycle(dependencies) {
		c.report(semanticOwner{}, "Objective dependency graph contains a cycle")
	}
}
func (m *semanticModel) checkObjectiveRelations(c *semanticCollector, row semanticObjective) {
	owner := semanticOwner{objectivesSection, row.name}
	if row.Participant != "" && !variable(row.Participant) {
		if !m.definitions[agentsSection][row.Participant] {
			c.report(owner, fmt.Sprintf("Objective '%s' references undefined agent '%s'", row.name, row.Participant))
		} else {
			allowed := fieldValue(fieldValue(m.transport.Agents)[row.Participant].Actions)
			for _, ref := range row.Actions {
				if !variable(ref) && !slices.Contains(allowed, ref) {
					c.report(owner, fmt.Sprintf("Objective '%s' action '%s' is not declared by agent '%s'", row.name, ref, row.Participant))
				}
			}
		}
	}
	if row.Owner != "" && !variable(row.Owner) && !m.entityNames[row.Owner] {
		c.report(owner, fmt.Sprintf("Objective '%s' references undefined entity '%s'", row.name, row.Owner))
	}
}
func (m *semanticModel) checkObjectiveSuccessReferences(c *semanticCollector, row semanticObjective) {
	for _, ref := range row.Success.Assertions {
		if !variable(ref) && !m.definitions[assertionsSection][ref] {
			c.report(semanticOwner{objectivesSection, row.name}, fmt.Sprintf("Objective '%s' references undefined assertion '%s' in success criteria", row.name, ref))
		}
	}
}
func (m *semanticModel) checkObjectiveDependencies(c *semanticCollector, row semanticObjective) []string {
	var result []string
	for _, ref := range row.Dependencies {
		if variable(ref) {
			continue
		}
		if !m.definitions[objectivesSection][ref] {
			c.report(semanticOwner{objectivesSection, row.name}, fmt.Sprintf("Objective '%s' depends on undefined objective '%s'", row.name, ref))
		} else {
			result = append(result, ref)
		}
	}
	return result
}
func (m *semanticModel) checkObjectiveAssertionRoles(c *semanticCollector) {
	assertions := fieldValue(m.transport.Assertions)
	for _, row := range m.objectives {
		for _, ref := range row.Success.Assertions {
			if variable(ref) {
				continue
			}
			value, present := assertions[ref]
			owner := semanticOwner{objectivesSection, row.name}
			switch {
			case !present:
				c.report(owner, fmt.Sprintf("Objective '%s' success assertion '%s' not in assertions section", row.name, ref))
			case string(fieldValue(value.Role)) != "invariant" && string(fieldValue(value.Role)) != "postcondition":
				c.report(owner, fmt.Sprintf("Objective '%s' success assertion '%s' must be an invariant or postcondition", row.name, ref))
			}
		}
	}
}
func (m *semanticModel) checkPreconditionAssertionUses(c *semanticCollector) {
	for _, name := range m.keys(eventsSection) {
		m.checkPreconditionUses(c, semanticOwner{eventsSection, name}, "Event '"+name+"'", "event trigger", fieldValue(fieldValue(m.transport.Events)[name].Assertions))
	}
	for _, name := range m.keys(agentsSection) {
		m.checkPreconditionUses(c, semanticOwner{agentsSection, name}, "Agent '"+name+"'", "agent starting state", fieldValue(fieldValue(m.transport.Agents)[name].StartingAssertions))
	}
}
func (m *semanticModel) checkPreconditionUses(c *semanticCollector, owner semanticOwner, label, use string, refs []string) {
	assertions := fieldValue(m.transport.Assertions)
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		value, present := assertions[ref]
		switch {
		case !present:
			c.report(owner, fmt.Sprintf("%s assertion '%s' not in assertions section", label, ref))
		case string(fieldValue(value.Role)) != "precondition":
			c.report(owner, fmt.Sprintf("%s assertion '%s' %s must be a precondition", label, ref, use))
		}
	}
}
