package admission

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
)

func controlDigest(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", invalid()
	}
	copyValue, err := ingress.Parse(raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64}, ingress.Object)
	if err != nil {
		return "", invalid()
	}
	controlSerialization(copyValue)
	return jsonDigest(copyValue)
}

func controlSerialization(v any) {
	switch node := v.(type) {
	case []any:
		for _, child := range node {
			controlSerialization(child)
		}
	case map[string]any:
		for _, child := range node {
			controlSerialization(child)
		}
		if stringAt(node, termKind) == termInject && node["world_request"] == nil {
			delete(node, "world_request")
		}
		if _, present := node["obligation_id"]; present && len(array(node["admitted_support"])) == 0 {
			delete(node, "admitted_support")
		}
	}
}

func controlRequest(v any, v2 bool) error {
	selection, context := at(v, "selection"), at(v, "context")
	if !equal(at(selection, termApparatus), at(context, termApparatus)) {
		return invalid()
	}
	for field, bound := range map[string]string{"depth": "max_depth", "effects_consumed": "max_effects", termAttempt: "max_attempts", termOrder: "expires_at_order"} {
		if numericGreater(at(context, field), at(selection, "bounds", bound)) {
			return invalid()
		}
	}
	instances := rowSet(at(selection, termBindings), "instance_id")
	if v2 {
		var err error
		instances, err = controlApplicableInstances(v)
		if err != nil {
			return err
		}
	}
	if !equalSet(rowSet(at(context, "provider_states"), "instance_id"), instances) {
		return invalid()
	}
	for _, binding := range array(at(selection, termBindings)) {
		if !instances[stringAt(binding, "instance_id")] {
			continue
		}
		if !equal(at(binding, "memory_scope"), at(context, "memory_scope")) || !controlBindingApplies(binding, context) {
			return invalid()
		}
	}
	return nil
}

func controlBindingApplies(binding, context any) bool {
	for _, applicability := range array(at(binding, "applicability")) {
		if matchingFields(applicability, context, "participant_address", "episode_id", "direction", "sink_ref", "phase_ref") && equal(at(applicability, "subject_kind"), at(context, "subject", "subject_kind")) {
			return true
		}
	}
	return false
}

func controlApplicabilityDigests(v any) error {
	selection, err := controlDigest(at(v, "selection"))
	if err != nil {
		return err
	}
	context, err := controlDigest(at(v, "context"))
	if err != nil {
		return err
	}
	return require(stringAt(v, "applicability", "selection_digest") == selection && stringAt(v, "applicability", "context_digest") == context)
}

func controlRequestCoverage(v any) error {
	selection := at(v, "selection")
	obligations, slots, bindings := map[string]any{}, map[string]any{}, map[string]any{}
	for _, obligation := range array(at(selection, "obligations")) {
		obligations[stringAt(obligation, "obligation_id")] = obligation
	}
	for _, slot := range array(at(selection, "slots")) {
		slots[stringAt(slot, "slot_id")] = slot
	}
	for _, binding := range array(at(selection, termBindings)) {
		bindings[stringAt(binding, "instance_id")] = binding
	}
	coverage := array(at(v, "applicability", "coverage"))
	if len(rowSet(coverage, "obligation_id")) != len(coverage) || !equalSet(rowSet(coverage, "obligation_id"), keySet(obligations)) {
		return invalid()
	}
	for _, item := range coverage {
		if err := controlCoverageItem(item); err != nil {
			return err
		}
		if stringAt(item, "status") != termApplies {
			continue
		}
		if err := controlAppliedCoverage(v, item, obligations[stringAt(item, "obligation_id")], slots, bindings); err != nil {
			return err
		}
	}
	return nil
}

func controlCoverageItem(v any) error {
	if !fieldsUnique(v, "slot_ids") {
		return invalid()
	}
	if stringAt(v, "status") == termApplies {
		return require(len(array(at(v, "slot_ids"))) > 0)
	}
	return require(len(array(at(v, "slot_ids"))) == 0)
}

func controlAppliedCoverage(v, item, obligation any, slots, bindings map[string]any) error {
	for _, identity := range stringsOf(at(item, "slot_ids")) {
		slot := slots[identity]
		if !set(at(v, "applicability", "applicable_slot_ids"))[identity] || !equal(at(slot, termKind), at(obligation, "required_kind")) {
			return invalid()
		}
		binding := bindings[stringAt(slot, "instance_id")]
		found := false
		for _, profile := range array(at(binding, "profiles")) {
			found = found || equal(profile, at(obligation, "profile"))
		}
		if !found || len(array(at(obligation, "admitted_support"))) > 0 && !rowSet(at(obligation, "admitted_support"), "instance_id")[stringAt(slot, "instance_id")] {
			return invalid()
		}
	}
	return nil
}

func controlRequiredClosure(v any) error {
	applicable, required := set(at(v, "applicability", "applicable_slot_ids")), set(at(v, "applicability", "required_slot_ids"))
	if !fieldsUnique(at(v, "applicability"), "applicable_slot_ids", "required_slot_ids") || !subsetSet(applicable, rowSet(at(v, "selection", "slots"), "slot_id")) || !subsetSet(required, applicable) {
		return invalid()
	}
	root, dependencies := controlCoverageRoots(v), map[string]map[string]bool{}
	for _, slot := range array(at(v, "selection", "slots")) {
		id := stringAt(slot, "slot_id")
		dependencies[id] = rowSet(at(slot, "dependencies"), "slot_id")
		if applicable[id] && !subsetSet(dependencies[id], applicable) {
			return invalid()
		}
		if applicable[id] && stringAt(slot, "role") == "mandatory" {
			root[id] = true
		}
	}
	controlDependencyClosure(root, dependencies)
	return require(equalSet(root, required))
}

func controlApplicableInstances(v any) (map[string]bool, error) {
	selection := at(v, "selection")
	if err := controlRequestCoverage(v); err != nil {
		return nil, err
	}
	if err := controlRequiredClosure(v); err != nil {
		return nil, err
	}
	instances := map[string]bool{}
	for _, slot := range array(at(selection, "slots")) {
		if set(at(v, "applicability", "applicable_slot_ids"))[stringAt(slot, "slot_id")] {
			instances[stringAt(slot, "instance_id")] = true
		}
	}
	if err := controlApplicabilityDigests(v); err != nil {
		return nil, err
	}
	return instances, nil
}

func controlCoverageRoots(v any) map[string]bool {
	root := map[string]bool{}
	for _, item := range array(at(v, "applicability", "coverage")) {
		if stringAt(item, "status") == termApplies {
			for _, id := range stringsOf(at(item, "slot_ids")) {
				root[id] = true
			}
		}
	}
	return root
}

func controlDependencyClosure(root map[string]bool, dependencies map[string]map[string]bool) {
	pending := make([]string, 0, len(root))
	for id := range root {
		pending = append(pending, id)
	}
	for len(pending) > 0 {
		id := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		for dependency := range dependencies[id] {
			if !root[dependency] {
				root[dependency] = true
				pending = append(pending, dependency)
			}
		}
	}
}
