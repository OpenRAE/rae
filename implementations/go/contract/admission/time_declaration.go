package admission

import (
	"math/big"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
)

func unitRatio(v any) bool {
	return v == nil || countEqual(at(v, "numerator"), 1) && countEqual(at(v, "denominator"), 1)
}
func reducedRatio(v any) bool {
	if v == nil {
		return true
	}
	n, nok := number(at(v, "numerator"))
	d, dok := number(at(v, "denominator"))
	return nok && dok && n.IsInt() && d.IsInt() && n.Sign() > 0 && d.Sign() > 0 && new(big.Int).GCD(nil, nil, n.Num(), d.Num()).Cmp(big.NewInt(1)) == 0
}
func timeDeclaration(v any) error {
	for _, section := range []string{"domains", "clocks", fieldMappings, fieldProgressionPolicies, "temporal_constraints"} {
		if !keyed(at(v, section), "address") {
			return invalid()
		}
	}
	if err := timeDomainDeclarations(v); err != nil {
		return err
	}
	for _, clock := range object(at(v, "clocks")) {
		if at(v, "domains", stringAt(clock, "time_domain_address")) == nil || (stringAt(clock, "monotonicity") == "may_jump") != boolean(at(clock, "supports_jump")) {
			return invalid()
		}
	}
	if err := timeMappings(v); err != nil {
		return err
	}
	if err := timePolicies(v); err != nil {
		return err
	}
	return timeConstraints(v)
}
func timeMappings(v any) error {
	edges := map[string][]string{}
	for _, mapping := range object(at(v, fieldMappings)) {
		source, target := stringAt(mapping, "source_domain_address"), stringAt(mapping, "target_domain_address")
		left, right := at(v, "domains", source), at(v, "domains", target)
		if source == target || left == nil || right == nil || !reducedRatio(at(mapping, "scale")) {
			return invalid()
		}
		if stringAt(mapping, "mapping_kind") == termIdentity && (!matchingFields(left, right, "tick_period_seconds", "epoch") || !unitRatio(at(mapping, "scale")) || !countEqual(defaultMember(mapping, "offset_ticks", jsonZero), 0)) {
			return invalid()
		}
		edges[source] = append(edges[source], target)
	}
	return require(!graph.HasCycle(edges))
}
func timePolicies(v any) error {
	seen := map[string]bool{}
	for _, policy := range object(at(v, fieldProgressionPolicies)) {
		ref := stringAt(policy, "clock_address")
		clock := at(v, "clocks", ref)
		if clock == nil || seen[ref] || !reducedRatio(at(policy, "pacing_ratio")) {
			return invalid()
		}
		seen[ref] = true
		mode := stringAt(policy, "advancement_mode")
		if (mode == "stepped") != (at(policy, "step_ticks") != nil) || mode != "real_time" && mode != "dilated" && !unitRatio(at(policy, "pacing_ratio")) {
			return invalid()
		}
		if (stringAt(policy, "reset_behavior") != statusUnsupported || stringAt(policy, "replay_behavior") != statusUnsupported) && !boolean(at(clock, "supports_reset")) {
			return invalid()
		}
	}
	return nil
}
func timeConstraints(v any) error {
	known := keySet(at(v, "domains"))
	for key := range object(at(v, "clocks")) {
		known[key] = true
	}
	for key := range object(at(v, fieldProgressionPolicies)) {
		known[key] = true
	}
	for _, constraint := range object(at(v, "temporal_constraints")) {
		if err := timeConstraint(v, constraint, known); err != nil {
			return err
		}
	}
	return nil
}
func fullCoordinateCompare(a, b any) (int, bool) {
	a, b = coordinateView(a), coordinateView(b)
	if object(a) == nil || object(b) == nil {
		return 0, false
	}
	for _, field := range []string{"segment", "tick", termMicrostep} {
		left, lok := number(at(a, field))
		right, rok := number(at(b, field))
		if !lok || !rok {
			return 0, false
		}
		if order := left.Cmp(right); order != 0 {
			return order, true
		}
	}
	return 0, true
}
func timeFactoryDefaults(v any) {
	for section, field := range map[string]string{fieldMappings: "scale", fieldProgressionPolicies: "pacing_ratio"} {
		for _, entry := range object(at(v, section)) {
			if at(entry, field) == nil {
				object(entry)[field] = map[string]any{"numerator": jsonOne, "denominator": jsonOne}
			}
		}
	}
}

func timeDomainDeclarations(v any) error {
	for _, domain := range object(at(v, "domains")) {
		kind, epoch := stringAt(domain, termKind), stringAt(domain, "epoch")
		if !reducedRatio(at(domain, "tick_period_seconds")) || kind == termWallClock && epoch != "unix" || kind == termMonotonic && epoch == "unix" {
			return invalid()
		}
	}
	return nil
}

func timeConstraint(v, constraint any, known map[string]bool) error {
	if at(v, "clocks", stringAt(constraint, "clock_address")) == nil || !fieldsUnique(constraint, "subject_addresses") {
		return invalid()
	}
	for _, subject := range stringsOf(at(constraint, "subject_addresses")) {
		if !known[subject] && !address.CompilerOwnedTemporalSubject(subject) {
			return invalid()
		}
	}
	valid := map[string]bool{"precedence": len(array(at(constraint, "subject_addresses"))) == 2, "duration": at(constraint, "duration_ticks") != nil, termWindow: at(constraint, "start") != nil && at(constraint, "end") != nil, kindDeadline: at(constraint, "end") != nil, "cadence": at(constraint, "cadence_ticks") != nil}[stringAt(constraint, termKind)]
	if !valid {
		return invalid()
	}
	if at(constraint, "start") != nil && at(constraint, "end") != nil {
		order, ok := fullCoordinateCompare(at(constraint, "start"), at(constraint, "end"))
		if !ok || order > 0 {
			return invalid()
		}
	}

	return nil
}
