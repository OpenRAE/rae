package authoring

import (
	"maps"
	"slices"
)

func (d semanticDeliveryCheck) control() {
	b := d.binding
	if b.Kind == "disclosure" {
		return
	}
	authority, evidence := b.Authority, b.Evidence
	if b.Control != nil {
		authority, evidence = b.Control.Authority, b.Control.Evidence
	}
	for _, ref := range authority {
		d.reference("control authority scope", ref, referenceAuthorityScope)
	}
	for _, ref := range evidence {
		d.reference("control evidence", ref, referenceTarget)
	}
	reusable := d.row.mixed != nil && d.row.mixed.Semantics == reusableMixedSemantics
	if b.Control != nil || reusable {
		d.reusableControl(reusable)
		return
	}
	d.legacyControl()
}
func (d semanticDeliveryCheck) reusableControl(reusable bool) {
	control, policy := d.binding.Control, d.row.mixed
	if control == nil {
		d.reportf("flat control fields cannot bind a mixed-control-policy-occurrence/rev1 policy")
		return
	}
	if !reusable {
		d.reportf("control block requires a mixed-control-policy-occurrence/rev1 mixed_control policy")
		return
	}
	if control.Semantics != policy.Semantics || control.Revision != policy.Revision {
		d.reportf("control policy pin disagrees with the owning mixed_control policy")
	}
	if policy.Participant != d.binding.Participant {
		d.reportf("control transition participant disagrees with participant_ref")
	}
	transition, known := policy.Permitted[control.Transition]
	if !known {
		d.reportf("control permitted_transition_ref '%s' does not resolve", control.Transition)
		return
	}
	if transition.Kind != d.binding.Kind {
		d.reportf("control permitted_transition_ref '%s' kind '%s' does not match delivery_kind '%s'", control.Transition, transition.Kind, d.binding.Kind)
	}
	state := policy.States[transition.Source]
	expected := resolvedControllerReference(state.Controller, policy.Participant)
	actual := resolvedControllerReference(control.Controller, d.binding.Participant)
	if actual != expected {
		d.reportf("control controller_ref must be the permitted transition's source-state controller")
	}
	bound := d.model.purposeReferences(control.Authority, referenceAuthorityScope)
	allowed := d.model.purposeReferences(state.Scope, referenceAuthorityScope)
	if len(bound) == 0 || !refsWithin(bound, allowed) {
		d.reportf("control authority scope widens the source-state scope")
	}
	d.reusableEvidence(transition, state)
}
func (d semanticDeliveryCheck) reusableEvidence(t semanticMixedTransition, state semanticMixedState) {
	bound := d.model.purposeReferences(d.binding.Control.Evidence, referenceTarget)
	permitted := d.model.purposeReferences(append(slices.Clone(t.Evidence), state.Evidence...), referenceDeclared)
	if len(bound) == 0 || !refsWithin(bound, permitted) {
		d.reportf("control evidence lies outside the permitted transition and source-state evidence")
	}
	if !refsWithin(bound, d.requiredEvidenceScope()) {
		d.reportf("evidence requirement does not cover the control evidence basis")
	}
}
func (d semanticDeliveryCheck) requiredEvidenceScope() map[string]bool {
	result := map[string]bool{}
	for _, ref := range d.binding.Requirements {
		requirement := fieldValue(d.model.transport.EvidenceRequirements)[ref]
		maps.Copy(result, d.model.purposeReferences(fieldValue(requirement.ScopeRefs), referenceDeclared))
	}
	return result
}
func (d semanticDeliveryCheck) legacyControl() {
	policy := d.row.mixed
	if policy == nil {
		d.reportf("control_transition_ref requires mixed_control on the owning behavior specification")
		return
	}
	ref := "None"
	if d.binding.Transition != nil {
		ref = *d.binding.Transition
	}
	transition, known := policy.Transitions[ref]
	if !known {
		d.reportf("control_transition_ref '%s' does not resolve", ref)
		return
	}
	state := policy.States[transition.Target]
	d.legacyIdentity(ref, transition, state)
	d.legacyBounds(transition, state)
	d.controlTime()
	d.legacyEvidence(transition, state)
}
func (d semanticDeliveryCheck) legacyIdentity(ref string, t semanticMixedTransition, state semanticMixedState) {
	b, policy := d.binding, d.row.mixed
	if t.Kind != b.Kind {
		d.reportf("control_transition_ref '%s' kind '%s' does not match delivery_kind '%s'", ref, t.Kind, b.Kind)
	}
	if policy.Participant != b.Participant {
		d.reportf("control transition participant disagrees with participant_ref")
	}
	if policy.Revision != b.Policy.Revision {
		d.reportf("control transition policy revision disagrees with delivery policy")
	}
	if resolvedControllerReference(b.Controller, b.Participant) != resolvedControllerReference(state.Controller, policy.Participant) {
		d.reportf("controller_ref disagrees with the control transition target state")
	}
	if !maps.Equal(d.model.purposeReferences(b.Authority, referenceAuthorityScope), d.model.purposeReferences(state.Scope, referenceAuthorityScope)) {
		d.reportf("control authority scope disagrees with the control transition target state")
	}
}
func (d semanticDeliveryCheck) legacyBounds(t semanticMixedTransition, state semanticMixedState) {
	b := d.binding
	if !modelNumberEqual(b.Effective, t.Effective) {
		d.reportf("control effective order disagrees with the control transition")
	}
	if !modelNumberEqual(b.From, t.From) || !modelNumberEqual(b.Until, t.Until) {
		d.reportf("control validity interval disagrees with the control transition")
	}
	if !mixedContains(state.From, state.Until, b.Effective) {
		d.reportf("control effective order falls outside the target controller-state validity interval")
	}
}
func (d semanticDeliveryCheck) legacyEvidence(t semanticMixedTransition, state semanticMixedState) {
	bound := d.model.purposeReferences(d.binding.Evidence, referenceTarget)
	if !maps.Equal(bound, d.model.purposeReferences(t.Evidence, referenceDeclared)) || !maps.Equal(bound, d.model.purposeReferences(state.Evidence, referenceDeclared)) {
		d.reportf("control evidence basis disagrees with the transition or target state")
	}
	if len(bound) == 0 || !refsWithin(bound, d.requiredEvidenceScope()) {
		d.reportf("evidence requirement does not cover the control evidence basis")
	}
}
func (d semanticDeliveryCheck) controlTime() {
	current := semanticCoordinate{Tick: d.binding.Effective, Microstep: "0"}
	bounded := false
	for _, ref := range d.binding.Constraints {
		interval := d.model.timeCoordinates[ref]
		if interval.start != nil {
			bounded = true
			if current.before(*interval.start) {
				d.reportf("temporal constraint excludes the control effective order")
			}
		}
		if interval.end != nil {
			bounded = true
			if interval.end.before(current) {
				d.reportf("temporal constraint excludes the control effective order")
			}
		}
	}
	if !bounded {
		d.reportf("directed control requires a bounded temporal constraint")
	}
}
