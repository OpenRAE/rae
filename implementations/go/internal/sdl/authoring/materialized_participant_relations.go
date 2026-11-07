package authoring

import "slices"

type participantRelation struct {
	root           materializedChecks
	detail         map[string]any
	source, target string
	refs           map[string]map[string]bool
}

func (c materializedChecks) participantRelationships() error {
	for _, raw := range object(c.value[relationshipsField]) {
		relationship := object(raw)
		if relationship["type"] != participantField {
			continue
		}
		source, err := c.participantEndpoint(relationship[sourceField])
		if err != nil {
			return err
		}
		target, err := c.participantEndpoint(relationship[targetField])
		if err != nil {
			return err
		}
		if source != "" && source == target {
			return semanticInvalid()
		}
		relation := participantRelation{root: c, detail: object(relationship[participantField]), source: source, target: target, refs: map[string]map[string]bool{}}
		if err = relation.check(); err != nil {
			return err
		}
	}
	return nil
}
func (c materializedChecks) participantEndpoint(raw any) (string, error) {
	if variable(raw) {
		return "", nil
	}
	selected, ok := c.index.resolveTarget(text(raw), []string{agentsSection})
	if !ok {
		return "", semanticInvalid()
	}
	for address, candidate := range c.index.aliases[text(raw)] {
		if candidate.value != nil && candidate.kind == selected.kind {
			return address[len(agentsSection)+1:], nil
		}
	}
	return "", semanticInvalid()
}
func (r participantRelation) check() error {
	for field, section := range map[string]string{"source_action_refs": actionsSection, "target_action_refs": actionsSection, "objective_refs": objectivesSection, "behavior_specification_refs": behaviorSection, boundaryRefsField: boundariesSection} {
		refs, err := canonicalSectionRefs(array(r.detail[field]), section, object(r.root.value[section]))
		if err != nil {
			return err
		}
		r.refs[field] = refs
	}
	if err := r.actions(); err != nil {
		return err
	}
	if err := r.behaviors(); err != nil {
		return err
	}
	if err := r.authority(); err != nil {
		return err
	}
	return r.control()
}
func canonicalSectionRefs(refs []any, section string, definitions map[string]any) (map[string]bool, error) {
	result := map[string]bool{}
	for _, ref := range concreteRefs(refs) {
		name, ok := sectionRef(ref, section, definitions)
		if !ok || result[name] {
			return nil, semanticInvalid()
		}
		result[name] = true
	}
	return result, nil
}
func (r participantRelation) agent(name string) map[string]any {
	return object(object(r.root.value[agentsSection])[name])
}
func hasVariable(refs []any) bool { return slices.ContainsFunc(refs, variable) }
func (r participantRelation) actions() error {
	for field, participant := range map[string]string{"source_action_refs": r.source, "target_action_refs": r.target} {
		if participant == "" {
			continue
		}
		available := array(r.agent(participant)["actions"])
		if !hasVariable(available) && !refsWithin(r.refs[field], stringSet(available)) {
			return semanticInvalid()
		}
	}
	if r.detail["kind"] != "coordination" {
		return nil
	}
	for action := range r.refs["source_action_refs"] {
		related := r.coordinationActions(action)
		if !hasVariable(related) && !refsWithin(r.refs["target_action_refs"], stringSet(related)) {
			return semanticInvalid()
		}
	}
	return nil
}
func (r participantRelation) coordinationActions(name string) []any {
	result := []any{}
	for _, raw := range array(object(object(r.root.value[actionsSection])[name])["interactions"]) {
		interaction := object(raw)
		if interaction["interaction_class"] != "coordination" {
			continue
		}
		peer, present := sectionRef(text(interaction[targetField]), agentsSection, object(r.root.value[agentsSection]))
		if r.target != "" && present && peer != r.target {
			continue
		}
		result = append(result, array(interaction["related_actions"])...)
	}
	return result
}
func (r participantRelation) behaviors() error {
	if r.source == "" || r.target == "" {
		return nil
	}
	roles := r.root.participantRoles()
	endpoints := map[string]bool{r.source: true, r.target: true}
	for name := range r.refs["behavior_specification_refs"] {
		spec := object(object(r.root.value[behaviorSection])[name])
		selectors := append(append([]any{}, array(spec[participantRefsField])...), array(spec[participantRoleRefsField])...)
		if hasVariable(selectors) {
			continue
		}
		selected := selectedParticipants(spec, object(r.root.value[agentsSection]), roles)
		unresolved := len(array(spec[participantRoleRefsField])) > 0 && (variable(roles[r.source]) || variable(roles[r.target]))
		if !selected[r.source] && !selected[r.target] && !unresolved {
			return semanticInvalid()
		}
	}
	for name := range r.refs["objective_refs"] {
		assignment := object(object(r.root.value[objectivesSection])[name])["assigned_participant"]
		if !variable(assignment) && !endpoints[text(assignment)] {
			return semanticInvalid()
		}
	}
	return nil
}
