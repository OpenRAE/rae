package admission

import (
	"encoding/json"
	"math/big"
	"strings"
)

// Numeric predicates reuse the scalar recorder's reference bounds. The source
// owner performs coercion; this boundary receives constructed JSON scalars.
func sdlNumberOperation(operation string) bool {
	parts := strings.Split(operation, ":")
	if len(parts) != 3 || (parts[0] != termInteger && parts[0] != typeNumber) || parts[1] == "" && parts[2] == "" {
		return false
	}
	var bounds [2]*big.Rat
	for i, bound := range parts[1:] {
		if bound == "" {
			continue
		}
		n, valid := number(json.Number(bound))
		if !valid || parts[0] == termInteger && !n.IsInt() {
			return false
		}
		bounds[i] = n
	}
	return bounds[0] == nil || bounds[1] == nil || bounds[0].Cmp(bounds[1]) <= 0
}

func sdlNumberField(value any, operation string) bool {
	if !sdlNumberOperation(operation) {
		return false
	}
	if variableRef(text(value)) {
		return true
	}
	n, valid := number(value)
	if !valid {
		return false
	}
	parts := strings.Split(operation, ":")
	raw, numeric := value.(json.Number)
	if parts[0] == termInteger && (!numeric || !n.IsInt() || strings.ContainsAny(raw.String(), ".eE")) {
		return false
	}
	if parts[1] != "" {
		minimum, _ := number(json.Number(parts[1]))
		if n.Cmp(minimum) < 0 {
			return false
		}
	}
	if parts[2] != "" {
		maximum, _ := number(json.Number(parts[2]))
		if n.Cmp(maximum) > 0 {
			return false
		}
	}
	return true
}
