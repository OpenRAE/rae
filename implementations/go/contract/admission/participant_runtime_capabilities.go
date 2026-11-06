package admission

import "github.com/OpenRAE/rae/implementations/go/base/address"

func (e *Validator) runtimeCapabilities(v any) error {
	if err := participantRuntimeFeatures(v); err != nil {
		return err
	}
	for _, field := range []string{"supported_participant_roles", "supported_behavior_features", "supported_interaction_features"} {
		if !fieldsUnique(v, field) || !e.vocabularyScope("capabilities.participant_runtime."+field, at(v, field)) {
			return invalid()
		}
	}
	if err := runtimeAutonomy(v); err != nil {
		return err
	}
	if err := toolSupport(at(v, "tool_profiles"), array(at(v, "feature_support")), set(at(v, "supported_behavior_features"))); err != nil {
		return err
	}
	return require(at(v, "invocation_tool_actions") == nil || boolean(at(v, "supports_autonomous_execution")) && at(v, "tool_profiles") != nil)
}

func autonomousLimitFields() []string {
	return []string{"max_autonomous_participants", "max_autonomous_action_attempts", "max_autonomous_in_flight", "max_autonomous_occurrences", "max_autonomous_retries_per_occurrence", "max_autonomous_burst_size"}
}

func autonomousListFields() []string {
	return []string{"supported_autonomous_selection_strategies", termSupportedAutonomousActionContracts, termSupportedAutonomousObservationBoundaries, "supported_autonomous_target_addresses", "supported_autonomous_policy_profiles", "supported_autonomous_activity_features", "supported_autonomous_random_stream_profiles", "execution_bindings", "supported_execution_control_actions"}
}

func runtimeAutonomy(v any) error {
	enabled := boolean(at(v, "supports_autonomous_execution"))
	if enabled != set(at(v, "supported_behavior_features"))["autonomous_execution"] {
		return invalid()
	}
	if err := runtimeAutonomousAddresses(v); err != nil {
		return err
	}
	if !enabled {
		return runtimeDisabledAutonomy(v)
	}
	for _, field := range append(autonomousLimitFields(), "max_concurrent_actions") {
		if at(v, field) == nil {
			return invalid()
		}
	}
	for _, field := range []string{"supported_autonomous_selection_strategies", termSupportedAutonomousActionContracts, termSupportedAutonomousObservationBoundaries, "supported_autonomous_policy_profiles", "execution_bindings"} {
		if len(array(at(v, field))) == 0 {
			return invalid()
		}
	}
	profiles := set(at(v, "supported_autonomous_policy_profiles"))
	if (profiles["participant-autonomous-execution/v2"] || profiles["participant-autonomous-execution/v3"]) && (len(array(at(v, "supported_autonomous_activity_features"))) == 0 || len(array(at(v, "supported_autonomous_random_stream_profiles"))) == 0) {
		return invalid()
	}
	if profiles["participant-autonomous-execution/v3"] && at(v, "resource_budgets") == nil {
		return invalid()
	}
	return runtimeExecutionBindings(v)
}

func runtimeDisabledAutonomy(v any) error {
	for _, field := range autonomousListFields() {
		if len(array(at(v, field))) > 0 {
			return invalid()
		}
	}
	for _, field := range append(autonomousLimitFields(), "max_execution_services", "max_concurrent_actions", "resource_budgets") {
		if at(v, field) != nil {
			return invalid()
		}
	}
	return require(!boolean(at(v, "supports_execution_control")) && !boolean(at(v, "supports_bounded_concurrency")))
}

func runtimeAutonomousAddresses(v any) error {
	for _, field := range []string{termSupportedAutonomousActionContracts, termSupportedAutonomousObservationBoundaries, "supported_autonomous_target_addresses"} {
		if !fieldsUnique(v, field) {
			return invalid()
		}
		for _, declared := range stringsOf(at(v, field)) {
			if !address.Valid(declared) {
				return invalid()
			}
		}
	}
	return nil
}

func runtimeExecutionBindings(v any) error {
	control := boolean(at(v, "supports_execution_control"))
	if control != (len(array(at(v, "supported_execution_control_actions"))) > 0) || control && at(v, "max_execution_services") == nil {
		return invalid()
	}
	if boolean(at(v, "supports_bounded_concurrency")) && !numericGreater(at(v, "max_concurrent_actions"), jsonOne) {
		return invalid()
	}
	bindings := array(at(v, "execution_bindings"))
	if len(rowSet(bindings, "binding_id")) != len(bindings) {
		return invalid()
	}
	actions, targets := set(at(v, termSupportedAutonomousActionContracts)), set(at(v, "supported_autonomous_target_addresses"))
	for _, binding := range bindings {
		if !actions[stringAt(binding, "action_contract_address")] || !subset(stringsOf(at(binding, "target_addresses")), targets) || numericGreater(defaultMember(binding, "max_in_flight", jsonOne), at(v, "max_concurrent_actions")) {
			return invalid()
		}
	}
	return nil
}
