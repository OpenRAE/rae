package comparison

import (
	"slices"
	"strings"
)

type dependencyGroup struct{ dependent, rule string }

func compareDependencies(input request, before, after []ownerProjection, reasons reasonSet) []dependencyChange {
	oldGroups, newGroups := dependencyGroups(before, reasons), dependencyGroups(after, reasons)
	groups := make([]dependencyGroup, 0, len(oldGroups)+len(newGroups))
	for group := range oldGroups {
		groups = append(groups, group)
	}
	for group := range newGroups {
		groups = append(groups, group)
	}
	slices.SortFunc(groups, func(a, b dependencyGroup) int {
		return compareTuple([]string{a.dependent, a.rule}, []string{b.dependent, b.rule})
	})
	groups = slices.Compact(groups)
	result := []dependencyChange{}
	for _, group := range groups {
		result = append(result, dependencyGroupChanges(group, oldGroups[group], newGroups[group])...)
	}
	if len(result) > input.Limits.Edges {
		result = result[:input.Limits.Edges]
		reasons[reasonEdges] = true
	}
	slices.SortFunc(result, func(a, b dependencyChange) int {
		return compareTuple([]string{a.Dependent, a.Rule, stateIdentity(a.Before), stateIdentity(a.After)}, []string{b.Dependent, b.Rule, stateIdentity(b.Before), stateIdentity(b.After)})
	})
	return result
}
func dependencyGroups(input []ownerProjection, reasons reasonSet) map[dependencyGroup][]dependencyState {
	known := map[string]bool{}
	for _, projection := range input {
		known[projection.identity] = true
	}
	result := map[dependencyGroup][]dependencyState{}
	for _, projection := range input {
		for _, edge := range projection.dependencies {
			state := dependencyState{Identity: edge.target, Resolution: "resolved", Provenance: []string{edge.provenance}, Reasons: []string{}}
			if !known[edge.target] {
				state.Resolution = "unresolved"
				state.Reasons = []string{"unresolved-reference"}
				reasons["unresolved-reference"] = true
			}
			key := dependencyGroup{edge.dependent, edge.rule}
			result[key] = append(result[key], state)
		}
	}
	return result
}
func dependencyGroupChanges(group dependencyGroup, old, next []dependencyState) []dependencyChange {
	oldMap, newMap := map[string]dependencyState{}, map[string]dependencyState{}
	for _, state := range old {
		oldMap[stateKey(state)] = state
	}
	for _, state := range next {
		newMap[stateKey(state)] = state
	}
	common := []string{}
	for key := range oldMap {
		if _, exists := newMap[key]; exists {
			common = append(common, key)
		}
	}
	slices.Sort(common)
	unchanged := map[string]bool{}
	result := []dependencyChange{}
	for _, key := range common {
		state := oldMap[key]
		unchanged[key] = true
		result = append(result, dependencyChange{Dependent: group.dependent, Rule: group.rule, Version: "1", Relation: relationUnchanged, Before: &state, After: &state})
	}
	oldRemaining, nextRemaining := remainingStates(old, unchanged), remainingStates(next, unchanged)
	for index := range max(len(oldRemaining), len(nextRemaining)) {
		item := dependencyChange{Dependent: group.dependent, Rule: group.rule, Version: "1", Relation: relationChanged}
		if index < len(oldRemaining) {
			state := oldRemaining[index]
			item.Before = &state
		} else {
			item.Relation = relationAdded
		}
		if index < len(nextRemaining) {
			state := nextRemaining[index]
			item.After = &state
		} else {
			item.Relation = relationRemoved
		}
		result = append(result, item)
	}
	return result
}
func remainingStates(input []dependencyState, unchanged map[string]bool) []dependencyState {
	result := []dependencyState{}
	for _, state := range input {
		if !unchanged[stateKey(state)] {
			result = append(result, state)
		}
	}
	slices.SortFunc(result, func(a, b dependencyState) int { return compareStrings(stateKey(a), stateKey(b)) })
	return result
}
func stateKey(input dependencyState) string {
	return input.Identity + "\x00" + input.Resolution + "\x00" + strings.Join(input.Provenance, "\x00")
}
func stateIdentity(input *dependencyState) string {
	if input == nil {
		return ""
	}
	return input.Identity
}
