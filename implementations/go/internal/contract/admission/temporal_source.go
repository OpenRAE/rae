package admission

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func sectionName(reference, section string, declarations any) (string, bool) {
	if _, ok := object(declarations)[reference]; ok {
		return reference, true
	}
	name, qualified := strings.CutPrefix(reference, section+".")
	_, ok := object(declarations)[name]
	return name, qualified && ok
}
func temporalSource(i validation.Invocation) error {
	v := sdlInstance(i)
	for name, action := range object(at(v, "action_contracts")) {
		for _, temporal := range array(at(action, "temporal_contracts")) {
			if at(temporal, "shared_time_binding") == nil {
				continue
			}
			if err := temporalSourceBinding(v, name, temporal); err != nil {
				return err
			}
		}
	}
	return nil
}
func temporalSourceBinding(v any, name string, temporal any) error {
	binding := at(temporal, "shared_time_binding")
	clock, cok := sectionName(stringAt(binding, "clock_ref"), "clocks", at(v, "clocks"))
	constraint, qok := sectionName(stringAt(binding, "constraint_ref"), "temporal_constraints", at(v, "temporal_constraints"))
	if !cok && !variableRef(stringAt(binding, "clock_ref")) || !qok && !variableRef(stringAt(binding, "constraint_ref")) {
		return invalid()
	}
	if !cok || !qok {
		return nil
	}
	bound := at(v, "temporal_constraints", constraint)
	if stringAt(bound, "clock_ref") != clock || !set(at(bound, "subject_refs"))[name] && !set(at(bound, "subject_refs"))["action_contracts."+name] {
		return invalid()
	}
	if err := temporalClockDomain(v, clock, temporal); err != nil {
		return err
	}
	expected := termWindow
	if stringAt(temporal, "temporal_kind") == kindDeadline {
		expected = kindDeadline
	}
	if stringAt(bound, "constraint_kind") != expected {
		return invalid()
	}
	if stringAt(temporal, "temporal_kind") == "dwell" {
		if err := temporalDwellSource(v, name, binding, bound); err != nil {
			return err
		}
	}
	return temporalPolicyClock(v, name, clock)
}
func temporalDwellSource(v any, name string, binding, constraint any) error {
	var condition any
	for _, precondition := range array(at(v, "action_contracts", name, termPreconditions)) {
		if equal(at(precondition, "precondition_id"), at(binding, "condition_precondition_id")) {
			condition = precondition
		}
	}
	if condition == nil {
		return invalid()
	}
	boundary, ok := sectionName(stringAt(binding, "observation_boundary_ref"), "observation_boundaries", at(v, "observation_boundaries"))
	if !ok && !variableRef(stringAt(binding, "observation_boundary_ref")) {
		return invalid()
	}
	if ok {
		if err := temporalBoundarySupport(at(v, "observation_boundaries", boundary), condition); err != nil {
			return err
		}
		if err := temporalBoundaryOwners(v, name, boundary); err != nil {
			return err
		}
	}
	return temporalDwellInterval(constraint)
}

func temporalBoundarySupport(boundary, condition any) error {
	observable := set(at(boundary, "observable_refs"))
	for _, rule := range array(at(boundary, "view_rules")) {
		ref := stringAt(rule, "information_ref")
		if slices.Contains([]string{"observable", termDisclosed, "discovered", "inferred", "deceptive"}, stringAt(rule, "disposition")) {
			observable[ref] = true
		} else {
			delete(observable, ref)
		}
	}
	for field, allowed := range map[string]map[string]bool{"support_refs": observable, fieldEvidenceRefs: set(at(boundary, fieldEvidenceRefs))} {
		for _, ref := range stringsOf(at(condition, field)) {
			if !allowed[ref] && !variableRef(ref) {
				return invalid()
			}
		}
	}
	return nil
}
func namesContain(refs any, name, section string, declarations any) bool {
	for _, ref := range stringsOf(refs) {
		resolved, ok := sectionName(ref, section, declarations)
		if ok && resolved == name {
			return true
		}
	}
	return false
}
func temporalBoundaryOwners(v any, name, boundary string) error {
	for _, agent := range object(at(v, "agents")) {
		if namesContain(at(agent, termActions), name, "action_contracts", at(v, "action_contracts")) && !namesContain(at(agent, "observation_boundaries"), boundary, "observation_boundaries", at(v, "observation_boundaries")) {
			return invalid()
		}
	}
	for _, spec := range object(at(v, "behavior_specifications")) {
		if !namesContain(at(spec, "action_contract_refs"), name, "action_contracts", at(v, "action_contracts")) {
			continue
		}
		if !namesContain(at(spec, "observation_boundary_refs"), boundary, "observation_boundaries", at(v, "observation_boundaries")) {
			return invalid()
		}
		selected, ok := sectionName(stringAt(spec, "autonomous_execution", "observation_boundary_ref"), "observation_boundaries", at(v, "observation_boundaries"))
		if ok && selected != boundary {
			return invalid()
		}
	}
	return nil
}
func temporalPolicyClock(v any, name, clock string) error {
	for _, spec := range object(at(v, "behavior_specifications")) {
		policy := at(spec, "autonomous_execution")
		if policy == nil {
			continue
		}
		refs := at(policy, "action_order")
		if at(policy, "action_candidates") != nil {
			choices := make([]any, 0, len(object(at(policy, "action_candidates"))))
			for _, candidate := range object(at(policy, "action_candidates")) {
				choices = append(choices, at(candidate, "action_ref"))
			}
			refs = choices
		}
		if !namesContain(refs, name, "action_contracts", at(v, "action_contracts")) {
			continue
		}
		selected, ok := sectionName(stringAt(policy, "clock_ref"), "clocks", at(v, "clocks"))
		if ok && selected != clock {
			return invalid()
		}
	}
	return nil
}

func temporalClockDomain(v any, clock string, temporal any) error {
	domain, dok := sectionName(stringAt(v, "clocks", clock, "time_domain_ref"), "time_domains", at(v, "time_domains"))
	if dok {
		expected := map[string]string{"simulated": "simulation_time", termWallClock: "wall_clock_time", "logical": "scenario_time", termMonotonic: "scenario_time", termExternal: "backend_time"}[stringAt(v, "time_domains", domain, termKind)]
		if stringAt(temporal, "time_domain") != expected {
			return invalid()
		}
	}
	return nil
}

func temporalDwellInterval(constraint any) error {
	if at(constraint, "start") != nil && at(constraint, "end") != nil {
		order, ok := coordinateCompare(at(constraint, "start"), at(constraint, "end"))
		if !ok || order >= 0 {
			return invalid()
		}
	}
	return nil
}
