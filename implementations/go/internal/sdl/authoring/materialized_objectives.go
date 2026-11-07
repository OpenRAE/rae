package authoring

import "github.com/OpenRAE/rae/implementations/go/internal/base/graph"

func (c materializedChecks) objectives() error {
	entities := map[string]any{}
	collectEntities(object(c.value[entitiesField]), "", entities)
	objectives := object(c.value[objectivesSection])
	dependencies := map[string][]string{}
	for name, raw := range objectives {
		objective := object(raw)
		if err := c.objectiveRelations(objective, entities); err != nil {
			return err
		}
		if err := referencesPresent(array(objective["depends_on"]), objectives); err != nil {
			return err
		}
		for _, ref := range array(objective["depends_on"]) {
			if !variable(ref) {
				dependencies[name] = append(dependencies[name], text(ref))
			}
		}
		if err := c.objectiveWindow(object(objective["window"])); err != nil {
			return err
		}
	}
	if graph.HasCycle(dependencies) {
		return semanticInvalid()
	}
	return nil
}

func (c materializedChecks) objectiveRelations(objective, entities map[string]any) error {
	for field, definitions := range map[string]map[string]any{"owner": entities, "assigned_participant": object(c.value[agentsSection])} {
		if ref := text(objective[field]); ref != "" {
			if err := referencesPresent([]any{ref}, definitions); err != nil {
				return err
			}
		}
	}
	if err := referencesPresent(array(objective["actions"]), object(c.value[actionsSection])); err != nil {
		return err
	}
	for _, ref := range concreteRefs(array(objective["targets"])) {
		target, ok := c.index.resolveTarget(ref, nil)
		if !ok || !target.objectiveSubject() {
			return semanticInvalid()
		}
	}
	participant := text(objective["assigned_participant"])
	if participant == "" || variable(participant) {
		return nil
	}
	allowed := map[string]any{}
	for _, ref := range array(object(object(c.value[agentsSection])[participant])["actions"]) {
		allowed[text(ref)] = true
	}
	return referencesPresent(array(objective["actions"]), allowed)
}

func (c materializedChecks) objectiveWindow(window map[string]any) error {
	for _, section := range []string{storiesField, scriptsField, eventsSection, "workflows"} {
		if err := referencesPresent(array(window[section]), object(c.value[section])); err != nil {
			return err
		}
	}
	reachable := map[string]bool{}
	for _, ref := range array(window[storiesField]) {
		for _, script := range array(object(object(c.value[storiesField])[text(ref)])[scriptsField]) {
			reachable[text(script)] = true
		}
	}
	if !windowSubset(array(window[scriptsField]), reachable) {
		return semanticInvalid()
	}
	selected := reachable
	if concrete := concreteRefs(array(window[scriptsField])); len(concrete) > 0 {
		selected = map[string]bool{}
		for _, script := range concrete {
			selected[script] = true
		}
	}
	events := map[string]bool{}
	for script := range selected {
		for event := range object(object(object(c.value[scriptsField])[script])[eventsSection]) {
			events[event] = true
		}
	}
	if !windowSubset(array(window[eventsSection]), events) {
		return semanticInvalid()
	}
	return c.objectiveWindowSteps(window)
}

func concreteRefs(refs []any) []string {
	result := []string{}
	for _, ref := range refs {
		if !variable(ref) {
			result = append(result, text(ref))
		}
	}
	return result
}
func windowSubset(refs []any, allowed map[string]bool) bool {
	if len(allowed) == 0 {
		return true
	}
	for _, ref := range concreteRefs(refs) {
		if !allowed[ref] {
			return false
		}
	}
	return true
}
