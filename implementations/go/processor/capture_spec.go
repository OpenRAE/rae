package processor

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func captureSpecDemandValues(specs []binding.ExperimentCaptureSpecV1) ([]CaptureDemand, error) {
	ordered := slices.Clone(specs)
	slices.SortStableFunc(ordered, func(left, right binding.ExperimentCaptureSpecV1) int {
		if order := strings.Compare(fieldValue(left.CaptureSpecId), fieldValue(right.CaptureSpecId)); order != 0 {
			return order
		}
		return strings.Compare(fieldValue(left.SpecVersion), fieldValue(right.SpecVersion))
	})
	result := []CaptureDemand{}
	for _, spec := range ordered {
		demands, err := oneCaptureSpecDemands(spec)
		if err != nil {
			return nil, err
		}
		result = append(result, demands...)
	}
	return result, nil
}
func captureSpecWindows(input []json.RawMessage) (map[string]string, error) {
	result := map[string]string{}
	for _, raw := range input {
		var window struct {
			ID   string `json:"window_id"`
			Kind string `json:"window_kind"`
		}
		if json.Unmarshal(raw, &window) != nil || window.ID == "" || result[window.ID] != "" {
			return nil, invalidCompiled()
		}
		result[window.ID] = window.Kind
	}
	return result, nil
}
func selectedCaptureWindows(refs []string, windows map[string]string) ([]string, error) {
	result := make([]string, 0, len(refs))
	for _, ref := range refs {
		kind, present := windows[ref]
		if !present {
			return nil, invalidCompiled()
		}
		result = append(result, kind)
	}
	slices.Sort(result)
	return slices.Compact(result), nil
}
func captureOptionalText(raw json.RawMessage) (*string, error) {
	if len(raw) == 0 {
		return nil, nil //nolint:nilnil // Absence is a valid nullable capture policy.
	}
	var result *string
	if json.Unmarshal(raw, &result) != nil {
		return nil, invalidCompiled()
	}
	return result, nil
}
func oneCaptureSpecDemands(spec binding.ExperimentCaptureSpecV1) ([]CaptureDemand, error) {
	windows, err := captureSpecWindows(fieldValue(spec.CaptureWindows))
	if err != nil {
		return nil, err
	}
	requirements := fieldValue(spec.CaptureRequirements)
	names := make([]string, 0, len(requirements))
	for name := range requirements {
		names = append(names, name)
	}
	slices.Sort(names)
	result := make([]CaptureDemand, 0, len(names))
	for _, name := range names {
		requirement := requirements[name]
		kinds, err := selectedCaptureWindows(fieldValue(requirement.WindowRefs), windows)
		if err != nil {
			return nil, err
		}
		redaction, err := captureOptionalText(fieldValue(requirement.RedactionPolicy))
		if err != nil {
			return nil, err
		}
		retention, err := captureOptionalText(fieldValue(requirement.RetentionPolicy))
		if err != nil {
			return nil, err
		}
		disclosure := "full"
		if redaction != nil || fieldValue(requirement.Sensitivity) == termRedacted {
			disclosure = termRedacted
		}
		policies := []string{}
		if retention != nil {
			policies = append(policies, *retention)
		}
		result = append(result, CaptureDemand{
			DemandID: fieldValue(requirement.RequirementId), Address: "capture_specs." + fieldValue(spec.CaptureSpecId) + ".capture_requirements." + name,
			OutputContract: fieldValue(requirement.OutputContract), FieldSelectors: nonNilStrings(fieldValue(requirement.FieldSelectors)),
			ArtifactRoles: nonNilStrings(fieldValue(requirement.RequiredArtifactRoles)), MediaTypes: nonNilStrings(fieldValue(requirement.ExpectedMediaTypes)),
			CaptureKind: fieldValue(requirement.CaptureKind), SourceClasses: []string{}, SourceRefs: []string{}, Scopes: []string{fieldValue(requirement.CaptureScope)}, ScopeRefs: []string{},
			ChannelKinds: []string{}, ChannelRefs: []string{fieldValue(fieldValue(requirement.ChannelRef).RefId)}, WindowKinds: kinds,
			IntegrityModes: nonNilStrings(fieldValue(requirement.IntegrityRequirements)), Sensitivity: fieldValue(requirement.Sensitivity), Disclosure: disclosure,
			RetentionPolicyRefs: policies, ExportPolicy: "not-required", RedactionPolicy: redaction,
		})
	}
	return result, nil
}
