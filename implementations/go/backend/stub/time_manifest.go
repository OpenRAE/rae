package stub

func timeCapabilities(coordinated bool) map[string]any {
	return map[string]any{
		"name":                            "stub-time-runtime",
		"supported_contract_versions":     []string{"time-model-v1", "time-runtime-state-v1", "realized-time-model-v1", "runtime-snapshot-v1", "experiment-run-v1"},
		"supported_domain_kinds":          []string{"wall_clock", "monotonic", "simulated", "logical", "external"},
		"supported_authority_kinds":       []string{termRuntime, "backend", "system", "external"},
		"supported_advancement_modes":     []string{"real_time", "dilated", "stepped", "event_driven", "externally_paced"},
		"supported_synchronization_modes": []string{"none", "authority", "barrier", "conservative"},
		"supported_mapping_kinds":         []string{"identity", "affine_rational"},
		"supported_constraint_kinds":      []string{"precedence", "duration", "window", "deadline", "cadence"},
		"supported_reset_behaviors":       []string{"unsupported", "new_segment_zero", "new_segment_preserve_value"},
		"supported_replay_behaviors":      []string{"unsupported", "restart_from_anchor", "restore_recorded_advances"},
		"supports_pause":                  true, "supports_jump": true, "supports_exact_rational_mappings": true, "supports_append_only_history": true, "supports_run_provenance": true, "supports_coordinated_participant_reset": coordinated,
	}
}
