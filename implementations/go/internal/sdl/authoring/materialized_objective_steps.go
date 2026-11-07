package authoring

import "strings"

func (c materializedChecks) objectiveWindowSteps(window map[string]any) error {
	steps, workflows := concreteRefs(array(window["steps"])), concreteRefs(array(window["workflows"]))
	if len(steps) > 0 && len(workflows) == 0 {
		return semanticInvalid()
	}
	allowed := map[string]bool{}
	for _, workflow := range workflows {
		allowed[workflow] = true
	}
	for _, ref := range steps {
		split := strings.LastIndexByte(ref, '.')
		if split <= 0 || split == len(ref)-1 {
			return semanticInvalid()
		}
		workflow, step := ref[:split], ref[split+1:]
		if len(allowed) > 0 && !allowed[workflow] {
			return semanticInvalid()
		}
		value := object(object(c.value["workflows"])[workflow])
		if value == nil || object(value["steps"])[step] == nil {
			return semanticInvalid()
		}
	}
	return nil
}
