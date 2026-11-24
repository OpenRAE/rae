package admission

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

func flowUniqueReferences(values []string) bool {
	if len(values) > 100000 {
		return false
	}
	remaining := 8 * 1048576
	for _, value := range values {
		if value == "" || len(value) > remaining {
			return false
		}
		remaining -= len(value)
	}
	return unique(values)
}

func flowSelectionDocument(selection FlowActionSelection) (any, error) {
	if !strings.HasPrefix(selection.ActionContractAddress, "participant.action-contract.") || selection.ArgumentShapeRef == "" || selection.ProposalRef == "" || len(selection.Arguments) > 4096 {
		return nil, invalid()
	}
	result := map[string]any{"action_contract_address": selection.ActionContractAddress, "argument_shape_ref": selection.ArgumentShapeRef, "proposal_ref": selection.ProposalRef}
	for field, values := range map[string][]string{"defaulted_argument_names": selection.DefaultedArgumentNames, "omitted_argument_names": selection.OmittedArgumentNames, "normalization_disclosure_refs": selection.NormalizationDisclosureRefs, "omission_disclosure_refs": selection.OmissionDisclosureRefs, "default_disclosure_refs": selection.DefaultDisclosureRefs, "loss_disclosure_refs": selection.LossDisclosureRefs} {
		if !flowUniqueReferences(values) {
			return nil, invalid()
		}
		result[field] = jsonStrings(values)
	}
	arguments, err := flowSelectedArguments(selection.Arguments)
	if err != nil {
		return nil, err
	}
	result["normalized_arguments"] = arguments
	return result, nil
}

func flowArgumentValue(v any) bool {
	if list, ok := v.([]any); ok {
		for _, item := range list {
			if !flowArgumentScalar(item) {
				return false
			}
		}
		return true
	}
	return flowArgumentScalar(v)
}
func flowArgumentScalar(v any) bool {
	switch v.(type) {
	case string, bool:
		return true
	case json.Number:
		_, ok := number(v)
		return ok
	default:
		return false
	}
}

func (e *Validator) flowOwnerFragment(id, name string, raw []byte) (any, error) {
	v, err := e.low.DefaultedObjectFragment(id, schemaDefinitionsPrefix+name, raw, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 64})
	if err != nil {
		return nil, err
	}
	if _, err = e.controlModel(name, v); err != nil {
		return nil, err
	}
	if _, err = flowModel(name, v); err != nil {
		return nil, err
	}
	return v, nil
}

func (e *Validator) flowOwnerFragments(name string, raw [][]byte) ([]any, error) {
	if len(raw) > 4096 {
		return nil, invalid()
	}
	remaining := 64 * 1048576
	result := make([]any, 0, len(raw))
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := e.flowOwnerFragment(termRuntimeSnapshotV1, name, data)
		if err != nil {
			return nil, err
		}
		result = append(result, v)
	}
	return result, nil
}

func flowSelectedArguments(values map[string]json.RawMessage) ([]any, error) {
	names := make([]string, 0, len(values))
	for name := range values {
		names = append(names, name)
	}
	slices.Sort(names)
	arguments := make([]any, 0, len(names))
	remaining := 8 * 1048576
	for _, name := range names {
		raw := values[name]
		if name == "" || len(raw) > remaining {
			return nil, invalid()
		}
		remaining -= len(raw)
		wrapped, err := json.Marshal(map[string]json.RawMessage{"value": raw})
		if err != nil {
			return nil, invalid()
		}
		parsed, err := ingress.Parse(wrapped, ingress.Limits{MaxBytes: 8 * 1048576, MaxDepth: 4}, ingress.Object)
		if err != nil {
			return nil, err
		}
		value := at(parsed, "value")
		if !flowArgumentValue(value) {
			return nil, invalid()
		}
		arguments = append(arguments, []any{name, value})
	}
	return arguments, nil
}
