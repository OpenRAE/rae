package admission

import (
	"encoding/json"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/base/canonjson"
)

func constraintSource(v any) error {
	id := stringAt(v, "source_id")
	if strings.HasPrefix(id, "/") || strings.HasPrefix(id, "\\") {
		return invalid()
	}
	if len(id) >= 3 && (id[0] >= 'A' && id[0] <= 'Z' || id[0] >= 'a' && id[0] <= 'z') && id[1] == ':' && (id[2] == '/' || id[2] == '\\') {
		return invalid()
	}
	if slices.Contains(strings.Split(strings.ReplaceAll(id, "\\", "/"), "/"), "..") {
		return invalid()
	}
	return nil
}

func constraintScalarKey(v any) (string, error) {
	raw, err := json.Marshal(v)
	if err != nil {
		return "", invalid()
	}
	canonical, err := canonjson.JCS(raw)
	if err != nil {
		return "", invalid()
	}
	return string(canonical), nil
}

func constraintValues(values any, kind string) (map[string]bool, error) {
	keys := map[string]bool{}
	previous := ""
	for index, value := range array(values) {
		if kind != "" && !scalarMatches(value, kind) {
			return nil, invalid()
		}
		key, err := constraintScalarKey(value)
		if err != nil || index > 0 && key <= previous {
			return nil, invalid()
		}
		keys[key] = true
		previous = key
	}
	return keys, nil
}

func constraintGraph(v any) error {
	if !orderedRows(at(v, "symbols"), "symbol_id") || !orderedRows(at(v, "clauses"), "clause_id") {
		return invalid()
	}
	symbols := map[string]map[string]bool{}
	for _, symbol := range array(at(v, "symbols")) {
		domain, err := constraintValues(at(symbol, "domain"), stringAt(symbol, "sort"))
		if err != nil {
			return err
		}
		symbols[stringAt(symbol, "symbol_id")] = domain
	}
	for _, clause := range array(at(v, "clauses")) {
		domain := symbols[stringAt(clause, "symbol_id")]
		values, err := constraintValues(at(clause, "allowed_values"), "")
		if err != nil || domain == nil || !equalSubset(values, domain) {
			return invalid()
		}
	}
	return nil
}

func equalSubset(values, domain map[string]bool) bool {
	for key := range values {
		if !domain[key] {
			return false
		}
	}
	return true
}
