package realization

import "strings"

// Restore value-free markers only for native SDL construction. The validated
// markers are overlaid after construction; they never become raw values.
func restoreRuntimeMarkers(value any) (any, error) {
	switch input := value.(type) {
	case []any:
		result := make([]any, len(input))
		for i, item := range input {
			restored, err := restoreRuntimeMarkers(item)
			if err != nil {
				return nil, err
			}
			result[i] = restored
		}
		return result, nil
	case map[string]any:
		return restoreRuntimeRecord(input)
	default:
		return value, nil
	}
}
func restoreRuntimeRecord(input map[string]any) (map[string]any, error) {
	_, sourceMarker := input[termSourcePresent]
	_, optionsMarker := input[termOptionsPresent]
	if sourceMarker || optionsMarker {
		return restoreRuntimeMount(input)
	}
	result := map[string]any{}
	for key, item := range input {
		if runtimeMarker(key) {
			continue
		}
		restored, err := restoreRuntimeMarkers(item)
		if err != nil {
			return nil, err
		}
		result[key] = restored
	}
	for key, item := range input {
		if err := restoreRuntimeMarker(result, input, key, item); err != nil {
			return nil, err
		}
	}
	return result, nil
}
func runtimeMarker(key string) bool {
	return strings.HasSuffix(key, "_present") || strings.HasSuffix(key, "_commitment")
}
func restoreRuntimeMount(input map[string]any) (map[string]any, error) {
	if err := validateMountObservation([]any{input}); err != nil {
		return nil, err
	}
	result := map[string]any{}
	for key, item := range input {
		if key != termSourcePresent && key != termOptionsPresent {
			result[key] = item
		}
	}
	return result, nil
}
func restoreRuntimeMarker(result, input map[string]any, key string, item any) error {
	if field, presentMarker := strings.CutSuffix(key, "_present"); presentMarker {
		if field != termValue && field != termValues && field != termBindSource {
			return invalidRealization()
		}
		present, ok := item.(bool)
		if !ok {
			return invalidRealization()
		}
		if commitment := input[field+"_commitment"]; commitment != nil && (!present || !validCommitment(commitment)) {
			return invalidRealization()
		}
		result[field] = ""
		if field == termValues {
			result[field] = []any{}
		}
	}
	if field, commitmentMarker := strings.CutSuffix(key, "_commitment"); commitmentMarker {
		if _, present := input[field+"_present"]; !present {
			return invalidRealization()
		}
	}
	return nil
}

func overlayRuntimeMarkers(normalized, original any) (any, error) {
	switch output := normalized.(type) {
	case map[string]any:
		if err := overlayRuntimeRecord(output, original); err != nil {
			return nil, err
		}
	case []any:
		if err := overlayRuntimeSequence(output, original); err != nil {
			return nil, err
		}
	}
	return normalized, nil
}
func overlayRuntimeRecord(output map[string]any, original any) error {
	input, ok := original.(map[string]any)
	if !ok {
		return nil
	}
	for key, item := range input {
		if runtimeMarker(key) {
			output[key] = item
			continue
		}
		current, present := output[key]
		if !present {
			continue
		}
		overlaid, err := overlayRuntimeMarkers(current, item)
		if err != nil {
			return err
		}
		output[key] = overlaid
	}
	return nil
}
func overlayRuntimeSequence(output []any, original any) error {
	input, ok := original.([]any)
	if !ok {
		return nil
	}
	if len(input) != len(output) {
		return invalidRealization()
	}
	for i, item := range output {
		overlaid, err := overlayRuntimeMarkers(item, input[i])
		if err != nil {
			return err
		}
		output[i] = overlaid
	}
	return nil
}
