package admission

import (
	"encoding/json"
	"math/big"
	"strconv"
	"strings"
)

func factDeclarations(declarations map[string]any) error {
	for _, declaration := range declarations {
		if !fieldsUnique(declaration, "authority_refs") || !fieldsUnique(at(declaration, "visibility"), "participant_addresses", "workflow_addresses") {
			return invalid()
		}
		if (stringAt(declaration, "source_kind") == "secret_reference") != (stringAt(declaration, "sensitivity") == sensitivitySecret) {
			return invalid()
		}
	}
	return nil
}
func factSinks(sinks map[string]any) error {
	for _, sink := range sinks {
		if !strings.HasPrefix(stringAt(sink, "action_contract_address"), "participant.action-contract.") || !strings.HasPrefix(stringAt(sink, "target_field"), "input.") || len(stringAt(sink, "target_field")) <= len("input.") {
			return invalid()
		}
		if !fieldsUnique(sink, "allowed_source_kinds", "allowed_scope_kinds", "allowed_sensitivities", "authority_refs") {
			return invalid()
		}
	}
	return nil
}
func factScope(v any) error {
	expected := map[string]map[string]bool{kindRun: {}, termParticipant: {fieldParticipantAddress: true}, "episode": {fieldParticipantAddress: true, fieldEpisodeID: true}, termWorkflow: {fieldWorkflowAddress: true}}[stringAt(v, termKind)]
	if expected == nil {
		return invalid()
	}
	for _, field := range []string{fieldParticipantAddress, fieldEpisodeID, fieldWorkflowAddress} {
		if (at(v, field) != nil) != expected[field] {
			return invalid()
		}
	}
	return nil
}
func factVersionShape(v any) error {
	if err := factScope(at(v, "scope")); err != nil {
		return err
	}
	if !fieldsUnique(v, fieldEvidenceRefs, "provenance_refs") {
		return invalid()
	}
	if stringAt(v, "sensitivity") == sensitivitySecret {
		return require(at(v, "secret_ref") != nil && at(v, "value") == nil)
	}
	return require(at(v, "value") != nil && at(v, "secret_ref") == nil && scalarMatches(at(v, "value"), stringAt(v, "value_type")))
}
func scalarMatches(v any, kind string) bool {
	switch kind {
	case termNull:
		return v == nil
	case "string", "reference":
		_, ok := v.(string)
		return ok
	case typeBoolean:
		_, ok := v.(bool)
		return ok
	case termInteger:
		n, ok := number(v)
		return ok && n.IsInt()
	case "number":
		_, ok := v.(json.Number)
		return ok
	default:
		return false
	}
}

// referenceScalarEqual preserves the Python model's scalar equality at this
// explicit comparison boundary. It is not a conversion or a type-admission
// check: factVersionShape separately checks every concrete version value.
func referenceScalarEqual(a, b any) bool {
	left, ok := referenceNumber(a)
	if !ok {
		return equal(a, b)
	}
	right, ok := referenceNumber(b)
	return ok && left.Cmp(right) == 0
}
func referenceNumber(v any) (*big.Rat, bool) {
	switch value := v.(type) {
	case bool:
		if value {
			return big.NewRat(1, 1), true
		}
		return big.NewRat(0, 1), true
	case json.Number:
		if strings.ContainsAny(value.String(), ".eE") {
			n, err := strconv.ParseFloat(value.String(), 64)
			if err != nil {
				return nil, false
			}
			rational := new(big.Rat).SetFloat64(n)
			return rational, rational != nil
		}
		return number(value)
	default:
		return nil, false
	}
}
