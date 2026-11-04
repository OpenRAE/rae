package admission

func (r *materializationInventory) processLimits(requirement any) error {
	for _, declaration := range array(at(r.execution.manifest, "realization_support")) {
		if !equal(at(requirement, "domain"), at(declaration, "domain")) || !set(at(declaration, "supported_exact_requirement_kinds"))["declared-capability-match"] || !materializationObservation(requirement, at(declaration, "observation_capabilities", "process-resource-limits")) {
			continue
		}
		capabilities := materializationBoundProcessCapabilities(declaration, r.envelope)
		if materializationProcessDemands(array(at(requirement, "process_resource_limits")), capabilities) {
			return nil
		}
	}
	return invalid()
}
func materializationProcessDemands(demands, capabilities []any) bool {
	for _, demand := range demands {
		found := false
		for _, capability := range capabilities {
			if equal(at(demand, "resource"), at(capability, "resource")) && set(at(capability, "scopes"))[stringAt(demand, "scope")] && materializationLimitValue(at(demand, "soft"), capability) && materializationLimitValue(at(demand, "hard"), capability) {
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
func materializationLimitValue(v, capability any) bool {
	if text(v) == "unlimited" {
		return boolean(at(capability, "supports_unlimited"))
	}
	n, ok := number(v)
	if !ok || !n.IsInt() {
		return false
	}
	lower, ok := number(defaultMember(capability, "minimum", jsonZero))
	if !ok || n.Cmp(lower) < 0 {
		return false
	}
	if at(capability, "maximum") == nil {
		return true
	}
	upper, ok := number(at(capability, "maximum"))
	return ok && n.Cmp(upper) <= 0
}

func materializationBoundProcessCapabilities(declaration, envelope any) []any {
	capabilities := []any{}
	for _, claim := range array(at(declaration, "process_resource_limits")) {
		for _, configured := range array(at(envelope, termConfiguration, "process_resource_limits")) {
			if matchingFields(claim, configured, "resource", "minimum", "maximum", "supports_unlimited") && equalSet(set(at(claim, "scopes")), set(at(configured, "scopes"))) {
				capabilities = append(capabilities, claim)
				break
			}
		}
	}
	return capabilities
}
