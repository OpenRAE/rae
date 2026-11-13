package realization

import (
	"slices"
	"strings"
)

func stringSequence(value any) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	result := slices.Clone(items)
	for _, item := range result {
		if _, ok := item.(string); !ok {
			return nil, invalidRealization()
		}
	}
	return result, nil
}
func scalarSet(values []any) []any {
	result := make([]any, len(values))
	for i, value := range values {
		result[i] = map[string]any{termIdentityMarker: value, termValue: value}
	}
	return result
}

func projectMounts(value any, includeStateful, recursive bool) ([]any, error) {
	items, ok := value.([]any)
	if !ok {
		return nil, invalidRealization()
	}
	output := []any{}
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, invalidRealization()
		}
		kind, _ := record["source_kind"].(string)
		if !includeStateful && kind != termBind && kind != termTmpfs {
			continue
		}
		projected, err := projectMountRecord(record, recursive)
		if err != nil {
			return nil, err
		}
		output = append(output, projected)
	}
	if !recursive {
		slices.SortStableFunc(output, func(a, b any) int {
			return strings.Compare(ownedProjection[string](ownedProjection[map[string]any](a)[termTarget]), ownedProjection[string](ownedProjection[map[string]any](b)[termTarget]))
		})
	}
	return output, nil
}

func projectMountRecord(record map[string]any, recursive bool) (map[string]any, error) {
	target, ok := record[termTarget].(string)
	if !ok || target == "" {
		return nil, invalidRealization()
	}
	source, ok := fieldDefault(record, termSource, "").(string)
	if !ok {
		return nil, invalidRealization()
	}
	sourceProtected, err := protectedClassification(fieldDefault(record, "source_sensitivity", termUnknown))
	if err != nil || sourceProtected && source != "" {
		return nil, invalidRealization()
	}
	options, err := stringSequence(fieldDefault(record, termOptions, []any{}))
	if err != nil {
		return nil, err
	}
	optionsProtected, err := protectedClassification(fieldDefault(record, "options_sensitivity", termUnknown))
	if err != nil || optionsProtected && len(options) > 0 {
		return nil, invalidRealization()
	}
	optionsPresent := len(options) > 0 || optionsProtected
	if recursive {
		options = scalarSet(options)
	} else {
		slices.SortStableFunc(options, func(a, b any) int { return strings.Compare(ownedProjection[string](a), ownedProjection[string](b)) })
	}
	return map[string]any{termTarget: target, termSource: source, termSourcePresent: source != "" || sourceProtected, "source_sensitivity": fieldDefault(record, "source_sensitivity", termUnknown), "source_kind": record["source_kind"], "filesystem_type": fieldDefault(record, "filesystem_type", ""), "read_only": fieldDefault(record, "read_only", false), termOptions: options, termOptionsPresent: optionsPresent, "options_sensitivity": fieldDefault(record, "options_sensitivity", termUnknown), "propagation": fieldDefault(record, "propagation", termUnknown), "stability": fieldDefault(record, "stability", termUnknown), "backend_generated": record["backend_generated"]}, nil
}

func validateMountObservation(value any) error {
	items, ok := value.([]any)
	if !ok {
		return invalidRealization()
	}
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return invalidRealization()
		}
		if err := validateObservedMount(record); err != nil {
			return err
		}
	}
	return nil
}

func mountObservationFields() []string {
	allowed := []string{termTarget, termSource, termSourcePresent, "source_sensitivity", "source_kind", "filesystem_type", "read_only", termOptions, termOptionsPresent, "options_sensitivity", "propagation", "stability", "backend_generated"}
	return allowed
}
func observedMountCandidate(record map[string]any) (map[string]any, bool, error) {
	allowed := mountObservationFields()
	_, sourceMarker := record[termSourcePresent]
	_, optionsMarker := record[termOptionsPresent]
	candidate := record
	if sourceMarker || optionsMarker {
		if len(record) != len(allowed) {
			return nil, false, invalidRealization()
		}
		candidate = map[string]any{}
		for _, key := range allowed {
			field, present := record[key]
			if !present {
				return nil, false, invalidRealization()
			}
			if key != termSourcePresent && key != termOptionsPresent {
				candidate[key] = field
			}
		}
	}
	return candidate, sourceMarker || optionsMarker, nil
}
func validateObservedMount(record map[string]any) error {
	candidate, marked, err := observedMountCandidate(record)
	if err != nil {
		return err
	}
	normalized, err := normalizeConcernValue(termRuntimeMounts, []any{candidate})
	if err != nil {
		return err
	}
	row := ownedProjection[map[string]any](ownedProjection[[]any](normalized)[0])
	kind, _ := row["source_kind"].(string)
	if !slices.Contains([]string{termBind, termTmpfs, "volume", "image"}, kind) {
		return invalidRealization()
	}
	if marked {
		return validateMountMarkers(record, row)
	}
	return nil
}
func validateMountMarkers(record, row map[string]any) error {
	for _, name := range []string{termSource, termOptions} {
		present, ok := record[name+"_present"].(bool)
		if !ok {
			return invalidRealization()
		}
		expected, err := mountMarkerExpected(row, name)
		if err != nil {
			return err
		}
		if present != expected {
			return invalidRealization()
		}
	}
	return nil
}

func mountMarkerExpected(row map[string]any, name string) (bool, error) {
	protected, err := protectedClassification(row[name+"_sensitivity"])
	if err != nil {
		return false, err
	}
	expected := protected
	if text, ok := row[name].(string); ok {
		expected = expected || text != ""
	} else if array, ok := row[name].([]any); ok {
		expected = expected || len(array) > 0
	} else {
		return false, invalidRealization()
	}
	return expected, nil
}
