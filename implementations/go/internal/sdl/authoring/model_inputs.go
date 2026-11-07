package authoring

import (
	"encoding/json"
	"maps"
	"regexp"
	"strconv"
)

var permissionMode = regexp.MustCompile(`^(0o)?[0-7]{3,4}$`)

// These conversions change model shape before the published schema applies.
func structuredInput(model, name string, value any) (any, error) {
	switch model + "/" + name {
	case "RuntimeFilesystemEntry/mode":
		return filesystemMode(value)
	case "Workflow/timeout":
		switch value.(type) {
		case string, json.Number, float64, bool:
			return map[string]any{"seconds": value}, nil
		}
	case "WorkflowTimeoutPolicy/seconds":
		return positiveDuration(value)
	case "WorkflowCompensationPolicy/order":
		if value == nil {
			return "reverse_completion", nil
		}
		return pythonScalar(value), nil
	case "RuntimeDatastoreService/templates":
		return manifestEntries(value, "template_id"), nil
	case "RuntimeDatastoreService/mappings":
		return manifestEntries(value, "mapping_id"), nil
	case "OutcomeInterpretationRule/participant_scope":
		if s, ok := value.(string); ok {
			return lower(pythonTrim(s)), nil
		}
	case "AlternativeVariationPoint/target":
		if target := object(value); target != nil {
			if _, present := target["kind"]; !present {
				inferred := maps.Clone(target)
				inferred["kind"] = "reference"
				return inferred, nil
			}
		}
	}
	return value, nil
}

func omitInferredTarget(pointer, name string, original, normalized any) any {
	if pointer != "#/$defs/AlternativeVariationPoint" || name != "target" || object(original) == nil {
		return normalized
	}
	if _, present := object(original)["kind"]; present {
		return normalized
	}
	if fields, ok := normalized.(ordered); ok {
		for i := range fields {
			if fields[i].name == "kind" {
				fields[i].omit = true
			}
		}
	}
	return normalized
}

func filesystemMode(value any) (any, error) {
	if value == nil || value == "" || variable(value) {
		return value, nil
	}
	if number, ok := value.(json.Number); ok {
		n, err := strconv.ParseUint(number.String(), 10, 12)
		if err != nil {
			return nil, invalid()
		}
		mode := strconv.FormatUint(n, 8)
		return "0000"[:4-len(mode)] + mode, nil
	}
	if mode, ok := value.(string); ok && permissionMode.MatchString(pythonTrim(mode)) {
		return pythonTrim(mode), nil
	}
	return nil, invalid()
}

func positiveDuration(value any) (any, error) {
	parsed, err := duration(value)
	if err != nil {
		return nil, err
	}
	if n, ok := parsed.(json.Number); ok && n == "0" {
		return nil, invalid()
	}
	return parsed, nil
}

func manifestEntries(value any, id string) any {
	if name, ok := value.(string); ok {
		return []any{map[string]any{id: name, nameField: name}}
	}
	if rows, ok := value.([]any); ok {
		result := make([]any, len(rows))
		for i, row := range rows {
			if name, ok := row.(string); ok {
				row = map[string]any{id: name, nameField: name}
			}
			result[i] = row
		}
		return result
	}
	return value
}
