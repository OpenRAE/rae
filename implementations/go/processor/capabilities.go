package processor

import (
	"bytes"
	"encoding/json"
	"strings"
)

// Kind identifies the exact JSON scalar category retained by compilation.
func (value Scalar) Kind() string { return value.kind }

// Value returns an immutable string, boolean or exact JSON number.
func (value Scalar) Value() any { return value.value }

// MarshalJSON preserves the admitted scalar kind and value.
func (value Scalar) MarshalJSON() ([]byte, error) {
	if value.kind == "" {
		return nil, invalidCompiled()
	}
	return json.Marshal(value.value)
}
func compiledScalar(raw json.RawMessage) (Scalar, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	var value any
	if err := decoder.Decode(&value); err != nil {
		return Scalar{}, invalidCompiled()
	}
	var kind string
	switch v := value.(type) {
	case string:
		kind = "string"
	case bool:
		kind = "boolean"
	case json.Number:
		kind = "integer"
		if strings.ContainsAny(string(v), ".eE") {
			kind = "number"
		}
	default:
		return Scalar{}, invalidCompiled()
	}
	return Scalar{kind: kind, value: value}, nil
}
func (state *compilerState) compileCapabilityConstraints() {
	provenance, present := state.input.model.InstantiationProvenance.Value()
	if !present {
		return
	}
	result := []CapabilityConstraint{}
	for _, source := range fieldValue(provenance.CapabilityConstraints) {
		parts := strings.Split(fieldValue(source.FieldPointer), "/")
		// Nested process-limit domains belong to realization's semantic identities.
		if len(parts) != 4 {
			continue
		}
		node := strings.ReplaceAll(strings.ReplaceAll(parts[2], "~1", "/"), "~0", "~")
		constraint := CapabilityConstraint{Address: state.nodeAddress(node), Concern: parts[1] + "." + parts[3], Parameter: fieldValue(source.Parameter), AllowedValues: []Scalar{}}
		for _, raw := range fieldValue(source.AllowedValues) {
			value, err := compiledScalar(raw)
			if err != nil {
				state.err = err
				return
			}
			constraint.AllowedValues = append(constraint.AllowedValues, value)
		}
		result = append(result, constraint)
	}
	state.model.CapabilityConstraints = result
}
