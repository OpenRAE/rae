package governance

import (
	"fmt"
	"regexp"
	"slices"
)

const invalidRequirementPhases = "phases must be a list of mappings with a text id"

const requirementPolicyPath = "tools/policy/requirement_order.yaml"

type requirementPhase struct {
	id             string
	uids, blockers []string
	patterns       []*regexp.Regexp
	manual         bool
}

type requirementPolicy struct {
	project              string
	source               any
	phases               []requirementPhase
	ownership            map[string][]string
	codeRoots, testRoots []string
}

func orderPolicyError(message string) error {
	return policyInputError(requirementPolicyPath + " " + message)
}

func loadRequirementPolicy(r *repository) (*requirementPolicy, error) {
	data, err := r.read(requirementPolicyPath)
	if err != nil {
		return nil, err
	}
	value, err := yamlValue(data, true)
	if err != nil {
		return nil, err
	}
	return parseRequirementPolicy(value)
}

func parseRequirementPolicy(value any) (*requirementPolicy, error) {
	m, ok := value.(*mapping)
	if !ok {
		return nil, orderPolicyError("must be a mapping with a text project")
	}
	project, ok := m.get("project").(string)
	if !ok {
		return nil, orderPolicyError("must be a mapping with a text project")
	}
	phases, err := orderPhases(m)
	if err != nil {
		return nil, err
	}
	ownership, err := orderOwnership(m)
	if err != nil {
		return nil, err
	}
	trace, _ := m.get("traceability").(*mapping)
	code, codeOK := stringList(trace.get("required_code_roots"), false)
	tests, testsOK := stringList(trace.get("required_test_roots"), false)
	if trace == nil || !codeOK || !testsOK {
		return nil, orderPolicyError("traceability must have text lists of code and test roots")
	}
	source := m.get("requirement_source")
	if !m.has("requirement_source") {
		source = "ground-control-http"
	}
	return &requirementPolicy{project: project, source: source, phases: phases, ownership: ownership, codeRoots: code, testRoots: tests}, nil
}

func orderPhases(root *mapping) ([]requirementPhase, error) {
	value := root.get("phases")
	if !root.has("phases") {
		value = []any{}
	}
	items, ok := value.([]any)
	if !ok {
		return nil, orderPolicyError(invalidRequirementPhases)
	}
	ids := []string{}
	for _, item := range items {
		m, _ := item.(*mapping)
		id, valid := m.get("id").(string)
		if m == nil || !valid {
			return nil, orderPolicyError(invalidRequirementPhases)
		}
		ids = append(ids, id)
	}
	phases := make([]requirementPhase, len(items))
	for i, item := range items {
		m, ok := item.(*mapping)
		if !ok {
			return nil, orderPolicyError(invalidRequirementPhases)
		}
		phase, err := orderPhase(m, ids, i)
		if err != nil {
			return nil, err
		}
		phases[i] = phase
	}
	return phases, nil
}

func orderPhase(m *mapping, ids []string, index int) (requirementPhase, error) {
	lists := map[string][]string{}
	for _, field := range []string{"requirements", "patterns", "blocked_until"} {
		if !m.has(field) {
			lists[field] = []string{}
			continue
		}
		items, ok := stringList(m.get(field), false)
		if !ok {
			return requirementPhase{}, orderPolicyError(fmt.Sprintf("phases[%d].%s must be a list of text", index, field))
		}
		lists[field] = items
	}
	for _, blocker := range lists["blocked_until"] {
		if !slices.Contains(ids, blocker) {
			return requirementPhase{}, orderPolicyError(fmt.Sprintf("phases[%d].blocked_until names an unknown phase", index))
		}
	}
	patterns := []*regexp.Regexp{}
	for _, source := range lists["patterns"] {
		pattern, err := regexp.Compile(source)
		if err != nil {
			return requirementPhase{}, orderPolicyError(fmt.Sprintf("phases[%d].patterns has an invalid pattern", index))
		}
		patterns = append(patterns, pattern)
	}
	id, ok := m.get("id").(string)
	if !ok {
		return requirementPhase{}, orderPolicyError(invalidRequirementPhases)
	}
	return requirementPhase{id: id, uids: lists["requirements"], patterns: patterns, blockers: lists["blocked_until"], manual: truth(m.get("manual_release"))}, nil
}

func orderOwnership(root *mapping) (map[string][]string, error) {
	value := root.get("ownership")
	if !root.has("ownership") {
		value = newMapping()
	}
	m, ok := value.(*mapping)
	if !ok {
		return nil, orderPolicyError("ownership must map phases to lists of text")
	}
	owners := map[string][]string{}
	for _, key := range m.keys {
		roots, valid := stringList(m.get(key), false)
		if !valid {
			return nil, orderPolicyError("ownership must map phases to lists of text")
		}
		if id, text := key.(string); text {
			owners[id] = roots
		}
	}
	return owners, nil
}
