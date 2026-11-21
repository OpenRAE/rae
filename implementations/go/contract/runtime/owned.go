package runtime

import (
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/address"
	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

func invalidRequest() error { return fault.New(fault.InvalidInput, "backend-request-invalid", nil) }

func ownedObject(input map[string]any) (map[string]any, error) {
	limits := ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}
	if admission.CheckTransportTree(input, limits) != nil {
		return nil, invalidRequest()
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, invalidRequest()
	}
	document, err := ingress.Parse(raw, limits, ingress.Object)
	if err != nil {
		return nil, invalidRequest()
	}
	result, ok := document.(map[string]any)
	if !ok {
		return nil, invalidRequest()
	}
	return result, nil
}

func ownOperations(input []ProvisionOperation) ([]ProvisionOperation, error) {
	if len(input) > value.Runtime().MaxMembers {
		return nil, invalidRequest()
	}
	result := make([]ProvisionOperation, len(input))
	aggregate := make([]any, len(input))
	trees := make([]map[string]any, len(input))
	fragments := []admission.Fragment{}
	for i, operation := range input {
		if err := checkOperation(operation); err != nil {
			return nil, err
		}
		if operation.ExecutionPolicy != nil {
			fragments = append(fragments, operation.ExecutionPolicy)
		}
		fragments = append(fragments, operation.ExecutionPolicyScopes...)

		tree := map[string]any{"payload": operation.Payload, "ordering": operation.OrderingDependencies, "refresh": operation.RefreshDependencies, "profiles": operation.ProfileBindings}
		aggregate[i] = tree
		trees[i] = tree
		// Whole-list bounds are checked before any payload copy below.
		result[i] = operation
	}
	if admission.CheckFragmentBudget(fragments, 8<<20) != nil {
		return nil, invalidRequest()
	}
	if admission.CheckTransportTree(aggregate, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRequest()
	}
	for i, operation := range input {
		copied, err := ownedObject(trees[i])
		if err != nil {
			return nil, err
		}
		result[i].Payload, _ = copied["payload"].(map[string]any)
		result[i].OrderingDependencies = slices.Clone(operation.OrderingDependencies)
		result[i].RefreshDependencies = slices.Clone(operation.RefreshDependencies)
		result[i].ProfileBindings = nil
		raw, err := json.Marshal(operation.ProfileBindings)
		if err != nil || json.Unmarshal(raw, &result[i].ProfileBindings) != nil {
			return nil, invalidRequest()
		}
		result[i].ExecutionPolicyScopes = slices.Clone(operation.ExecutionPolicyScopes)
	}
	return result, nil
}

func ownDiagnostics(input []diagnostic.Diagnostic) ([]diagnostic.Diagnostic, error) {
	if len(input) > value.Runtime().MaxMembers {
		return nil, invalidRequest()
	}
	result := slices.Clone(input)
	values := make([]any, len(input))
	for i, item := range input {
		values[i] = []string{item.Code, item.Severity, item.Stage, item.Source, item.Pointer, item.OriginalPointer, item.Message, item.Domain, item.Address}
		if item.Range != nil {
			position := *item.Range
			result[i].Range = &position
		}
	}
	if admission.CheckTransportTree(values, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64}) != nil {
		return nil, invalidRequest()
	}
	return result, nil
}

func checkOperation(operation ProvisionOperation) error {
	if !address.Valid(operation.Address) {
		return invalidRequest()
	}
	if !slices.Contains([]string{"create", "update", "delete", "unchanged"}, operation.Action) {
		return invalidRequest()
	}
	if len(operation.ExecutionPolicyScopes) > value.Runtime().MaxMembers {
		return invalidRequest()
	}
	if operation.ExecutionPolicy != nil && admission.CheckFragment(operation.ExecutionPolicy, admission.OperationExecutionPolicy) != nil {
		return invalidRequest()
	}
	for _, scope := range operation.ExecutionPolicyScopes {
		if admission.CheckFragment(scope, admission.OperationPolicyScope) != nil {
			return invalidRequest()
		}
	}
	return nil
}
