package authoring

import (
	"fmt"
	"strings"
)

func concreteUnique(refs []string) []string {
	seen := map[string]bool{}
	var result []string
	for _, ref := range refs {
		if !variable(ref) && !seen[ref] {
			result = append(result, ref)
			seen[ref] = true
		}
	}
	return result
}
func (m *semanticModel) objectiveWindowReference(c *semanticCollector, name, ref, section, kind string) bool {
	if m.definitions[section][ref] {
		return true
	}
	c.report(semanticOwner{objectivesSection, name}, fmt.Sprintf("Objective '%s' references undefined %s '%s' in window", name, kind, ref))
	return false
}
func (m *semanticModel) checkObjectiveWindow(c *semanticCollector, name string, window semanticObjectiveWindow) {
	stories := fieldValue(m.transport.Stories)
	reachableScripts := map[string]bool{}
	for _, ref := range concreteUnique(window.Stories) {
		if m.objectiveWindowReference(c, name, ref, storiesField, "story") {
			for _, script := range fieldValue(stories[ref].Scripts) {
				reachableScripts[script] = true
			}
		}
	}
	selectedScripts := map[string]bool{}
	for _, ref := range concreteUnique(window.Scripts) {
		if !m.objectiveWindowReference(c, name, ref, scriptsField, "script") {
			continue
		}
		if len(reachableScripts) > 0 && !reachableScripts[ref] {
			c.report(semanticOwner{objectivesSection, name}, fmt.Sprintf("Objective '%s' window script '%s' is not included by the referenced stories", name, ref))
		}
		selectedScripts[ref] = true
	}
	if len(selectedScripts) == 0 {
		selectedScripts = reachableScripts
	}
	m.checkObjectiveWindowEvents(c, name, window.Events, m.scriptEvents(selectedScripts))
	m.checkObjectiveWindowSteps(c, name, window)
}
func (m *semanticModel) scriptEvents(selectedScripts map[string]bool) map[string]bool {
	scripts := fieldValue(m.transport.Scripts)
	reachableEvents := map[string]bool{}
	for script := range selectedScripts {
		for event := range fieldValue(scripts[script].Events) {
			reachableEvents[event] = true
		}
	}
	return reachableEvents
}
func (m *semanticModel) checkObjectiveWindowEvents(c *semanticCollector, name string, refs []string, reachable map[string]bool) {
	for _, ref := range concreteUnique(refs) {
		if !m.objectiveWindowReference(c, name, ref, eventsSection, "event") {
			continue
		}
		if len(reachable) > 0 && !reachable[ref] {
			c.report(semanticOwner{objectivesSection, name}, fmt.Sprintf("Objective '%s' window event '%s' is not included by the referenced scripts", name, ref))
		}
	}
}
func (m *semanticModel) checkObjectiveWindowSteps(c *semanticCollector, name string, window semanticObjectiveWindow) {
	allowed := map[string]bool{}
	workflows, steps := concreteUnique(window.Workflows), concreteUnique(window.Steps)
	for _, ref := range workflows {
		if m.objectiveWindowReference(c, name, ref, workflowsSection, "workflow") {
			allowed[ref] = true
		}
	}
	if len(steps) > 0 && len(workflows) == 0 {
		c.report(semanticOwner{objectivesSection, name}, fmt.Sprintf("Objective '%s' window steps require at least one referenced workflow", name))
	}
	for _, ref := range steps {
		m.checkObjectiveWindowStep(c, name, ref, allowed)
	}
}
func workflowStepReference(ref string) (string, string, bool) {
	if len(ref) > 2048 {
		return "", "", false
	}
	parts := strings.Split(ref, ".")
	if len(parts) < 2 {
		return "", "", false
	}
	for i, part := range parts {
		if part == privateSegment && i < len(parts)-1 {
			continue
		}
		if !localIdentifier(part) {
			return "", "", false
		}
	}
	return strings.Join(parts[:len(parts)-1], "."), parts[len(parts)-1], true
}
func (m *semanticModel) checkObjectiveWindowStep(c *semanticCollector, name, ref string, allowed map[string]bool) {
	owner := semanticOwner{objectivesSection, name}
	workflow, step, valid := workflowStepReference(ref)
	if !valid {
		c.report(owner, fmt.Sprintf("Objective '%s' window step '%s' must use '<workflow>.<step>' syntax", name, ref))
		return
	}
	if !m.definitions[workflowsSection][workflow] {
		c.report(owner, fmt.Sprintf("Objective '%s' window step '%s' references undefined workflow '%s'", name, ref, workflow))
		return
	}
	if len(allowed) > 0 && !allowed[workflow] {
		c.report(owner, fmt.Sprintf("Objective '%s' window step '%s' is not part of the referenced workflows", name, ref))
	}
	if _, present := fieldValue(fieldValue(m.transport.Workflows)[workflow].Steps)[step]; !present {
		c.report(owner, fmt.Sprintf("Objective '%s' window step '%s' references undefined step '%s'", name, ref, step))
	}
}
