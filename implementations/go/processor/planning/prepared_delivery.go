package planning

import (
	"encoding/json"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/realization"
)

// CheckPreparedDelivery compares returned values with the admitted completion.
// It asserts no delivery result or independent observation authority.
func CheckPreparedDelivery(input PreparedSelection, snapshot binding.RuntimeSnapshotV1) (string, error) {
	selection, err := nativePreparedSelection(input)
	if err != nil {
		return "", err
	}
	if err := admission.CheckPreparedSnapshot(snapshot); err != nil {
		return "", err
	}
	if err := checkTransport("runtime-snapshot-v1", snapshot); err != nil {
		return "", err
	}
	operations := map[string]planOperation{}
	for _, operation := range selection.operations {
		operations[operation.Address] = operation
	}
	for _, authority := range selection.authorities {
		if authority.Posture == "closed" {
			continue
		}
		operation, hasOperation := operations[authority.Address]
		raw, hasEntry := fieldValue(snapshot.Entries)[authority.Address]
		if !hasOperation || !hasEntry {
			continue
		}
		var entry snapshotEntry
		if json.Unmarshal(raw, &entry) != nil {
			return "", invalidPlan()
		}
		violation, err := selection.preparedConcernDeliveryViolation(authority, operation, entry, snapshot)
		if err != nil || violation != "" {
			return violation, err
		}
	}
	return selection.additionalDeliveryViolation(snapshot)
}
func (selection *preparedSelection) preparedConcernDeliveryViolation(authority realization.Authority, operation planOperation, entry snapshotEntry, snapshot binding.RuntimeSnapshotV1) (string, error) {
	expectedPayload, err := preparedPayload(operation.Payload)
	if err != nil {
		return "", err
	}
	actualPayload, err := preparedPayload(entry.Payload)
	if err != nil {
		return "", err
	}
	expected, hasExpected := preparedPointer(expectedPayload, authority.PayloadPath)
	actual, hasActual := preparedPointer(actualPayload, authority.PayloadPath)
	actual, hasActual = preparedDeliveredValue(authority, snapshot, actual, hasActual)
	if !hasExpected && !hasActual {
		return "", nil
	}
	if !hasExpected || !hasActual {
		return "Backend did not deliver its admitted realization completion.", nil
	}
	requirement, found := selection.requirementByConcern[preparedConcernKey{authority.Address, authority.FieldPath, authority.Concern}]
	if !found {
		return "", invalidPlan()
	}
	matches, err := preparedDeliveryConcernEqual(requirement, expected, actual)
	if err != nil {
		return "", err
	}
	if !matches {
		return "Backend did not deliver its admitted realization completion.", nil
	}
	return "", nil
}

func nativePreparedSelection(input PreparedSelection) (*preparedSelection, error) {
	selection, ok := input.(*preparedSelection)
	if !ok || selection == nil || selection.original == nil {
		return nil, invalidPlan()
	}
	return selection, nil
}
func preparedDeliveryConcernEqual(requirement realization.Requirement, expected, actual any) (bool, error) {
	if requirement.Kind == "compute-substrate" {
		return preparedJSONEqual(expected, actual), nil
	}
	owner, err := planOwner()
	if err != nil {
		return false, err
	}
	before, err := admission.AdmitFragment(owner, admission.RealizationValue, expected, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	after, err := admission.AdmitFragment(owner, admission.RealizationValue, actual, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 128})
	if err != nil {
		return false, err
	}
	expectedProjection, err := realization.ProjectConcern(requirement.Kind, before, false, requirement.Constraint != nil)
	if err != nil {
		return false, err
	}
	actualProjection, err := realization.ProjectConcern(requirement.Kind, after, true, requirement.Constraint != nil)
	if err != nil {
		return false, err
	}
	return preparedJSONEqual(expectedProjection.Document(), actualProjection.Document()), nil
}
func preparedDeliveredValue(authority realization.Authority, snapshot binding.RuntimeSnapshotV1, fallback any, present bool) (any, bool) {
	field, operatingSystem := map[string]string{termOsFamily: "family", termOsDistribution: "distribution", termOsVersion: "version"}[authority.Concern]
	if !operatingSystem {
		return fallback, present
	}
	for _, observation := range fieldValue(snapshot.RealizationObservations) {
		if fieldValue(observation.Address) != authority.Address || fieldValue(observation.Domain) != authority.Domain || fieldValue(observation.RequirementKind) != "operating-system" {
			continue
		}
		var identity map[string]json.RawMessage
		if json.Unmarshal(fieldValue(observation.OperatingSystem), &identity) != nil || identity == nil {
			return fallback, present
		}
		raw, found := identity[field]
		if !found {
			return nil, false
		}
		var value string
		if json.Unmarshal(raw, &value) != nil {
			return nil, false
		}
		return value, true
	}
	return fallback, present
}
func (selection *preparedSelection) additionalDeliveryViolation(snapshot binding.RuntimeSnapshotV1) (string, error) {
	safe, err := SanitizePreparedSnapshot(selection, snapshot)
	if err != nil {
		return "", err
	}
	expectedInventory, _, err := selection.selectedInventory()
	if err != nil {
		return "", err
	}
	expectedSafe, err := SanitizePreparedSnapshot(selection, expectedInventory)
	if err != nil {
		return "", err
	}
	for _, operation := range selection.additionalNodeOperations() {
		raw, present := fieldValue(safe.Entries)[operation.Address]
		if !present {
			return "Backend did not deliver its admitted portable node completion.", nil
		}
		matches, err := preparedEntryPayloadsEqual(fieldValue(expectedSafe.Entries)[operation.Address], raw)
		if err != nil {
			return "", err
		}
		if !matches {
			return "Backend did not deliver its admitted portable node completion.", nil
		}
	}
	return "", nil
}

func preparedEntryPayloadsEqual(expectedRaw, actualRaw []byte) (bool, error) {
	var expected, actual snapshotEntry
	if json.Unmarshal(expectedRaw, &expected) != nil || json.Unmarshal(actualRaw, &actual) != nil {
		return false, invalidPlan()
	}
	before, err := preparedPayload(expected.Payload)
	if err != nil {
		return false, err
	}
	after, err := preparedPayload(actual.Payload)
	if err != nil {
		return false, err
	}
	return preparedJSONEqual(before, after), nil
}
func (selection *preparedSelection) additionalNodeOperations() []planOperation {
	authored := map[string]bool{}
	for _, operation := range selection.original.operations[termProvisioning] {
		authored[operation.Address] = true
	}
	result := []planOperation{}
	for _, operation := range selection.operations {
		if !authored[operation.Address] && operation.Action != termDelete && (operation.Kind == termNode || operation.Kind == termNetwork) {
			result = append(result, operation)
		}
	}
	return result
}

// SanitizePreparedSnapshot returns a copied disclosure projection for additional
// portable nodes selected under the original collection authority.
func SanitizePreparedSnapshot(input PreparedSelection, snapshot binding.RuntimeSnapshotV1) (binding.RuntimeSnapshotV1, error) {
	selection, err := nativePreparedSelection(input)
	if err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	if err := admission.CheckPreparedSnapshot(snapshot); err != nil {
		return binding.RuntimeSnapshotV1{}, err
	}
	selected := []string{}
	for _, operation := range selection.additionalNodeOperations() {
		selected = append(selected, operation.Address)
	}
	return realization.SanitizePreparedNodeSnapshot(selected, snapshot)
}
