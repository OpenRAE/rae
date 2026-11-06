package admission

func resourceCapabilities(v any) error {
	for _, field := range []string{"supported_owner_kinds", "supported_resource_kinds", "supported_accounting_modes", "supported_reset_modes", "supported_fairness_policies", "supported_isolation_strengths", "realization_contract_ids", "cross_range_pool_refs"} {
		seen := map[string]bool{}
		for _, value := range array(at(v, field)) {
			key, err := jsonDigest(value)
			if err != nil || seen[key] {
				return invalid()
			}
			seen[key] = true
		}
	}
	seen := map[string]bool{}
	for _, pool := range array(at(v, "configured_pools")) {
		key, err := jsonDigest([]any{at(pool, "pool_ref"), at(pool, "resource_kind"), at(pool, "meter_profile_ref")})
		if err != nil || seen[key] || !resourcePoolSupported(v, pool) {
			return invalid()
		}
		seen[key] = true
	}
	return resourceCrossRange(v)
}
func resourceCrossRange(v any) error {
	for _, ref := range stringsOf(at(v, "cross_range_pool_refs")) {
		found := false
		for _, pool := range array(at(v, "configured_pools")) {
			if stringAt(pool, "pool_ref") == ref {
				found = true
				if stringAt(pool, "tenant_isolation") != "tenant_partitioned" {
					return invalid()
				}
			}
		}
		if !found {
			return invalid()
		}
	}
	return nil
}

func resourcePoolSupported(v, pool any) bool {
	for _, pair := range [][2]string{{"owner_kind", "supported_owner_kinds"}, {"resource_kind", "supported_resource_kinds"}, {"accounting_mode", "supported_accounting_modes"}, {"fairness_policy", "supported_fairness_policies"}, {"tenant_isolation", "supported_isolation_strengths"}} {
		found := false
		for _, supported := range array(at(v, pair[1])) {
			if equal(supported, at(pool, pair[0])) {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}
