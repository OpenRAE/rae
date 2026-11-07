package admission

import (
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func (e *Validator) controlSelection(i validation.Invocation) error {
	v := i.Instance
	if stringAt(v, termApparatus, termKind) != termApparatus || !fieldsUnique(v, "required_profiles") {
		return invalid()
	}
	bindings, slots := array(at(v, termBindings)), array(at(v, "slots"))
	if len(rowSet(bindings, "instance_id")) != len(bindings) || len(rowSet(slots, "slot_id")) != len(slots) {
		return invalid()
	}
	profiles := map[string]bool{}
	for _, binding := range bindings {
		if err := e.controlBinding(binding); err != nil {
			return err
		}
		for _, profile := range array(at(binding, "profiles")) {
			profiles[stringAt(profile, "ref")] = true
		}
	}
	if !subset(stringsOf(at(v, "required_profiles")), profiles) {
		return invalid()
	}
	if err := controlSlotGraph(slots, rowSet(bindings, "instance_id")); err != nil {
		return err
	}
	if stringAt(v, termSchemaVersion) == "participant-control-selection/v2" {
		return controlObligations(v)
	}
	return nil
}
func (e *Validator) controlBinding(v any) error {
	for field, kind := range map[string]string{"mechanism": "mechanism", termImplementation: termImplementation, termAuthority: termAuthority, "memory_scope": "memory"} {
		if stringAt(v, field, termKind) != kind {
			return invalid()
		}
	}
	for field, kind := range map[string]string{"profiles": termProfile, termEvidence: termEvidence, "limitations": "limitation"} {
		if err := controlBindingReferences(v, field, kind); err != nil {
			return err
		}
	}
	if !uniqueValues(at(v, "applicability")) || len(rowSet(at(v, "profiles"), "ref")) != len(array(at(v, "profiles"))) {
		return invalid()
	}
	for _, profile := range array(at(v, "profiles")) {
		if err := e.controlBindingProfile(v, profile); err != nil {
			return err
		}
	}
	if at(v, "state_scope") != nil {
		if !equal(at(v, "state_scope", termAuthority), at(v, termAuthority)) || stringAt(v, "state_scope", termAuthority, termKind) != termAuthority || !equal(at(v, "state_scope", "configuration_digest"), at(v, "configuration_digest")) {
			return invalid()
		}
	}
	return nil
}
func controlSlotGraph(slots []any, instances map[string]bool) error {
	byID := map[string]any{}
	for _, slot := range slots {
		byID[stringAt(slot, "slot_id")] = slot
	}
	edges := map[string][]string{}
	for _, slot := range slots {
		if err := controlSlotEdges(slot, instances, byID, edges); err != nil {
			return err
		}
	}
	return require(!graph.HasCycle(edges))
}
func controlStrengthPin(v any) error {
	for _, constraint := range array(at(v, termConstraints)) {
		if stringAt(constraint, termKind) != termConstraint {
			return invalid()
		}
	}
	return require(stringAt(v, "required_strength") != assuranceBounded || len(array(at(v, termConstraints))) > 0)
}
func controlObligations(v any) error {
	obligations := array(at(v, "obligations"))
	if len(rowSet(obligations, "obligation_id")) != len(obligations) {
		return invalid()
	}
	selected := map[string]any{}
	for _, binding := range array(at(v, termBindings)) {
		if err := controlSelectedProfiles(binding, selected); err != nil {
			return err
		}
	}
	declared := map[string]bool{}
	for _, obligation := range obligations {
		if err := controlObligation(obligation, selected, declared); err != nil {
			return err
		}
	}
	for key, profile := range selected {
		if set(at(v, "required_profiles"))[stringAt(profile, "ref")] && !declared[key] {
			return invalid()
		}
	}
	return ownerFlowObligations(v)
}
func controlSupportPromises(v any) error {
	rows := array(at(v, "admitted_support"))
	if len(rowSet(rows, "instance_id")) != len(rows) {
		return invalid()
	}
	for _, support := range rows {
		if err := controlEffectiveSupport(support); err != nil {
			return err
		}
		if stringAt(support, "status") != termResolved || stringAt(support, "effective_level") == statusUnsupported {
			return invalid()
		}
	}
	return nil
}

func controlBindingReferences(v any, field, kind string) error {
	if !uniqueValues(at(v, field)) {
		return invalid()
	}
	for _, ref := range array(at(v, field)) {
		if stringAt(ref, termKind) != kind {
			return invalid()
		}
	}

	return nil
}

func controlSelectedProfiles(binding any, selected map[string]any) error {
	for _, profile := range array(at(binding, "profiles")) {
		key, err := jsonDigest(profile)
		if err != nil {
			return err
		}
		selected[key] = profile
	}

	return nil
}

func controlSlotEdges(slot any, instances map[string]bool, byID map[string]any, edges map[string][]string) error {
	if !instances[stringAt(slot, "instance_id")] || len(rowSet(at(slot, "dependencies"), "slot_id")) != len(array(at(slot, "dependencies"))) {
		return invalid()
	}
	id := stringAt(slot, "slot_id")
	edges[id] = nil
	for _, dependency := range array(at(slot, "dependencies")) {
		parent := byID[stringAt(dependency, "slot_id")]
		if parent == nil || !equal(at(parent, termKind), at(dependency, termKind)) {
			return invalid()
		}
		edges[id] = append(edges[id], stringAt(dependency, "slot_id"))
	}
	if at(slot, "required_strength") != nil {
		if err := controlStrengthPin(slot); err != nil {
			return err
		}
	}

	return nil
}

func (e *Validator) controlBindingProfile(v, profile any) error {
	if err := e.controlProfile(profile); err != nil {
		return err
	}
	if stringAt(profile, "ref") == termParticipantOwnerFlowPolicyV1 && stringAt(v, "protocol_revision") != "participant-control-provider/v2" {
		return invalid()
	}

	return nil
}

func controlObligation(obligation any, selected map[string]any, declared map[string]bool) error {
	key, err := jsonDigest(at(obligation, termProfile))
	if err != nil {
		return err
	}
	if selected[key] == nil || stringAt(obligation, termProfile, termKind) != termProfile {
		return invalid()
	}
	declared[key] = true
	if err := controlStrengthPin(obligation); err != nil {
		return err
	}
	if err := controlSupportPromises(obligation); err != nil {
		return err
	}

	return nil
}
