package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/internal/base/value"
)

// These are private wire views, consumed only at the publication boundary.
// Shared value traversal owns depth, nodes, members and aggregate scalar work.
func planProjectionValue(input any) (any, error) {
	switch item := input.(type) {
	case json.RawMessage:
		return planRawValue(item)
	case materializationSourceWire:
		return materializationBudgetValue(item)
	case *string:
		if item == nil {
			return nil, nil //nolint:nilnil // An absent optional wire field projects to JSON null.
		}
		return *item, nil
	case *json.Number:
		if item == nil {
			return nil, nil //nolint:nilnil // An absent optional wire field projects to JSON null.
		}
		return *item, nil
	case []string:
		return planSequence(item)
	case []json.RawMessage:
		return planSequence(item)
	case []map[string]any:
		return planSequence(item)
	case []planOperation:
		return planSequence(item)
	case []authorityWire:
		return planSequence(item)
	case []constraintWire:
		return planSequence(item)
	case []boundWire:
		return planSequence(item)
	case []binding.DomainProfileBindingV1:
		return planSequence(item)
	default:
		return planRecordProjection(input)
	}
}
func planRecordProjection(input any) (any, error) {
	switch item := input.(type) {
	case planOperation:
		return operationBudgetValue(item), nil
	case authorityWire:
		return authorityBudgetValue(item), nil
	case constraintWire:
		return map[string]any{termAddress: item.Address, "field_path": item.Path, "concern": item.Concern, "posture": item.Posture, "value_domain": item.Domain, "governing_scope": item.Scope, "provenance": item.Provenance}, nil
	case boundWire:
		return map[string]any{"identity_digest": item.Identity, "value_pointer": item.Pointer, termDomain: item.Domain}, nil
	case snapshotEntry:
		return map[string]any{termAddress: item.Address, termDomain: item.Domain, "resource_type": item.Kind, termPayload: item.Payload, "ordering_dependencies": item.Ordering, "refresh_dependencies": item.Refresh, "profile_bindings": item.Profiles, "status": item.Status}, nil
	case map[string]snapshotEntry:
		return snapshotBudgetEntries(item)
	case binding.DomainProfileBindingV1:
		return planGeneratedValue(item)
	case *binding.PlanRealizationProfilesV1:
		if item == nil {
			return nil, nil //nolint:nilnil // An absent optional wire field projects to JSON null.
		}
		return planGeneratedValue(item)
	default:
		return input, nil // Unknown carriers are refused by value.ValidateProjected.
	}
}

func planSequence[T any](input []T) ([]any, error) {
	if input == nil {
		return []any(nil), nil
	}
	if len(input) > value.Plan().MaxMembers {
		return nil, value.ErrLimit
	}
	result := make([]any, len(input))
	for i, item := range input {
		result[i] = item
	}
	return result, nil
}
func snapshotBudgetEntries(input map[string]snapshotEntry) (any, error) {
	if len(input) > value.Runtime().MaxMembers {
		return nil, value.ErrLimit
	}
	result := make(map[string]any, len(input))
	for key, item := range input {
		result[key] = item
	}
	return result, nil
}
func planRawValue(raw []byte) (any, error) {
	if len(raw) == 0 {
		return nil, nil //nolint:nilnil // An absent optional wire field projects to JSON null.
	}
	limits := value.Plan()
	if len(raw) > 8<<20 {
		return nil, value.ErrLimit
	}
	// Strict ingress accepts scalar leaves through a bounded one-element array.
	parsed, err := ingress.Parse(append(append([]byte{'['}, raw...), ']'), ingress.Limits{MaxBytes: len(raw) + 2, MaxDepth: limits.MaxDepth + 1}, ingress.Array)
	if err != nil {
		return nil, err
	}
	sequence, ok := parsed.([]any)
	if !ok || len(sequence) != 1 {
		return nil, value.ErrInput
	}
	return sequence[0], nil
}
func planGeneratedValue(input any) (any, error) {
	if err := admission.CheckTransport(input, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128}); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(input)
	if err != nil {
		return nil, err
	}
	return planRawValue(raw)
}
func operationBudgetValue(item planOperation) map[string]any {
	result := map[string]any{"action": item.Action, termAddress: item.Address, "resource_type": item.Kind, termPayload: item.Payload, "ordering_dependencies": item.Ordering, "refresh_dependencies": item.Refresh}
	if len(item.Profiles) > 0 {
		result["profile_bindings"] = item.Profiles
	}
	if len(item.ExecutionPolicy) > 0 {
		result["execution_policy"] = item.ExecutionPolicy
	}
	if len(item.ExecutionPolicyScopes) > 0 {
		result["execution_policy_scopes"] = item.ExecutionPolicyScopes
	}
	return result
}
func authorityBudgetValue(item authorityWire) map[string]any {
	result := map[string]any{termAddress: item.Address, "field_path": item.Path, termDomain: item.Domain, "requirement_kind": item.Kind, "payload_pointer": item.Pointer, "mode": item.Mode, "source": item.Source, "provenance": item.Provenance, "governing_scope": item.Scope, "bounds": item.Bounds, "verification_scope": item.Verification, "required_observation_strength": item.Strength}
	if len(item.Structure) > 0 {
		result["structure"] = item.Structure
	}
	if len(item.Constraint) > 0 {
		result["constraint_document"] = item.Constraint
	}
	if item.Binding != "" {
		result["constraint_binding"] = item.Binding
	}
	return result
}

// This private carrier is constructed only from the admitted source field.
// A user data member named snapshot cannot grant the document text ceiling.
type materializationSourceWire json.RawMessage

func (source materializationSourceWire) MarshalJSON() ([]byte, error) {
	return json.RawMessage(source).MarshalJSON()
}
func materializationBudgetValue(raw materializationSourceWire) (any, error) {
	parsed, err := planRawValue(raw)
	if err != nil {
		return nil, err
	}
	record, ok := parsed.(map[string]any)
	if !ok {
		return nil, value.ErrInput
	}
	snapshot, ok := record["snapshot"].(string)
	if !ok {
		return nil, value.ErrInput
	}
	record["snapshot"] = value.DeclaredDocument(snapshot)
	return record, nil
}
