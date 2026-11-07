package admission

import (
	_ "embed" // Required by go:embed for the packaged compatibility records.
	"encoding/json"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

//go:embed sdl-field-rules.json
var sdlFieldJSON string

func readSDLFieldRules() (map[string]map[string]string, error) {
	return decodeSDLFieldRules(sdlFieldJSON)
}
func decodeSDLFieldRules(raw string) (map[string]map[string]string, error) {
	var fields map[string]map[string]string
	if err := json.Unmarshal([]byte(raw), &fields); err != nil || len(fields) == 0 {
		return nil, fault.New(fault.Operational, codeContractCatalogInvalid, nil)
	}
	for name, model := range fields {
		if name == "" || len(model) == 0 {
			return nil, fault.New(fault.Operational, codeContractCatalogInvalid, nil)
		}
		for field, operation := range model {
			if field == "" || !sdlFieldOperation(operation) {
				return nil, fault.New(fault.Operational, codeContractCatalogInvalid, nil)
			}
		}
	}
	return fields, nil
}
func sdlFieldOperation(operation string) bool {
	for range 16 {
		_, inner, wrapped := sdlFieldWrapper(operation)
		if !wrapped {
			break
		}
		operation = inner
	}
	switch operation {
	case "portable", "qualified", "nonblank", "absolute-path", "contained-relative", "contained-mount", "unique-nonblank":
		return true
	default:
		return false
	}
}

func sdlFieldWrapper(operation string) (string, string, bool) {
	for _, wrapper := range []string{"optional-", "nullable-", "list-"} {
		if inner, found := strings.CutPrefix(operation, wrapper); found {
			return wrapper, inner, true
		}
	}
	return "", operation, false
}

func withSDLFieldRules(rules map[string]func(any) error, models map[string]map[string]string) map[string]func(any) error {
	for name, fields := range models {
		prior := rules[name]
		rules[name] = func(v any) error {
			for field, operation := range fields {
				value, present := object(v)[field]
				if present && !sdlFieldValue(value, operation) {
					return invalid()
				}
			}
			if prior != nil {
				return prior(v)
			}
			return nil
		}
	}
	return rules
}
func sdlFieldValue(value any, operation string) bool {
	if wrapper, inner, wrapped := sdlFieldWrapper(operation); wrapped {
		return sdlWrappedField(value, wrapper, inner)
	}
	switch operation {
	case "portable":
		return sdlSymbol.MatchString(text(value))
	case "qualified":
		return materializationQualified(text(value))
	case "nonblank":
		return !sdlBlank(text(value))
	case "unique-nonblank":
		return nonblankSDLValues(value)
	case "absolute-path":
		return absoluteSDLPath(text(value), false)
	case "contained-relative":
		return containedPath(text(value), false)
	case "contained-mount":
		return containedPath(text(value), true)
	default:
		return false
	}
}

func sdlWrappedField(value any, wrapper, operation string) bool {
	if wrapper == "nullable-" && value == nil || wrapper == "optional-" && (value == nil || value == "") {
		return true
	}
	if wrapper != "list-" {
		return sdlFieldValue(value, operation)
	}
	values, ok := value.([]any)
	if !ok {
		return false
	}
	for _, item := range values {
		if !sdlFieldValue(item, operation) {
			return false
		}
	}
	return true
}
