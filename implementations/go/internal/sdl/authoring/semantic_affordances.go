package authoring

import (
	"encoding/json"
	"fmt"
	"maps"
	"slices"
	"strings"
)

// semanticAffordance is the closed projection of ParticipantToolAffordance.
// Construction has already enforced the published field shapes and uniqueness.
type semanticAffordance struct {
	id           string
	Tool         *string  `json:"tool_ref"`
	Actions      []string `json:"action_contract_refs"`
	Boundaries   []string `json:"observation_boundary_refs"`
	Participants []string `json:"participant_refs"`
	Roles        []string `json:"participant_role_refs"`
}

func (m *semanticModel) affordanceFacts(name string) ([]semanticAffordance, error) {
	values := fieldValue(fieldValue(m.transport.BehaviorSpecifications)[name].ToolAffordances)
	var result []semanticAffordance
	for _, id := range m.keys(behaviorSection, name, toolAffordancesField) {
		row := semanticAffordance{id: id}
		if err := json.Unmarshal(values[id], &row); err != nil {
			return nil, invalid()
		}
		result = append(result, row)
	}
	return result, nil
}
func (m *semanticModel) selectParticipants(participants, roles []string) []string {
	selected := map[string]bool{}
	for _, name := range participants {
		if m.definitions[agentsSection][name] {
			selected[name] = true
		}
	}
	for name, role := range m.roles {
		if slices.Contains(roles, role) {
			selected[name] = true
		}
	}
	return slices.Sorted(maps.Keys(selected))
}
func (a semanticAffordance) signature() string {
	tool := ""
	if a.Tool != nil {
		tool = *a.Tool
	}
	actions, boundaries := slices.Clone(a.Actions), slices.Clone(a.Boundaries)
	slices.Sort(actions)
	slices.Sort(boundaries)
	// Quoted strings and slice delimiters keep tuple components distinct.
	return fmt.Sprintf("%q/%q/%q", tool, actions, boundaries)
}
func (m *semanticModel) behaviorToolAffordances(c *semanticCollector, row semanticBehavior) {
	seen := map[string]string{}
	parent := m.selectParticipants(row.participants, row.roles)
	for _, a := range row.affordances {
		owner := semanticOwner{behaviorSection, row.name}
		label := fmt.Sprintf("Behavior specification '%s' tool affordance '%s'", row.name, a.id)
		signature := a.signature()
		if original, ok := seen[signature]; ok {
			c.report(owner, fmt.Sprintf("Behavior specification '%s' has duplicate tool affordance relation '%s' matching '%s'; mapping order has no priority or fallback meaning", row.name, a.id, original))
		} else {
			seen[signature] = a.id
		}
		participants := m.affordanceParticipants(c, row, a, parent, label)
		m.affordanceActions(c, row, a, participants, label)
		m.affordanceBoundaries(c, row, a, participants, label)
	}
}
func (m *semanticModel) affordanceParticipants(c *semanticCollector, row semanticBehavior, a semanticAffordance, parent []string, label string) []string {
	if len(a.Participants) == 0 && len(a.Roles) == 0 {
		return parent
	}
	owner := semanticOwner{behaviorSection, row.name}
	m.affordanceSelectorReferences(c, owner, a, label)
	selected := m.selectParticipants(a.Participants, a.Roles)
	if slices.ContainsFunc(row.participants, func(ref string) bool { return variable(ref) }) || slices.ContainsFunc(row.roles, func(ref string) bool { return variable(ref) }) {
		return selected
	}
	for _, name := range selected {
		if !slices.Contains(parent, name) {
			c.report(owner, fmt.Sprintf("%s selects participant '%s' outside its owning behavior specification; binding selectors only narrow", label, name))
		}
	}
	return selected
}
func (m *semanticModel) affordanceSelectorReferences(c *semanticCollector, owner semanticOwner, a semanticAffordance, label string) {
	for _, ref := range a.Participants {
		if !variable(ref) && !m.definitions[agentsSection][ref] {
			c.report(owner, fmt.Sprintf("%s participant_ref '%s' does not reference a declared agent", label, ref))
		}
	}
	for _, ref := range a.Roles {
		found := false
		for _, role := range m.roles {
			found = found || role == ref
		}
		if !variable(ref) && !found {
			c.report(owner, fmt.Sprintf("%s participant_role_ref '%s' does not match any declared participant role", label, ref))
		}
	}
}
func (m *semanticModel) affordanceActions(c *semanticCollector, row semanticBehavior, a semanticAffordance, participants []string, label string) {
	owner := semanticOwner{behaviorSection, row.name}
	for _, ref := range a.Actions {
		if variable(ref) {
			continue
		}
		if !slices.Contains(row.actions, ref) {
			c.report(owner, fmt.Sprintf("%s action_contract_ref '%s' widens its owning behavior specification", label, ref))
		}
		for _, name := range participants {
			if !slices.Contains(fieldValue(fieldValue(m.transport.Agents)[name].Actions), ref) {
				c.report(owner, fmt.Sprintf("%s action_contract_ref '%s' is outside participant '%s' actions", label, ref, name))
			}
		}
	}
}
func (m *semanticModel) affordanceBoundaries(c *semanticCollector, row semanticBehavior, a semanticAffordance, participants []string, label string) {
	owner := semanticOwner{behaviorSection, row.name}
	for _, ref := range a.Boundaries {
		if variable(ref) {
			continue
		}
		if !slices.Contains(row.boundaries, ref) {
			c.report(owner, fmt.Sprintf("%s observation_boundary_ref '%s' widens its owning behavior specification", label, ref))
		}
		for _, name := range participants {
			if !slices.Contains(fieldValue(fieldValue(m.transport.Agents)[name].ObservationBoundaries), ref) {
				c.report(owner, fmt.Sprintf("%s observation_boundary_ref '%s' is outside participant '%s' observation boundaries", label, ref, name))
			}
		}
		if !m.affordanceClassified(row.name, a.id, ref) {
			canonical := behaviorSection + "." + row.name + "." + toolAffordancesField + "." + a.id
			c.report(owner, fmt.Sprintf("%s reference '%s' must be explicitly classified by observation boundary '%s'", label, canonical, ref))
		}
	}
}
func (m *semanticModel) affordanceClassified(name, id, ref string) bool {
	boundary, ok := fieldValue(m.transport.ObservationBoundaries)[ref]
	if !ok {
		return true
	}
	canonical := behaviorSection + "." + name + "." + toolAffordancesField + "." + id
	declared := slices.Contains(fieldValue(boundary.ObservableRefs), canonical) || slices.Contains(fieldValue(boundary.HiddenRefs), canonical) || slices.Contains(fieldValue(boundary.EvidenceRefs), canonical)
	classified := false
	for _, rule := range fieldValue(boundary.ViewRules) {
		classified = classified || fieldValue(rule.InformationRef) == canonical
	}
	return declared && classified
}
func (m *semanticModel) checkAffordanceTools(c *semanticCollector) {
	for _, row := range m.behaviors {
		for _, a := range row.affordances {
			if a.Tool == nil || variable(*a.Tool) {
				continue
			}
			m.affordanceTool(c, row.name, a)
		}
	}
}

func (m *semanticModel) affordanceTool(c *semanticCollector, name string, a semanticAffordance) {
	ref := *a.Tool
	owner := semanticOwner{behaviorSection, name}
	label := fmt.Sprintf("Behavior specification '%s' tool affordance '%s' tool_ref '%s'", name, a.id, ref)
	candidates := m.index.aliases[ref]
	switch len(candidates) {
	case 0:
		c.report(owner, label+" does not reference a declared scenario content identity")
	case 1:
		for _, candidate := range candidates {
			if candidate.kind != contentField {
				c.report(owner, label+" must resolve through the scenario-content tools-and-artifacts reference model")
			}
		}
	default:
		c.report(owner, label+" is ambiguous; use one of: "+strings.Join(slices.Sorted(maps.Keys(candidates)), ", "))
	}
}
