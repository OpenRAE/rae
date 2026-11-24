package planning

import (
	"encoding/json"
	"maps"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/processor"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

func (plan *executionPlan) reportedDescendants() (map[string]bool, error) {
	retained := map[string]bool{}
	entries := fieldValue(plan.context.Snapshot.Entries)
	for _, archive := range fieldValue(plan.context.Snapshot.MaterializationAttestations) {
		raw := fieldValue(archive.Inventory)
		if len(raw) == 0 || string(raw) == termNull {
			continue
		}
		var inventory binding.BackendRuntimeDescendantsV1
		if json.Unmarshal(raw, &inventory) != nil {
			return nil, invalidPlan()
		}
		for _, descendant := range fieldValue(inventory.Descendants) {
			address := fieldValue(descendant.Address)
			if _, present := entries[address]; present {
				retained[address] = true
			}
		}
	}
	return retained, nil
}

func (plan *executionPlan) retainReportedDescendants(model processor.CompiledScenario, entries map[string]snapshotEntry) ([]diagnostic.Diagnostic, error) {
	retained, err := plan.reportedDescendants()
	if err != nil || len(retained) == 0 {
		return nil, err
	}
	operations := retainDescendantOperations(plan.operations[termProvisioning], retained)
	plan.operations[termProvisioning] = operations
	submitted := map[string]bool{}
	for _, operation := range operations {
		submitted[operation.Address] = true
	}
	members, err := plan.collectionMembers(entries, "")
	if err != nil {
		return nil, err
	}
	authority, err := realization.CompileNodeCollection(model.Original, members)
	if err != nil {
		return nil, err
	}
	for _, address := range slices.Sorted(maps.Keys(retained)) {
		if submitted[address] {
			continue
		}
		entry := entries[address]
		member, err := snapshotCollectionMember(entry)
		if err != nil {
			return nil, err
		}
		members = append(members, member)
	}
	if authority != nil {
		valid, err := realization.NodeCollectionAdmits(authority, members)
		if err != nil {
			return nil, err
		}
		if valid {
			return nil, nil
		}
	}
	return []diagnostic.Diagnostic{planDiagnostic("realization.descendant-collection-conflict", termProvisioning, "nodes", "Accepted descendants require explicit lifecycle disposition before this collection can close.")}, nil
}

func snapshotCollectionMember(entry snapshotEntry) (realization.NodeCollectionMember, error) {
	member := realization.NodeCollectionMember{Address: entry.Address, Kind: entry.Kind}
	if entry.Kind != termNode && entry.Kind != termNetwork {
		return member, nil
	}
	var payload struct {
		Name *string `json:"name"`
	}
	if json.Unmarshal(entry.Payload, &payload) != nil || payload.Name == nil {
		return member, invalidPlan()
	}
	member.Name = *payload.Name
	return member, nil
}

func retainDescendantOperations(input []planOperation, retained map[string]bool) []planOperation {
	operations := make([]planOperation, 0, len(input))
	for _, operation := range input {
		if operation.Action == termDelete && retained[operation.Address] {
			continue
		}
		operations = append(operations, operation)
	}
	return operations
}
