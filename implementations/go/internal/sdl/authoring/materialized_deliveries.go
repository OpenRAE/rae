package authoring

type injectDelivery struct {
	root          materializedChecks
	spec, binding map[string]any
	address       string
}

func (c materializedChecks) injectDeliveries() error {
	for name, raw := range object(c.value[behaviorSection]) {
		spec := object(raw)
		for id, rawBinding := range object(spec[participantInjectDeliveriesField]) {
			check := injectDelivery{root: c, spec: spec, binding: object(rawBinding), address: behaviorSection + "." + name + ".participant_inject_deliveries." + id}
			for _, pass := range []func() error{check.participant, check.occurrence, check.observation, check.registries, check.control} {
				if err := pass(); err != nil {
					return err
				}
			}
		}
	}
	return nil
}
func (d injectDelivery) participant() error {
	ref, boundary := d.binding["participant_ref"], d.binding["observation_boundary_ref"]
	if variable(ref) {
		return nil
	}
	agent := object(object(d.root.value[agentsSection])[text(ref)])
	if agent == nil || !stringSet(array(d.spec[participantRefsField]))[text(ref)] {
		return semanticInvalid()
	}
	if !variable(boundary) && (!stringSet(array(d.spec[boundaryRefsField]))[text(boundary)] || !stringSet(array(agent[boundariesSection]))[text(boundary)]) {
		return semanticInvalid()
	}
	return nil
}
func (d injectDelivery) occurrence() error {
	anchor := object(d.binding["occurrence"])
	refs := map[string]string{injectsSection: text(d.binding["inject_ref"]), eventsSection: text(anchor["event_ref"]), scriptsField: text(anchor["script_ref"]), storiesField: text(anchor["story_ref"])}
	unresolved := false
	for section, ref := range refs {
		unresolved = unresolved || variable(ref)
		if err := referencesPresent([]any{ref}, object(d.root.value[section])); err != nil {
			return err
		}
	}
	if unresolved {
		return nil
	}
	event := object(object(d.root.value[eventsSection])[refs[eventsSection]])
	script := object(object(d.root.value[scriptsField])[refs[scriptsField]])
	story := object(object(d.root.value[storiesField])[refs[storiesField]])
	if !stringSet(array(event[injectsSection]))[refs[injectsSection]] || object(script[eventsSection])[refs[eventsSection]] == nil || !stringSet(array(story[scriptsField]))[refs[scriptsField]] {
		return semanticInvalid()
	}
	return nil
}
func (d injectDelivery) overlap(left, right string) bool {
	for address := range d.root.index.aliases[left] {
		if _, present := d.root.index.aliases[right][address]; present {
			return true
		}
	}
	return false
}
func (d injectDelivery) observation() error {
	if err := d.root.index.targetReferences([]any{d.binding["source_item_ref"], d.binding["result_item_ref"]}); err != nil {
		return err
	}
	boundary := text(d.binding["observation_boundary_ref"])
	if variable(boundary) {
		return nil
	}
	value := object(object(d.root.value[boundariesSection])[boundary])
	if value == nil {
		return semanticInvalid()
	}
	if variable(d.binding["result_item_ref"]) {
		return nil
	}
	policy := object(d.binding["delivery_policy"])
	for _, raw := range array(value[viewRulesField]) {
		rule := object(raw)
		if rule["disposition"] != "observable" && rule["disposition"] != "disclosed" {
			continue
		}
		if d.overlap(text(rule[informationRefField]), text(d.binding["result_item_ref"])) && rule["visibility_basis"] == policy["visibility_basis_ref"] && rule["disclosure_rule"] == policy["disclosure_basis_ref"] {
			return nil
		}
	}
	return semanticInvalid()
}
func (d injectDelivery) registries() error {
	for field, section := range map[string]string{"temporal_constraint_refs": "temporal_constraints", evidenceRequirementRefsField: "evidence_requirements"} {
		subject := "subject_refs"
		if field == evidenceRequirementRefsField {
			subject = "source_refs"
		}
		for _, ref := range concreteRefs(array(d.binding[field])) {
			entry := object(object(d.root.value[section])[ref])
			if entry == nil {
				return semanticInvalid()
			}
			bound := false
			for _, raw := range array(entry[subject]) {
				bound = bound || d.overlap(d.address, text(raw))
			}
			if !bound {
				return semanticInvalid()
			}
		}
	}
	return nil
}
