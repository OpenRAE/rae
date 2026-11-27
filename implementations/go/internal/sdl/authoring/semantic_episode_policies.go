package authoring

import (
	"encoding/json"
	"fmt"
	"maps"
	"slices"
	"strings"
)

// Constraint kinds that bound elapsed shared time, so their expiry can be a timeout.
var episodeTimeoutKinds = []string{"deadline", "window", durationOperation} //nolint:gochecknoglobals // Fixed reference vocabulary.

type semanticEpisodePolicy struct {
	Initialization *struct {
		AssertionRefs []string `json:"assertion_refs"`
	} `json:"initialization"`
	InteractionStructure *struct {
		ActionContractRefs []string `json:"action_contract_refs"`
	} `json:"interaction_structure"`
	TerminalConditions   map[string]semanticEpisodeCondition `json:"terminal_conditions"`
	TruncationConditions map[string]semanticEpisodeCondition `json:"truncation_conditions"`
	ResetPolicy          *struct {
		MemoryResetAuthorityRef *string  `json:"memory_reset_authority_ref"`
		EvidenceRequirementRefs []string `json:"evidence_requirement_refs"`
	} `json:"reset_policy"`
}

type semanticEpisodeCondition struct {
	TerminalReason          string   `json:"terminal_reason"`
	AssertionRefs           []string `json:"assertion_refs"`
	TemporalConstraintRef   string   `json:"temporal_constraint_ref"`
	EvidenceRequirementRefs []string `json:"evidence_requirement_refs"`
}

type semanticEpisodeOwner struct {
	behavior     semanticBehavior
	policy       semanticEpisodePolicy
	participants []string
	resolved     bool
}

type semanticEpisodeCheck struct {
	model       *semanticModel
	collector   *semanticCollector
	assertions  map[string]struct{ Role string }
	constraints map[string]struct {
		Kind     string   `json:"constraint_kind"`
		Subjects []string `json:"subject_refs"`
	}
}

// checkEpisodePolicies requires every episode policy reference to resolve to a
// closed declaration of the right kind and role, and one policy per participant.
// It evaluates no condition and observes no episode.
func (m *semanticModel) checkEpisodePolicies(c *semanticCollector) {
	owners := m.episodeOwners()
	if len(owners) == 0 {
		return
	}
	check := semanticEpisodeCheck{model: m, collector: c}
	if !decodeTransport(fieldValue(m.transport.Assertions), &check.assertions) || !decodeTransport(fieldValue(m.transport.TemporalConstraints), &check.constraints) {
		c.report(semanticOwner{}, "Episode policy references could not be resolved")
		return
	}
	for _, owner := range owners {
		check.policy(owner)
	}
	check.onePolicyPerParticipant(owners)
}

func decodeTransport(value, target any) bool {
	raw, err := json.Marshal(value)
	return err == nil && json.Unmarshal(raw, target) == nil
}

func (m *semanticModel) episodeOwners() []semanticEpisodeOwner {
	specifications := fieldValue(m.transport.BehaviorSpecifications)
	owners := []semanticEpisodeOwner{}
	for _, row := range m.behaviors {
		raw := fieldValue(specifications[row.name].EpisodePolicy)
		if len(raw) == 0 || string(raw) == "null" {
			continue
		}
		var policy semanticEpisodePolicy
		if json.Unmarshal(raw, &policy) != nil {
			continue
		}
		unresolved := slices.ContainsFunc(row.participants, variableText)
		if len(row.roles) > 0 {
			unresolved = unresolved || slices.ContainsFunc(row.roles, variableText) || slices.ContainsFunc(slices.Collect(maps.Values(m.roles)), variableText)
		}
		owners = append(owners, semanticEpisodeOwner{behavior: row, policy: policy, participants: m.selectParticipants(row.participants, row.roles), resolved: !unresolved})
	}
	return owners
}

func variableText(value string) bool { return variable(value) }

func (e semanticEpisodeCheck) report(message string) { e.collector.report(semanticOwner{}, message) }

func (e semanticEpisodeCheck) onePolicyPerParticipant(owners []semanticEpisodeOwner) {
	governing := map[string][]string{}
	for _, owner := range owners {
		for _, participant := range owner.participants {
			governing[participant] = append(governing[participant], owner.behavior.name)
		}
	}
	for _, participant := range slices.Sorted(maps.Keys(governing)) {
		names := governing[participant]
		if len(names) < 2 {
			continue
		}
		slices.Sort(names)
		quoted := make([]string, len(names))
		for index, name := range names {
			quoted[index] = "'" + name + "'"
		}
		e.report(fmt.Sprintf("Participant '%s' is governed by more than one episode policy (behavior specifications %s)", participant, strings.Join(quoted, ", ")))
	}
}

