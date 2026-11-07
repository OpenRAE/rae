package authoring

func (r participantRelation) authority() error {
	scopes := operatingScopeIndex(r.root.value)
	for field, index := range map[string]*declarationIndex{"authority_basis_refs": r.root.index, scopeRefsField: scopes} {
		purpose := "declared"
		if field == scopeRefsField {
			purpose = "target"
		}
		selected, err := uniqueNamedRefs(array(r.detail[field]), index, purpose)
		if err != nil {
			return err
		}
		if err = r.refinementScope(field, selected, index, purpose); err != nil {
			return err
		}
	}
	if r.source != "" {
		available := array(r.agent(r.source)[boundariesSection])
		if !hasVariable(available) && !refsWithin(r.refs[boundaryRefsField], stringSet(available)) {
			return semanticInvalid()
		}
	}
	return nil
}
func uniqueNamedRefs(refs []any, index *declarationIndex, purpose string) (map[string]bool, error) {
	result := map[string]bool{}
	for _, ref := range concreteRefs(refs) {
		resolved, err := index.canonicalRefs([]any{ref}, purpose)
		if err != nil {
			return nil, err
		}
		for address := range resolved {
			if result[address] {
				return nil, semanticInvalid()
			}
			result[address] = true
		}
	}
	return result, nil
}
func (r participantRelation) refinementScope(field string, selected map[string]bool, index *declarationIndex, purpose string) error {
	endpoints, agentField := []string{r.source}, "authority_anchors"
	if field == scopeRefsField {
		endpoints = append(endpoints, r.target)
		agentField = "operating_scope"
	}
	for _, name := range endpoints {
		if name == "" {
			continue
		}
		allowed := array(r.agent(name)[agentField])
		if hasVariable(allowed) {
			continue
		}
		resolved, err := index.canonicalRefs(allowed, purpose)
		if err != nil {
			return err
		}
		if !refsWithin(selected, resolved) {
			return semanticInvalid()
		}
	}
	return nil
}
func (r participantRelation) control() error {
	ref := text(r.detail["control_specification_ref"])
	if ref == "" || variable(ref) {
		return nil
	}
	registry := object(r.root.value[behaviorSection])
	name, ok := sectionRef(ref, behaviorSection, registry)
	policy := object(object(registry[name])["mixed_control"])
	if !ok || policy == nil {
		return semanticInvalid()
	}
	if r.source == "" || r.target == "" {
		return nil
	}
	controlled, controller := r.target, r.source
	if r.detail["kind"] == "delegation" {
		controlled, controller = r.source, r.target
	}
	if text(policy["participant_ref"]) != controlled {
		return semanticInvalid()
	}
	states := []map[string]any{}
	allowed := []any{}
	for _, raw := range object(policy["controller_states"]) {
		state := object(raw)
		if text(state["controller_ref"]) == controller && state["authority_status"] == "active" {
			states = append(states, state)
			allowed = append(allowed, array(state[scopeRefsField])...)
		}
	}
	if len(states) == 0 {
		return semanticInvalid()
	}
	scopes := operatingScopeIndex(r.root.value)
	return r.root.controlRefsWithin(array(r.detail[scopeRefsField]), allowed, scopes, "target")
}
