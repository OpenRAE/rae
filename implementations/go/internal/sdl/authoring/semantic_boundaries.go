package authoring

import "fmt"

func (m *semanticModel) checkRelatedActions(c *semanticCollector) {
	values := fieldValue(m.transport.ActionContracts)
	for _, name := range m.keys(actionsSection) {
		for _, interaction := range fieldValue(values[name].Interactions) {
			for _, ref := range fieldValue(interaction.RelatedActions) {
				if !variable(ref) && !m.definitions[actionsSection][ref] {
					c.report(semanticOwner{actionsSection, name}, fmt.Sprintf("Action contract '%s' interaction related_action '%s' does not reference a declared action_contract", name, ref))
				}
			}
		}
	}
}
func (m *semanticModel) checkBoundaryViews(c *semanticCollector) {
	values := fieldValue(m.transport.ObservationBoundaries)
	for _, name := range m.keys(boundariesSection) {
		boundary := values[name]
		declared, evidence := map[string]bool{}, map[string]bool{}
		for _, group := range [][]string{fieldValue(boundary.ObservableRefs), fieldValue(boundary.HiddenRefs), fieldValue(boundary.EvidenceRefs)} {
			for _, ref := range group {
				declared[ref] = true
			}
		}
		for _, ref := range fieldValue(boundary.EvidenceRefs) {
			evidence[ref] = true
		}
		owner := semanticOwner{boundariesSection, name}
		for _, row := range fieldValue(boundary.ViewRules) {
			checkBoundaryReferences(c, owner, "Observation boundary '"+name+"' view_rule", fieldValue(row.InformationRef), fieldValue(row.EvidenceRefs), declared, evidence)
		}
		for _, row := range fieldValue(boundary.ViewTransitions) {
			label := fmt.Sprintf("Observation boundary '%s' view_transition '%s'", name, fieldValue(row.TransitionId))
			checkBoundaryReferences(c, owner, label, fieldValue(row.InformationRef), fieldValue(row.EvidenceRefs), declared, evidence)
		}
	}
}
func checkBoundaryReferences(c *semanticCollector, owner semanticOwner, label, information string, refs []string, declared, evidence map[string]bool) {
	if !variable(information) && !declared[information] {
		c.report(owner, fmt.Sprintf("%s information_ref '%s' is not declared by observable_refs, hidden_refs, or evidence_refs", label, information))
	}
	for _, ref := range refs {
		if !variable(ref) && !evidence[ref] {
			c.report(owner, fmt.Sprintf("%s evidence_ref '%s' is not declared by evidence_refs", label, ref))
		}
	}
}

type semanticBoundaryRule struct{ information, disposition, visibility, disclosure string }

func (m *semanticModel) boundaryRuleFacts() error {
	m.boundaryRules = map[string][]semanticBoundaryRule{}
	for name, boundary := range fieldValue(m.transport.ObservationBoundaries) {
		for _, value := range fieldValue(boundary.ViewRules) {
			disclosure, err := scalarText(fieldValue(value.DisclosureRule), "")
			if err != nil {
				return err
			}
			m.boundaryRules[name] = append(m.boundaryRules[name], semanticBoundaryRule{fieldValue(value.InformationRef), string(fieldValue(value.Disposition)), fieldValue(value.VisibilityBasis), disclosure})
		}
	}
	return nil
}
