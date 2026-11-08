package authoring

import (
	"encoding/json"
	"fmt"
	"slices"
)

func mixedContains(from, until, coordinate json.Number) bool {
	return !modelLess(coordinate, from) && !modelLess(until, coordinate)
}
func mixedIntersects(from, until, otherFrom, otherUntil json.Number) bool {
	return !modelLess(until, otherFrom) && !modelLess(otherUntil, from)
}
func (s semanticMixedCheck) legacyTransition(id string, t semanticMixedTransition) {
	source, target := s.policy.States[t.Source], s.policy.States[t.Target]
	label := s.label() + " transition '" + id + "'"
	if source.Status == revokedTerm {
		s.report(label, "starts from revoked authority")
	}
	if !mixedContains(source.From, source.Until, t.Effective) {
		s.report(label, "is late for its from-state validity")
	}
	if !mixedContains(target.From, target.Until, t.Effective) {
		s.report(label, "precedes its to-state validity")
	}
	if t.Proposal != nil {
		proposal := s.policy.Transitions[*t.Proposal]
		if t.Source != proposal.Target {
			s.report(label, "must start from its proposal's resulting state")
		}
		if !modelNumberEqual(t.Expected, proposal.Resulting) {
			s.report(label, "must expect its proposal's resulting state revision")
		}
	}
	if t.Kind == handoffTerm {
		handoff := s.label() + " handoff transition '" + id + "'"
		if source.Controller == target.Controller {
			s.report(handoff, "must change controller")
		}
		if len(t.Completion) == 0 {
			s.report(handoff, "requires completion evidence")
		}
	}
	s.evidence(label, t.Evidence)
	s.evidence(label, t.Completion)
}
func (s semanticMixedCheck) permittedTransition(id string, t semanticMixedTransition) {
	source, target := s.policy.States[t.Source], s.policy.States[t.Target]
	label := s.label() + " permitted transition '" + id + "'"
	if source.Status == revokedTerm {
		s.report(label, "starts from revoked authority")
	}
	if target.Status == revokedTerm {
		s.report(label, "enters revoked authority")
	}
	if !mixedIntersects(t.From, t.Until, source.From, source.Until) {
		s.report(label, "window does not intersect its from-state validity")
	}
	if !mixedIntersects(t.From, t.Until, target.From, target.Until) {
		s.report(label, "window does not intersect its to-state validity")
	}
	changes := s.controller(source) != s.controller(target)
	if t.Kind == handoffTerm && !changes {
		s.report(label, "handoff must change controller")
	}
	if t.Kind != handoffTerm && changes {
		s.report(label, "changes controller; only a handoff changes controller identity")
	}
	s.evidence(label, t.Evidence)
	s.evidence(label, t.Completion)
}
func (t semanticMixedTransition) allowedTargets() []string {
	switch t.Kind {
	case "approval", "denial":
		return []string{proposalTerm}
	case "external-direction":
		return t.Targets
	case "intervention":
		return []string{"action", controlTerm, "attempt"}
	case "override":
		return []string{controlTerm, decisionTerm}
	case "cancellation":
		return []string{proposalTerm, decisionTerm, "admitted-action", "attempt"}
	}
	return nil
}
func (s semanticMixedCheck) script() {
	earlier := map[string]string{}
	for _, step := range s.policy.Steps {
		transition := s.policy.Permitted[step.Transition]
		label := s.label() + " script step '" + step.ID + "'"
		s.stepWindow(label, step, transition)
		allowed := transition.allowedTargets()
		if step.TargetKind != nil && !slices.Contains(allowed, *step.TargetKind) {
			s.report(label, fmt.Sprintf("target_kind '%s' widens its permitted transition", *step.TargetKind))
		}
		if step.TargetStep != nil {
			s.stepTarget(label, step, allowed, earlier)
		}
		earlier[step.ID] = transition.Kind
	}
}
func (s semanticMixedCheck) stepWindow(label string, step semanticMixedStep, t semanticMixedTransition) {
	if step.From == nil || step.Until == nil {
		return
	}
	if !mixedContains(t.From, t.Until, *step.From) || !mixedContains(*step.From, t.Until, *step.Until) {
		s.report(label, "window widens its permitted transition window")
	}
	for _, side := range []struct{ label, ref string }{{"from", t.Source}, {"to", t.Target}} {
		state := s.policy.States[side.ref]
		if !mixedIntersects(*step.From, *step.Until, state.From, state.Until) {
			s.report(label, "window does not intersect its "+side.label+"-state validity")
		}
	}
}
func (s semanticMixedCheck) stepTarget(label string, step semanticMixedStep, allowed []string, earlier map[string]string) {
	kind, known := earlier[*step.TargetStep]
	if !known {
		s.report(label, fmt.Sprintf("target_step_ref '%s' must name an earlier step", *step.TargetStep))
		return
	}
	if step.TargetKind != nil {
		allowed = []string{*step.TargetKind}
	}
	produced := []string{controlTerm}
	switch kind {
	case proposalTerm:
		produced = append(produced, proposalTerm)
	case "approval", "denial":
		produced = append(produced, decisionTerm)
	}
	count := 0
	for _, target := range produced {
		if slices.Contains(allowed, target) {
			count++
		}
	}
	if count != 1 {
		s.report(label, fmt.Sprintf("target_step_ref '%s' must produce exactly one eligible target", *step.TargetStep))
	}
}
