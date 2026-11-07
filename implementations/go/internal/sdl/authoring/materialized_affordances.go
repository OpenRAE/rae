package authoring

import (
	"encoding/json"
	"slices"
)

func (c materializedChecks) toolAffordances(name string, spec map[string]any, roles map[string]string) error {
	participants := selectedParticipants(spec, object(c.value[agentsSection]), roles)
	seen := map[string]bool{}
	for id, raw := range object(spec[toolAffordancesField]) {
		binding := object(raw)
		signature, err := affordanceSignature(binding)
		if err != nil {
			return err
		}
		if seen[signature] {
			return semanticInvalid()
		}
		seen[signature] = true
		selected, err := c.affordanceParticipants(spec, binding, participants, roles)
		if err != nil {
			return err
		}
		if err = c.affordanceReferences(name, id, spec, binding, selected); err != nil {
			return err
		}
	}
	return nil
}
func affordanceSignature(binding map[string]any) (string, error) {
	actions, boundaries := concreteAllRefs(array(binding[actionRefsField])), concreteAllRefs(array(binding[boundaryRefsField]))
	slices.Sort(actions)
	slices.Sort(boundaries)
	encoded, err := json.Marshal(struct {
		Tool       string   `json:"tool"`
		Actions    []string `json:"actions"`
		Boundaries []string `json:"boundaries"`
	}{text(binding[toolRefField]), actions, boundaries})
	if err != nil {
		return "", semanticInvalid()
	}
	return string(encoded), nil
}
func concreteAllRefs(refs []any) []string {
	result := make([]string, 0, len(refs))
	for _, ref := range refs {
		result = append(result, text(ref))
	}
	return result
}
func (c materializedChecks) affordanceParticipants(spec, binding map[string]any, parent map[string]bool, roles map[string]string) (map[string]bool, error) {
	if len(array(binding[participantRefsField])) == 0 && len(array(binding[participantRoleRefsField])) == 0 {
		return parent, nil
	}
	if err := referencesPresent(array(binding[participantRefsField]), object(c.value[agentsSection])); err != nil {
		return nil, err
	}
	if err := behaviorRoleRefs(array(binding[participantRoleRefsField]), roles, false); err != nil {
		return nil, err
	}
	selected := selectedParticipants(binding, object(c.value[agentsSection]), roles)
	selectors := append([]any{}, array(spec[participantRefsField])...)
	selectors = append(selectors, array(spec[participantRoleRefsField])...)
	if slices.ContainsFunc(selectors, variable) {
		return selected, nil
	}
	for name := range selected {
		if !parent[name] {
			return nil, semanticInvalid()
		}
	}
	return selected, nil
}
func (c materializedChecks) affordanceReferences(name, id string, spec, binding map[string]any, participants map[string]bool) error {
	if err := c.affordanceTool(binding); err != nil {
		return err
	}
	for field, agentField := range map[string]string{actionRefsField: "actions", boundaryRefsField: boundariesSection} {
		parent := stringSet(array(spec[field]))
		for _, ref := range concreteRefs(array(binding[field])) {
			if !parent[ref] {
				return semanticInvalid()
			}
			if !c.participantsPermit(participants, agentField, ref) {
				return semanticInvalid()
			}
			if field == boundaryRefsField && !c.affordanceClassified(name, id, ref) {
				return semanticInvalid()
			}
		}
	}
	return nil
}
func (c materializedChecks) participantsPermit(participants map[string]bool, field, ref string) bool {
	for name := range participants {
		if !stringSet(array(object(object(c.value[agentsSection])[name])[field]))[ref] {
			return false
		}
	}
	return true
}
func (c materializedChecks) affordanceClassified(name, id, ref string) bool {
	boundary := object(object(c.value[boundariesSection])[ref])
	if boundary == nil {
		return true
	}
	canonical := "behavior_specifications." + name + ".tool_affordances." + id
	declared := false
	for _, field := range []string{observableRefsField, hiddenRefsField, evidenceRefsField} {
		declared = declared || stringSet(array(boundary[field]))[canonical]
	}
	classified := false
	for _, raw := range array(boundary[viewRulesField]) {
		classified = classified || text(object(raw)[informationRefField]) == canonical
	}
	return declared && classified
}

func (c materializedChecks) affordanceTool(binding map[string]any) error {
	if ref := text(binding[toolRefField]); ref != "" && !variable(ref) {
		candidates := c.index.aliases[ref]
		if len(candidates) != 1 {
			return semanticInvalid()
		}
		for _, candidate := range candidates {
			if candidate.kind != contentField {
				return semanticInvalid()
			}
		}
	}

	return nil
}
