package planning

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/canonjson"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/graph"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func reconcileResources(resources map[string]plannedResource, entries map[string]snapshotEntry, requirements []realization.Requirement) (map[string]string, map[string]snapshotEntry, error) {
	actions := map[string]string{}
	deleted := map[string]snapshotEntry{}
	for _, address := range slices.Sorted(maps.Keys(resources)) {
		resource := resources[address]
		entry, exists := entries[address]
		action := termCreate
		if exists {
			matches, err := entryMatches(entry, resource, requirements)
			if err != nil {
				return nil, nil, err
			}
			action = termUpdate
			if matches {
				action = termUnchanged
			}
		}
		actions[address] = action
	}
	for address, entry := range entries {
		if _, exists := resources[address]; !exists {
			actions[address] = termDelete
			deleted[address] = entry
		}
	}
	refreshDependents(resources, actions)
	return actions, deleted, nil
}

func entryMatches(entry snapshotEntry, resource plannedResource, requirements []realization.Requirement) (bool, error) {
	if entry.Domain != resource.facts.Domain || entry.Kind != resource.facts.Kind || !slices.Equal(entry.Ordering, resource.facts.OrderingDependencies) || !slices.Equal(entry.Refresh, resource.facts.RefreshDependencies) || !profileBindingsEqual(entry.Profiles, resource.profiles) {
		return false, nil
	}
	owner, err := planOwner()
	if err != nil {
		return false, err
	}
	fragment := func(raw []byte) (admission.Fragment, error) {
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		var value any
		if checkErr := decoder.Decode(&value); checkErr != nil {
			return nil, invalidPlan()
		}
		return admission.AdmitFragment(owner, admission.RealizationValue, value, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	}
	before, err := fragment(resource.payload)
	if err != nil {
		if category, _ := fault.CategoryOf(err); category == fault.InvalidInput {
			return false, nil
		}
		return false, err
	}
	after, err := fragment(entry.Payload)
	if err != nil {
		if category, _ := fault.CategoryOf(err); category == fault.InvalidInput {
			return false, nil
		}
		return false, err
	}
	return realization.Equivalent(requirements, resource.facts.Address, before, after)
}

func profileBindingsEqual(left, right []binding.DomainProfileBindingV1) bool {
	if len(left) != len(right) {
		return false
	}
	if len(left) == 0 {
		return true
	}
	first, err := json.Marshal(left)
	if err != nil {
		return false
	}
	second, err := json.Marshal(right)
	if err != nil {
		return false
	}
	first, err = canonjson.JCS(first)
	if err != nil {
		return false
	}
	second, err = canonjson.JCS(second)
	return err == nil && bytes.Equal(first, second)
}

func domainOperations(domain string, resources map[string]plannedResource, actions map[string]string, deleted map[string]snapshotEntry) ([]planOperation, error) {
	order, err := graph.Order(dependencyGraph(resources, domain, false), nil)
	if err != nil {
		return nil, err
	}
	operations := make([]planOperation, 0, len(order))
	for _, address := range order {
		resource := resources[address]
		operations = append(operations, planOperation{Action: actions[address], Address: address, Kind: resource.facts.Kind, Payload: resource.payload, Ordering: nonNilStrings(resource.facts.OrderingDependencies), Refresh: nonNilStrings(resource.facts.RefreshDependencies), Profiles: resource.profiles})
	}
	deleteResources := map[string]plannedResource{}
	for address, entry := range deleted {
		if entry.Domain == domain {
			deleteResources[address] = plannedResource{facts: processor.Resource{Address: address, Domain: entry.Domain, Kind: entry.Kind, OrderingDependencies: entry.Ordering, RefreshDependencies: entry.Refresh}}
		}
	}
	deleteOrder, err := graph.Order(dependencyGraph(deleteResources, domain, false), nil)
	if err != nil {
		return nil, err
	}
	slices.Reverse(deleteOrder)
	for _, address := range deleteOrder {
		entry := deleted[address]
		operations = append(operations, planOperation{Action: termDelete, Address: address, Kind: entry.Kind, Payload: entry.Payload, Ordering: nonNilStrings(entry.Ordering), Refresh: nonNilStrings(entry.Refresh)})
	}
	return operations, nil
}
func nonNilStrings(input []string) []string {
	if input == nil {
		return []string{}
	}
	return input
}