func (e semanticEpisodeCheck) policy(owner semanticEpisodeOwner) {
	policy := owner.policy
	label := fmt.Sprintf("Behavior specification '%s' episode policy", owner.behavior.name)
	if policy.Initialization != nil {
		e.assertionRoles(label+" initialization", policy.Initialization.AssertionRefs, []string{rolePrecondition}, "a precondition")
	}
	if policy.InteractionStructure != nil {
		e.turnActions(label, owner, policy.InteractionStructure.ActionContractRefs)
	}
	for _, id := range e.model.episodeConditionOrder(owner.behavior.name, "terminal_conditions", policy.TerminalConditions) {
		condition := policy.TerminalConditions[id]
		conditionLabel := fmt.Sprintf("%s terminal condition '%s'", label, id)
		if condition.TerminalReason == "timed_out" {
			e.timeout(conditionLabel, condition.TemporalConstraintRef, owner)
		} else {
			e.closure(conditionLabel, condition.AssertionRefs)
		}
		e.evidence(conditionLabel, condition.EvidenceRequirementRefs)
	}
	for _, id := range e.model.episodeConditionOrder(owner.behavior.name, "truncation_conditions", policy.TruncationConditions) {
		condition := policy.TruncationConditions[id]
		conditionLabel := fmt.Sprintf("%s truncation condition '%s'", label, id)
		e.closure(conditionLabel, condition.AssertionRefs)
		e.evidence(conditionLabel, condition.EvidenceRequirementRefs)
	}
	if reset := policy.ResetPolicy; reset != nil {
		resetLabel := label + " reset policy"
		if reset.MemoryResetAuthorityRef != nil && !variable(*reset.MemoryResetAuthorityRef) {
			e.model.namedReference(e.collector, semanticOwner{}, resetLabel, "memory_reset_authority_ref", *reset.MemoryResetAuthorityRef, referenceTarget)
		}
		e.evidence(resetLabel, reset.EvidenceRequirementRefs)
	}
}

// episodeConditionOrder keeps the authored condition order of the reference pass.
func (m *semanticModel) episodeConditionOrder(name, field string, conditions map[string]semanticEpisodeCondition) []string {
	order := m.keys(behaviorSection, name, "episode_policy", field)
	if len(order) != len(conditions) {
		return slices.Sorted(maps.Keys(conditions))
	}
	return order
}

func (e semanticEpisodeCheck) closure(label string, refs []string) {
	e.assertionRoles(label, refs, []string{"invariant", rolePostcondition}, "an invariant or postcondition")
}

func (e semanticEpisodeCheck) assertionRoles(label string, refs, roles []string, roleLabel string) {
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		assertion, present := e.assertions[ref]
		if !present {
			e.report(fmt.Sprintf("%s assertion '%s' not in assertions section", label, ref))
		} else if !slices.Contains(roles, assertion.Role) {
			e.report(fmt.Sprintf("%s assertion '%s' must be %s", label, ref, roleLabel))
		}
	}
}

func (e semanticEpisodeCheck) turnActions(label string, owner semanticEpisodeOwner, refs []string) {
	specResolved := !slices.ContainsFunc(owner.behavior.actions, variableText)
	for _, ref := range refs {
		if variable(ref) {
			continue
		}
		refLabel := fmt.Sprintf("%s interaction_structure action_contract_ref '%s'", label, ref)
		if specResolved && !slices.Contains(owner.behavior.actions, ref) {
			e.report(refLabel + " is outside the owning behavior specification")
		}
		for _, participant := range owner.participants {
			actions := e.model.agentActions(participant)
			if !slices.Contains(actions, ref) && !slices.ContainsFunc(actions, variableText) {
				e.report(fmt.Sprintf("%s is outside participant '%s'", refLabel, participant))
			}
		}
	}
}

func (m *semanticModel) agentActions(name string) []string {
	for _, row := range m.agents {
		if row.name == name {
			return row.actions
		}
	}
	return nil
}

func (e semanticEpisodeCheck) timeout(label, ref string, owner semanticEpisodeOwner) {
	if variable(ref) {
		return
	}
	constraint, present := e.constraints[ref]
	if !present {
		e.report(fmt.Sprintf("%s temporal_constraint_ref '%s' does not reference a declared temporal constraint", label, ref))
		return
	}
	if !slices.Contains(episodeTimeoutKinds, constraint.Kind) {
		e.report(fmt.Sprintf("%s temporal_constraint_ref '%s' must be a deadline, window, or duration constraint", label, ref))
	}
	if !owner.resolved || slices.ContainsFunc(constraint.Subjects, variableText) {
		return
	}
	subjects := map[string]bool{}
	for _, subject := range constraint.Subjects {
		for address := range e.model.index.aliases[subject] {
			subjects[address] = true
		}
	}
	if !e.timeoutBindsOwner(owner, subjects) {
		e.report(fmt.Sprintf("%s temporal_constraint_ref '%s' binds neither the owning behavior specification nor every participant it selects", label, ref))
	}
}

// A timeout applies to every selected participant's episode, so its clock limit
// binds the specification itself or each of those participants.
func (e semanticEpisodeCheck) timeoutBindsOwner(owner semanticEpisodeOwner, subjects map[string]bool) bool {
	if e.resolvesInto("behavior_specifications."+owner.behavior.name, subjects) {
		return true
	}
	if len(owner.participants) == 0 {
		return false
	}
	for _, participant := range owner.participants {
		if !e.resolvesInto("agents."+participant, subjects) {
			return false
		}
	}
	return true
}

func (e semanticEpisodeCheck) resolvesInto(reference string, subjects map[string]bool) bool {
	for address := range e.model.index.aliases[reference] {
		if subjects[address] {
			return true
		}
	}
	return false
}

func (e semanticEpisodeCheck) evidence(label string, refs []string) {
	for _, ref := range refs {
		if !variable(ref) && !e.model.definitions[evidenceRequirementsSection][ref] {
			e.report(fmt.Sprintf("%s evidence_requirement_ref '%s' does not reference a declared evidence requirement", label, ref))
		}
	}
}
