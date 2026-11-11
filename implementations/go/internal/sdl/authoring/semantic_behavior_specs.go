package authoring

import (
	"encoding/json"
	"fmt"
)

type semanticBehavior struct {
	deliveries                                                                         []semanticDelivery
	mixed                                                                              *semanticMixed
	autonomous                                                                         *semanticAutonomous
	affordances                                                                        []semanticAffordance
	name, mode                                                                         string
	participants, roles, actions, boundaries, outcomes, authority, features, contracts []string
}

func (m *semanticModel) behaviorFacts() error {
	m.behaviorIndex = map[string]int{}
	for _, name := range m.keys(behaviorSection) {
		row, err := m.behaviorFact(name)
		if err != nil {
			return err
		}
		m.behaviorIndex[name] = len(m.behaviors)
		m.behaviors = append(m.behaviors, row)
	}
	return nil
}
func (m *semanticModel) behaviorFact(name string) (semanticBehavior, error) {
	values := fieldValue(m.transport.BehaviorSpecifications)
	raw := values[name]
	mode, err := scalarText(fieldValue(raw.BehaviorMode), "")
	if err != nil {
		return semanticBehavior{}, err
	}
	affordances, err := m.affordanceFacts(name)
	if err != nil {
		return semanticBehavior{}, err
	}
	var autonomous *semanticAutonomous
	if hasField(raw.AutonomousExecution) {
		value, loadErr := m.autonomousFacts(name)
		if loadErr != nil {
			return semanticBehavior{}, loadErr
		}
		autonomous = &value
	}
	var mixed *semanticMixed
	if hasField(raw.MixedControl) {
		var value semanticMixed
		if json.Unmarshal(fieldValue(raw.MixedControl), &value) != nil {
			return semanticBehavior{}, invalid()
		}
		mixed = &value
	}
	deliveries, err := m.deliveryFacts(name)
	if err != nil {
		return semanticBehavior{}, err
	}

	return semanticBehavior{deliveries: deliveries, mixed: mixed, autonomous: autonomous, affordances: affordances, name: name, mode: mode, participants: fieldValue(raw.ParticipantRefs), roles: fieldValue(raw.ParticipantRoleRefs), actions: fieldValue(raw.ActionContractRefs), boundaries: fieldValue(raw.ObservationBoundaryRefs), outcomes: fieldValue(raw.OutcomeInterpretationRuleRefs), authority: fieldValue(raw.AuthorityScopeRefs), features: fieldValue(raw.BackendFeatureSupportRefs), contracts: fieldValue(raw.EvidenceContractRefs)}, nil
}
func (m *semanticModel) effectiveRoles() map[string]string {
	entities := map[string]string{}
	for _, entity := range m.entities {
		if entity.role != nil {
			entities[entity.name] = *entity.role
		}
	}
	result := map[string]string{}
	for _, agent := range m.agents {
		role := agent.role
		if role == "" && len(agent.affiliations) == 1 {
			ref := agent.affiliations[0]
			if variable(ref) {
				role = ref
			} else {
				role = entities[ref]
			}
		}
		if role != "" {
			result[agent.name] = role
		}
	}
	return result
}
func (m *semanticModel) checkBehaviorSpecs(c *semanticCollector) { m.checkBehaviorSpecFields(c) }
func (m *semanticModel) checkBehaviorSpecFields(c *semanticCollector) {
	roles, unresolved := map[string]bool{}, false
	for _, role := range m.roles {
		roles[role] = true
		unresolved = unresolved || variable(role)
	}
	for _, row := range m.behaviors {
		m.behaviorSpecReferences(c, row, roles, unresolved)
		m.behaviorSpecVocabulary(c, row)
		m.behaviorAutonomous(c, row)
		m.behaviorToolAffordances(c, row)
	}
	m.checkAutonomousOwners(c)
}
func (m *semanticModel) behaviorSpecReferences(c *semanticCollector, row semanticBehavior, roles map[string]bool, unresolved bool) {
	groups := []struct {
		field   string
		refs    []string
		known   map[string]bool
		message string
		skip    bool
	}{
		{termParticipantRef, row.participants, m.definitions[agentsSection], "does not reference a declared agent", false},
		{"participant_role_ref", row.roles, roles, "does not match a declared participant role", unresolved},
		{"action_contract_ref", row.actions, m.definitions[actionsSection], "does not reference a declared action_contract", false},
		{"observation_boundary_ref", row.boundaries, m.definitions[boundariesSection], "does not reference a declared observation_boundary", false},
		{"outcome_interpretation_rule_ref", row.outcomes, m.definitions[outcomeRulesSection], "does not reference a declared outcome_interpretation_rule", false},
	}
	for _, group := range groups {
		if group.skip {
			continue
		}
		for _, ref := range group.refs {
			if !variable(ref) && !group.known[ref] {
				c.report(semanticOwner{behaviorSection, row.name}, fmt.Sprintf("Behavior specification '%s' %s '%s' %s", row.name, group.field, ref, group.message))
			}
		}
	}
}
func (m *semanticModel) behaviorSpecVocabulary(c *semanticCollector, row semanticBehavior) {
	owner, label := semanticOwner{behaviorSection, row.name}, "Behavior specification '"+row.name+"'"
	if row.mode != "" && m.parser.authority.CheckScope("behavior_specifications.behavior_mode", row.mode) != nil {
		c.report(owner, fmt.Sprintf("%s behavior_mode '%s' is not in participant-decision-surface-modes: it is neither a listed term nor an accepted extension term of that vocabulary", label, row.mode))
	}
	for _, ref := range row.features {
		if !variable(ref) && !m.parser.authority.Permits("participant-runtime-behavior-features", ref) && !m.parser.authority.Permits("participant-runtime-interaction-features", ref) {
			c.report(owner, fmt.Sprintf("%s backend_feature_support_ref '%s' is not a governed participant runtime feature: it is neither a listed term nor an accepted extension term of the participant runtime behavior or interaction feature vocabularies", label, ref))
		}
	}
	for _, ref := range row.contracts {
		if !variable(ref) && !m.parser.evidenceContracts[ref] {
			c.report(owner, fmt.Sprintf("%s evidence_contract_ref '%s' does not reference a published contract: evidence_contract_refs must reference published processor, backend, or participant contracts", label, ref))
		}
	}
}
func (m *semanticModel) checkBehaviorAuthority(c *semanticCollector) {
	for _, row := range m.behaviors {
		for _, ref := range row.authority {
			m.namedReference(c, semanticOwner{behaviorSection, row.name}, "Behavior specification '"+row.name+"'", "authority_scope_ref", ref, referenceAuthorityScope)
		}
	}
}
