package governance

import (
	"encoding/json"
	"math"
	"strconv"
)

const repoPolicyConfig = "tools/policy/adr_policy.yaml"

type policyJSONBridge struct {
	active map[any]bool
	memo   map[any]any
}

func loadRepositoryPolicy(r *repository) (*mapping, map[string]any, []Finding) {
	malformed := func(message string) []Finding {
		return []Finding{finding("policy-config-malformed", message, repoPolicyConfig)}
	}
	text, err := r.text(repoPolicyConfig)
	if err != nil {
		return nil, nil, malformed(repoPolicyConfig + " could not be parsed (missing or invalid YAML)")
	}
	value, err := yamlValue([]byte(text), true)
	if err != nil {
		return nil, nil, malformed(repoPolicyConfig + " could not be parsed (missing or invalid YAML)")
	}
	policy := object(value)
	if policy == nil {
		return nil, nil, malformed(repoPolicyConfig + " root must be a YAML mapping; got " + pythonType(value))
	}
	bridge := policyJSONBridge{active: map[any]bool{}, memo: map[any]any{}}
	normalized, ok := bridge.value(policy, 0)
	if !ok {
		return nil, nil, malformed(repoPolicyConfig + " must contain only JSON data")
	}
	transport, ok := normalized.(map[string]any)
	if !ok {
		return nil, nil, malformed(repoPolicyConfig + " must contain only JSON data")
	}
	return policy, transport, []Finding{}
}

// This is the legacy json.dumps(sort_keys=True) boundary. It deliberately
// allows non-finite values here; the separate Conftest input boundary refuses
// their JSON transport only when an evaluation actually runs.
func (b *policyJSONBridge) value(value any, depth int) (any, bool) {
	if depth > 1000 {
		return nil, false
	}
	switch value := value.(type) {
	case nil, bool, string, json.Number, float64:
		return value, true
	case *mapping:
		return b.mapping(value, depth)
	case []any:
		return b.sequence(value, depth)
	default:
		return nil, false
	}
}
func (b *policyJSONBridge) mapping(value *mapping, depth int) (any, bool) {
	if b.active[value] {
		return nil, false
	}
	if previous, exists := b.memo[value]; exists {
		return previous, true
	}
	b.active[value] = true
	defer delete(b.active, value)
	result := map[string]any{}
	b.memo[value] = result
	group := ""
	for _, key := range value.keys {
		name, kind, ok := policyJSONKey(key)
		if !ok || group != "" && group != kind {
			return nil, false
		}
		group = kind
		normalized, ok := b.value(value.get(key), depth+1)
		if !ok {
			return nil, false
		}
		result[name] = normalized
	}
	return result, true
}
func (b *policyJSONBridge) sequence(value []any, depth int) (any, bool) {
	if len(value) == 0 {
		return []any{}, true
	}
	id := &value[0]
	if b.active[id] {
		return nil, false
	}
	if previous, exists := b.memo[id]; exists {
		return previous, true
	}
	b.active[id] = true
	defer delete(b.active, id)
	result := make([]any, len(value))
	b.memo[id] = result
	for i, item := range value {
		normalized, ok := b.value(item, depth+1)
		if !ok {
			return nil, false
		}
		result[i] = normalized
	}
	return result, true
}
func policyJSONKey(value any) (string, string, bool) {
	switch value := value.(type) {
	case string:
		return value, "text", true
	case nil:
		return nullLiteral, nullLiteral, true
	case bool:
		return strconv.FormatBool(value), numberKind, true
	case json.Number:
		return string(value), numberKind, true
	case float64:
		switch {
		case math.IsNaN(value):
			return "NaN", numberKind, true
		case math.IsInf(value, 1):
			return "Infinity", numberKind, true
		case math.IsInf(value, -1):
			return "-Infinity", numberKind, true
		}
		return pythonFloat(value), numberKind, true
	default:
		return "", "", false
	}
}
