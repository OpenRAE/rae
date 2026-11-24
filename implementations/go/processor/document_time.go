package processor

// compiledTimeProjection is the external compiled-model view. The planner and
// published time contract continue to consume the same typed time records.
func compiledTimeProjection(model CompiledTimeModel) map[string]any {
	domains, clocks, mappings, policies, constraints := []any{}, []any{}, []any{}, []any{}, []any{}
	for _, v := range model.Domains {
		domains = append(domains, map[string]any{termAddress: v.Address, "kind": v.Kind, "tick_period_numerator": v.TickNumerator, "tick_period_denominator": v.TickDenominator, "epoch": v.Epoch, "visibility": v.Visibility, termDescription: v.Description})
	}
	for _, v := range model.Clocks {
		clocks = append(clocks, map[string]any{termAddress: v.Address, "time_domain_address": v.TimeDomainAddress, "authority_kind": v.AuthorityKind, "authority_ref": v.AuthorityRef, "monotonicity": v.Monotonicity, "supports_pause": v.SupportsPause, "supports_reset": v.SupportsReset, "supports_jump": v.SupportsJump, termDescription: v.Description})
	}
	for _, v := range model.Mappings {
		mappings = append(mappings, map[string]any{termAddress: v.Address, "source_domain_address": v.SourceDomainAddress, "target_domain_address": v.TargetDomainAddress, "mapping_kind": v.Kind, "scale_numerator": v.ScaleNumerator, "scale_denominator": v.ScaleDenominator, "offset_ticks": v.OffsetTicks, termDescription: v.Description})
	}
	for _, v := range model.ProgressionPolicies {
		policies = append(policies, map[string]any{termAddress: v.Address, "clock_address": v.ClockAddress, "advancement_mode": v.AdvancementMode, "pacing_numerator": v.PacingNumerator, "pacing_denominator": v.PacingDenominator, "synchronization_mode": v.SynchronizationMode, "step_ticks": v.StepTicks, "drift_bound_ticks": v.DriftBoundTicks, "reset_behavior": v.ResetBehavior, "replay_behavior": v.ReplayBehavior, termDescription: v.Description})
	}
	for _, v := range model.Constraints {
		constraints = append(constraints, map[string]any{termAddress: v.Address, "kind": v.Kind, "clock_address": v.ClockAddress, "subject_addresses": nonNilStrings(v.SubjectAddresses), "start_tick": v.StartTick, "start_microstep": v.StartMicrostep, "end_tick": v.EndTick, "end_microstep": v.EndMicrostep, "duration_ticks": v.DurationTicks, "cadence_ticks": v.CadenceTicks, termDescription: v.Description})
	}
	return map[string]any{"domains": domains, "clocks": clocks, "mappings": mappings, "progression_policies": policies, "constraints": constraints}
}
func compiledCapabilityProjection(constraints []CapabilityConstraint) []any {
	result := make([]any, len(constraints))
	for i, v := range constraints {
		result[i] = map[string]any{termAddress: v.Address, "concern": v.Concern, "parameter": v.Parameter, "allowed_values": v.AllowedValues}
	}
	return result
}
