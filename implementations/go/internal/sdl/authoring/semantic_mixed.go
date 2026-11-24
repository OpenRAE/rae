package authoring

import (
	"encoding/json"
	"fmt"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

const reusableMixedSemantics = "mixed-control-policy-occurrence/rev1"

type semanticMixed struct {
	Semantics   string                             `json:"semantics"`
	Participant string                             `json:"participant_ref"`
	Revision    string                             `json:"policy_revision"`
	Initial     string                             `json:"initial_state_ref"`
	States      map[string]semanticMixedState      `json:"controller_states"`
	Transitions map[string]semanticMixedTransition `json:"transitions"`
	Permitted   map[string]semanticMixedTransition `json:"permitted_transitions"`
	Steps       []semanticMixedStep                `json:"script_steps"`
}
type semanticMixedState struct {
	Controller string      `json:"controller_ref"`
	Authority  []string    `json:"authority_basis_refs"`
	Scope      []string    `json:"scope_refs"`
	Evidence   []string    `json:"evidence_refs"`
	Status     string      `json:"authority_status"`
	From       json.Number `json:"valid_from_order"`
	Until      json.Number `json:"valid_until_order"`
}
type semanticMixedTransition struct {
	Kind       string      `json:"transition_kind"`
	Source     string      `json:"from_state_ref"`
	Target     string      `json:"to_state_ref"`
	Proposal   *string     `json:"proposal_ref"`
	Expected   json.Number `json:"expected_state_revision"`
	Resulting  json.Number `json:"resulting_state_revision"`
	Effective  json.Number `json:"effective_order"`
	From       json.Number `json:"valid_from_order"`
	Until      json.Number `json:"valid_until_order"`
	Evidence   []string    `json:"evidence_refs"`
	Completion []string    `json:"completion_evidence_refs"`
	Targets    []string    `json:"target_kinds"`
}
type semanticMixedStep struct {
	ID         string       `json:"step_id"`
	Transition string       `json:"permitted_transition_ref"`
	From       *json.Number `json:"valid_from_order"`
	Until      *json.Number `json:"valid_until_order"`
	TargetKind *string      `json:"target_kind"`
	TargetStep *string      `json:"target_step_ref"`
}
type semanticMixedCheck struct {
	model     *semanticModel
	collector *semanticCollector
	row       semanticBehavior
	policy    *semanticMixed
	pointer   string
}

func (s semanticMixedCheck) label() string {
	return "Behavior specification '" + s.row.name + "' mixed_control"
}
func (s semanticMixedCheck) report(label, message string) {
	finding := s.collector.finding(semanticOwner{behaviorSection, s.row.name}, label+" "+message, termError)
	if s.pointer != "" {
		finding.Pointer = s.pointer
	}
	s.collector.errors = append(s.collector.errors, finding)
}
func (s semanticMixedCheck) reference(label, field, ref string, purpose semanticPurpose) {
	start := len(s.collector.errors)
	s.model.requireNamedReference(s.collector, semanticOwner{behaviorSection, s.row.name}, label, field, ref, purpose)
	if s.pointer != "" {
		for i := start; i < len(s.collector.errors); i++ {
			s.collector.errors[i].Pointer = s.pointer
		}
	}
}
func (m *semanticModel) checkMixedControl(c *semanticCollector) {
	for _, row := range m.behaviors {
		owner := semanticOwner{behaviorSection, row.name}
		if row.mode == "mixed-control" && row.mixed == nil {
			c.report(owner, fmt.Sprintf("Behavior specification '%s' mixed-control mode requires mixed_control", row.name))
		}
		if row.mixed == nil {
			continue
		}
		if row.mode != "mixed-control" {
			c.report(owner, fmt.Sprintf("Behavior specification '%s' mixed_control requires behavior_mode mixed-control", row.name))
		}
		check := semanticMixedCheck{model: m, collector: c, row: row, policy: row.mixed}
		check.policyChecks()
	}
}
func (s semanticMixedCheck) policyChecks() {
	label := s.label()
	if !slices.Contains(s.row.participants, s.policy.Participant) {
		s.report(label, "must bind exactly one participant_ref owned by the behavior specification")
	}
	if s.policy.Revision != fieldValue(fieldValue(s.model.transport.BehaviorSpecifications)[s.row.name].SemanticVersion) {
		s.report(label, "policy_revision must match the behavior specification semantic_version")
	}
	scope := s.model.purposeReferences(s.row.authority, referenceAuthorityScope)
	for _, id := range s.model.keys(behaviorSection, s.row.name, termMixedControl, "controller_states") {
		s.state(id, s.policy.States[id], scope)
	}
	if s.policy.States[s.policy.Initial].Status == revokedTerm {
		s.report(label, "initial state cannot use revoked authority")
	}
	if s.policy.Semantics == reusableMixedSemantics {
		for _, id := range s.model.keys(behaviorSection, s.row.name, termMixedControl, "permitted_transitions") {
			transition := s.transitionLocation("permitted_transitions", id)
			transition.permittedTransition(id, s.policy.Permitted[id])
		}
		s.script()
	} else {
		for _, id := range s.model.keys(behaviorSection, s.row.name, termMixedControl, "transitions") {
			transition := s.transitionLocation("transitions", id)
			transition.legacyTransition(id, s.policy.Transitions[id])
		}
	}
}
func (s semanticMixedCheck) transitionLocation(collection, id string) semanticMixedCheck {
	s.pointer = jsonpointer.FromTokens([]string{behaviorSection, s.row.name, termMixedControl, collection, id})
	return s
}
func (s semanticMixedCheck) controller(state semanticMixedState) string {
	return resolvedControllerReference(state.Controller, s.policy.Participant)
}
func resolvedControllerReference(controller, participant string) string {
	if controller == selfTerm {
		return participant
	}
	return controller
}
func (s semanticMixedCheck) state(id string, state semanticMixedState, ownerScope map[string]bool) {
	label := s.label() + " controller state '" + id + "'"
	name := s.controller(state)
	agent, known := fieldValue(s.model.transport.Agents)[name]
	if !known {
		s.report(label, fmt.Sprintf("controller_ref '%s' must reference a declared agent or self", state.Controller))
		return
	}
	allowed := s.model.purposeReferences(fieldValue(agent.AuthorityAnchors), referenceAuthorityAnchor)
	for _, ref := range state.Authority {
		s.reference(label, "authority_basis_ref", ref, referenceAuthorityAnchor)
		if !refsWithin(s.model.purposeReferences([]string{ref}, referenceAuthorityAnchor), allowed) {
			s.report(label, fmt.Sprintf("authority basis '%s' is not declared by controller '%s'", ref, state.Controller))
		}
	}
	s.stateScopes(label, state, ownerScope, s.model.operatingReferences(fieldValue(agent.OperatingScope)))
	s.evidence(label, state.Evidence)
}
func (s semanticMixedCheck) stateScopes(label string, state semanticMixedState, ownerScope, controllerScope map[string]bool) {
	for _, ref := range state.Scope {
		s.reference(label, "scope_ref", ref, referenceAuthorityScope)
		actual := s.model.purposeReferences([]string{ref}, referenceAuthorityScope)
		if !refsWithin(actual, ownerScope) {
			s.report(label, fmt.Sprintf("scope_ref '%s' widens the behavior specification authority scope", ref))
		}
		if !refsWithin(actual, controllerScope) {
			s.report(label, fmt.Sprintf("scope_ref '%s' is outside controller '%s' operating_scope", ref, state.Controller))
		}
	}
}
func (s semanticMixedCheck) evidence(label string, refs []string) {
	for _, ref := range refs {
		s.reference(label, "evidence_ref", ref, referenceDeclared)
	}
}
func (m *semanticModel) purposeReferences(refs []string, purpose semanticPurpose) map[string]bool {
	result := map[string]bool{}
	for _, ref := range refs {
		resolved := m.referenceResult(ref, []semanticPurpose{purpose})
		// Eligible names retain every candidate in their resolution domain.
		// Containment checks must not discard an ineligible ambiguous declaration.
		if len(resolved.eligible) == 0 {
			continue
		}
		for _, address := range resolved.domain {
			result[address] = true
		}
	}
	return result
}
func (m *semanticModel) operatingReferences(refs []string) map[string]bool {
	result := map[string]bool{}
	for _, ref := range refs {
		for address := range m.operating.aliases[ref] {
			result[address] = true
		}
	}
	return result
}
