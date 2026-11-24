package realization

import (
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type plannedConcernKey struct{ address, kind string }
type expectedPlannedConcern struct {
	key     plannedConcernKey
	pointer string
}

func (s *evaluationState) plannedDiagnostics() ([]diagnostic.Diagnostic, error) {
	finding := s.plannedInventoryFinding()
	var err error
	if finding == nil {
		finding, err = s.plannedBindingFinding()
	}
	if err != nil {
		return nil, err
	}
	if finding == nil {
		finding, err = s.plannedSelectionFinding()
	}
	if err != nil {
		return nil, err
	}
	if finding == nil && s.options.Manifest != nil {
		finding, err = s.plannedManifestFinding()
	}
	if err != nil {
		return nil, err
	}
	if finding != nil {
		return []diagnostic.Diagnostic{*finding}, nil
	}
	return []diagnostic.Diagnostic{}, nil
}

func expectedPlannedConcerns(operation evaluatedOperation) []expectedPlannedConcern {
	if operation.Action == termDelete {
		return nil
	}
	result := []expectedPlannedConcern{}
	for _, definition := range applicablePlannedDefinitions(operation.ResourceType) {
		applies := definition.section == termNodes && (operation.ResourceType == termNode || operation.ResourceType == termNetwork) || definition.section == termContent && operation.ResourceType == termContentPlacement
		if !applies || !plannedIncludesConcern(operation.Payload, definition) {
			continue
		}
		result = append(result, expectedPlannedConcern{plannedConcernKey{operation.Address, definition.kind}, jsonpointer.FromTokens(definition.payload)})
	}
	for _, kind := range derivedPlannedConcernKinds(operation) {
		result = append(result, expectedPlannedConcern{plannedConcernKey{operation.Address, kind}, jsonpointer.FromTokens(derivedConcernPayload(kind))})
	}
	return result
}
func derivedPlannedConcernKinds(operation evaluatedOperation) []string {
	result := []string{}
	if operation.Payload["domain_topology"] != nil {
		result = append(result, "domain-topology")
	}
	switch operation.ResourceType {
	case termGeneratedArtifact, termPersistentVolume:
		result = append(result, operation.ResourceType)
	case termContentPlacement:
		if binding, ok := operation.Payload["service_materialization"].(map[string]any); ok {
			kind := termServiceContentMaterialization
			if binding["interface_profile"] == "service-search-index-schema" {
				kind = termServiceSearchIndexSchemaMaterialization
			}
			result = append(result, kind)
		}
	}
	return result
}
func applicablePlannedDefinitions(resourceType string) []concernDefinition {
	if resourceType == termNode || resourceType == termNetwork || resourceType == termContentPlacement {
		return concernDefinitions
	}
	return nil
}

func plannedIncludesConcern(payload map[string]any, definition concernDefinition) bool {
	if !definition.nonStatefulMountsOnly {
		return true
	}
	value, present := payloadConcern(payload, definition.payload)
	rows, sequence := value.([]any)
	if !present || !sequence || len(rows) == 0 {
		return true
	}
	for _, input := range rows {
		if row, ok := input.(map[string]any); ok && (row["source_kind"] == "bind" || row["source_kind"] == "tmpfs") {
			return true
		}
	}
	return false
}

func (s *evaluationState) plannedInventoryFinding() *diagnostic.Diagnostic {
	actual := map[plannedConcernKey]plannedAuthority{}
	for _, authority := range s.plan.Authority {
		actual[plannedConcernKey{authority.Address, authority.Kind}] = authority
	}
	expected, finding := s.plannedExpectedInventory(actual)
	if finding != nil {
		return finding
	}
	if finding = plannedExcessFinding(expected, actual); finding != nil {
		return finding
	}
	for _, operation := range s.plan.Operations {
		for _, row := range expectedPlannedConcerns(operation) {
			authority := actual[row.key]
			if authority.Pointer != row.pointer {
				return plannedFailure(authority, "realization.authority-payload-pointer-invalid", "Provisioning plan authority uses a non-canonical payload pointer for '"+authority.Kind+"'.")
			}
		}
	}
	return nil
}
func (s *evaluationState) plannedExpectedInventory(actual map[plannedConcernKey]plannedAuthority) (map[plannedConcernKey]string, *diagnostic.Diagnostic) {
	operations := slices.Clone(s.plan.Operations)
	slices.SortStableFunc(operations, func(a, b evaluatedOperation) int { return strings.Compare(a.Address, b.Address) })
	expected := map[plannedConcernKey]string{}
	for _, operation := range operations {
		rows := expectedPlannedConcerns(operation)
		slices.SortStableFunc(rows, func(a, b expectedPlannedConcern) int { return strings.Compare(a.key.kind, b.key.kind) })
		for _, row := range rows {
			if _, present := actual[row.key]; !present {
				return nil, &diagnostic.Diagnostic{Code: "realization.authority-incomplete", Domain: termRuntimeRealization, Address: row.key.address, Message: "Provisioning plan is missing resolved authority for '" + row.key.kind + "'.", Severity: termError}
			}
			expected[row.key] = row.pointer
		}
	}
	return expected, nil
}
func plannedExcessFinding(expected map[plannedConcernKey]string, actual map[plannedConcernKey]plannedAuthority) *diagnostic.Diagnostic {
	keys := make([]plannedConcernKey, 0, len(actual))
	for key := range actual {
		keys = append(keys, key)
	}
	slices.SortFunc(keys, func(a, b plannedConcernKey) int {
		if order := strings.Compare(a.address, b.address); order != 0 {
			return order
		}
		return strings.Compare(a.kind, b.kind)
	})
	for _, key := range keys {
		if _, present := expected[key]; !present {
			return &diagnostic.Diagnostic{Code: "realization.authority-excess", Domain: termRuntimeRealization, Address: key.address, Message: "Provisioning plan carries authority for inapplicable concern '" + key.kind + "'.", Severity: termError}
		}
	}
	return nil
}

func (s *evaluationState) plannedBindingFinding() (*diagnostic.Diagnostic, error) {
	for _, authority := range s.plan.Authority {
		if len(authority.Constraint) == 0 || string(authority.Constraint) == "null" {
			continue
		}
		valid, err := s.plannedSourceBindingValid(authority)
		if err != nil {
			return nil, err
		}
		if !valid {
			return plannedFailure(authority, "realization.authority-selection-invalid", "Recursive authority is not bound to the submitted source projection."), nil
		}
	}
	return nil, nil //nolint:nilnil // No binding finding is a valid optional result.
}

func (s *evaluationState) plannedSourceBindingValid(authority plannedAuthority) (bool, error) {
	constraint, err := plannedNativeFragment(authority.Constraint, admission.RealizationConstraint)
	if err != nil {
		return false, plannedUnexpected(err)
	}
	requirement := Requirement{Kind: authority.Kind, Constraint: constraint}
	selected := plannedPointerValue(s.operations[authority.Address].Payload, authority.Pointer)
	if missingValue(selected) {
		return false, nil
	}
	projected, err := projectEvaluationConcern(requirement, selected, false)
	if err != nil {
		return false, plannedUnexpected(err)
	}
	fragment, err := nativeValueFragment(projected)
	if err != nil {
		return false, err
	}
	binding, err := admission.RealizationConstraintBinding(requirement.Constraint, fragment)
	if err != nil {
		return false, plannedUnexpected(err)
	}
	if binding != authority.Binding {
		return false, nil
	}
	if authority.Mode == termOpen {
		return true, nil
	}
	admitted, err := constraintAdmitsValue(requirement.Constraint, projected)
	return admitted, plannedUnexpected(err)
}

func (s *evaluationState) plannedSelectionFinding() (*diagnostic.Diagnostic, error) {
	for _, authority := range s.plan.Authority {
		operation, live := s.operations[authority.Address]
		selected := any(missingConcern{})
		if live && operation.Action != termDelete {
			selected = plannedPointerValue(operation.Payload, authority.Pointer)
		}
		valid, err := plannedSelectionAdmitted(authority, selected)
		if err != nil {
			return nil, err
		}
		if !valid {
			return plannedFailure(authority, "realization.authority-selection-invalid", "Provisioning adapter cannot materialize a plan value outside resolved authority for '"+authority.Kind+"'."), nil
		}
	}
	return nil, nil //nolint:nilnil // No selection finding is a valid optional result.
}

func plannedSelectionAdmitted(authority plannedAuthority, selected any) (bool, error) {
	structure, err := plannedNativeFragment(authority.Structure, admission.RealizationStructure)
	if err != nil {
		return false, err
	}
	if structure != nil && (missingValue(selected) || !legacyStructureMatches(structure.Document(), selected, selected, 0)) {
		return false, nil
	}
	if missingValue(selected) {
		return true, nil
	}
	if authority.Mode == termClosed {
		return emptyPreparedConcern(selected) || authority.Kind == "runtime-restart-policy" && selected == "unknown", nil
	}
	if authority.Mode == termConstrained {
		return plannedBoundsAdmit(authority, selected)
	}
	return true, nil
}
func plannedBoundsAdmit(authority plannedAuthority, selected any) (bool, error) {
	lookup := plannedBoundLookup{input: selected}
	for _, bound := range authority.Bounds {
		if bound.Identity != "" && authority.Kind != termProcessResourceLimits {
			return false, nil
		}
		valid, err := lookup.admits(bound)
		if err != nil || !valid {
			return valid, err
		}
	}
	return true, nil
}

func (s *evaluationState) plannedManifestFinding() (*diagnostic.Diagnostic, error) {
	needsEnvelope := false
	for _, authority := range s.plan.Authority {
		needsEnvelope = needsEnvelope || authority.Mode == termOpen || authority.Mode == termConstrained
	}
	planned, err := plannedOptionalValue(s.plan.Envelope)
	if err != nil {
		return nil, err
	}
	selected, err := plannedOptionalValue(sourceValue(s.options.Manifest.RealizationEnvelope))
	if err != nil {
		return nil, err
	}
	if needsEnvelope && (planned == nil || selected == nil || !payloadEqual(planned, selected)) {
		return &diagnostic.Diagnostic{Code: "realization.authority-envelope-mismatch", Domain: termRuntimeRealization, Address: "runtime.realization-envelope", Message: "Provisioning plan authority was not admitted against the selected realization envelope.", Severity: termError}, nil
	}
	requirements, err := s.plannedRequirements()
	if err != nil {
		return plannedViewFailure(err, s.plan)
	}
	for _, requirement := range requirements {
		finding, supportErr := supportDiagnostic(requirement, ResolveOptions{Manifest: *s.options.Manifest, Envelope: s.options.Envelope})
		if supportErr != nil || finding != nil {
			return finding, supportErr
		}
	}
	constraints, err := s.plannedConstraintRequirements()
	if err != nil {
		return nil, err
	}
	findings, err := resolutionDiagnostics(constraints, ResolveOptions{Manifest: *s.options.Manifest, Envelope: s.options.Envelope})
	if err != nil {
		return nil, err
	}
	if len(findings) > 0 {
		return &findings[0], nil
	}
	return nil, nil //nolint:nilnil // No apparatus finding is a valid optional result.
}
