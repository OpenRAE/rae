package admission

const (
	termConstraints = "constraints"
	termNamespace   = "namespace"
	termPresent     = "present"
)

func sdlDesignation(v any) error {
	for _, collection := range []string{"scopes", termConstraints} {
		seen := map[string]bool{}
		for _, row := range array(at(v, collection)) {
			namespace := array(at(row, termNamespace))
			if namespace == nil {
				namespace = []any{}
			}
			identity := map[string]any{termNamespace: namespace, "pointer": at(row, "field_pointer")}
			if collection == termConstraints {
				identity["concern"] = at(row, "concern")
			}
			key, err := jsonDigest(identity)
			if err != nil || seen[key] {
				return invalid()
			}
			seen[key] = true
		}
	}
	return nil
}

func sdlInjectDelivery(v any) error {
	// The published shape enforces control-block exclusivity and complete
	// flat agreements. Coordinates remain an intrinsic model predicate.
	if at(v, "control") != nil || stringAt(v, "delivery_kind") == "disclosure" {
		return nil
	}
	return require(!numericGreater(at(v, "control_valid_from_order"), at(v, "control_effective_order")) && !numericGreater(at(v, "control_effective_order"), at(v, "control_valid_until_order")))
}
