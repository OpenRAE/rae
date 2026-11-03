package validation

import (
	"bytes"
	"encoding/json"
	"maps"
	"slices"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/internal/base/fault"
	"github.com/OpenRAE/rae/implementations/go/internal/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

// Defaulted checks the original bounded input and returns a fresh JSON value
// with published default annotations applied. This is a digest-owner view,
// not model normalization or semantic admission. Families own serializer
// omissions. Output is bounded by MaxBytes, 64 levels and 100,000 visits.
func (v *Validator) Defaulted(id string, data []byte, limits ingress.Limits) (any, error) {
	original, err := v.parse(id, data, limits)
	if err != nil {
		return nil, err
	}
	return defaultedSchema(v.contracts[id].schema, original, limits)
}

func defaultedSchema(schema *jsonschema.Schema, original any, limits ingress.Limits) (any, error) {
	encoded, err := json.Marshal(original)
	if err != nil {
		return nil, failure(fault.InvalidInput, "contract-defaults-limit")
	}
	if len(encoded) > limits.MaxBytes {
		return nil, failure(fault.InvalidInput, "contract-defaults-limit")
	}
	target, err := copyJSON(encoded)
	if err != nil {
		return nil, err
	}
	depth := 64
	if limits.MaxDepth > 0 {
		depth = min(depth, limits.MaxDepth)
	}
	state := defaultWalk{target: target, remaining: limits.MaxBytes - len(encoded), depth: depth, assigned: map[string][]byte{}}
	if err := state.walk(visit{schema, original, ""}); err != nil {
		return nil, err
	}
	if err := schema.Validate(target); err != nil {
		return nil, failure(fault.Operational, "contract-default-invalid")
	}
	return target, nil
}

type defaultWalk struct {
	target           any
	remaining, depth int
	assigned         map[string][]byte
}

func copyJSON(encoded []byte) (any, error) {
	decoder := json.NewDecoder(bytes.NewReader(encoded))
	decoder.UseNumber()
	var copyValue any
	if err := decoder.Decode(&copyValue); err != nil {
		return nil, failure(fault.Operational, "contract-default-invalid")
	}
	return copyValue, nil
}

func (w *defaultWalk) walk(root visit) error {
	stack := []visit{root}
	seen := map[visitIdentity]bool{}
	for work := 0; len(stack) > 0; work++ {
		if work >= 100000 {
			return failure(fault.InvalidInput, "contract-defaults-limit")
		}
		current := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		if strings.Count(current.path, "/") > w.depth {
			return failure(fault.InvalidInput, "contract-defaults-limit")
		}
		identity := visitIdentity{current.schema, current.path}
		if seen[identity] {
			continue
		}
		seen[identity] = true
		additional, err := w.addDefaults(current)
		if err != nil {
			return err
		}
		stack = append(stack, additional...)
		stack = append(stack, applicable(current)...)
	}
	return nil
}

func (w *defaultWalk) addDefaults(current visit) ([]visit, error) {
	original, ok := current.value.(map[string]any)
	if !ok {
		return nil, nil
	}
	resolved, ok := atDefaultPath(w.target, current.path)
	if !ok {
		return nil, failure(fault.Operational, "contract-default-invalid")
	}
	target, ok := resolved.(map[string]any)
	if !ok {
		return nil, failure(fault.Operational, "contract-default-invalid")
	}
	var additional []visit
	for _, name := range slices.Sorted(maps.Keys(current.schema.Properties)) {
		property := current.schema.Properties[name]
		if _, present := original[name]; present || property.Default == nil {
			continue
		}
		path := current.path + "/" + escape(name)
		copyValue, err := w.addMember(path, name, *property.Default, target)
		if err != nil {
			return nil, err
		}
		additional = append(additional, visit{property, copyValue, path})
	}
	return additional, nil
}

func (w *defaultWalk) addMember(path, name string, value any, target map[string]any) (any, error) {
	encoded, err := json.Marshal(value)
	if err != nil {
		return nil, failure(fault.Operational, "contract-default-invalid")
	}
	if previous, assigned := w.assigned[path]; assigned && !bytes.Equal(previous, encoded) {
		return nil, failure(fault.Operational, "contract-default-conflict")
	}
	w.assigned[path] = encoded
	if _, present := target[name]; !present {
		if len(encoded)+6*len(name)+4 > w.remaining {
			return nil, failure(fault.InvalidInput, "contract-defaults-limit")
		}
		w.remaining -= len(encoded) + 6*len(name) + 4
		target[name], err = copyJSON(encoded)
		if err != nil {
			return nil, err
		}
	}
	return copyJSON(encoded)
}

func atDefaultPath(root any, path string) (any, bool) {
	current := root
	for _, token := range jsonpointer.Tokens(path) {
		switch value := current.(type) {
		case map[string]any:
			var present bool
			current, present = value[token]
			if !present {
				return nil, false
			}
		case []any:
			index, ok := jsonpointer.ArrayIndex(token, len(value))
			if !ok {
				return nil, false
			}
			current = value[index]
		default:
			return nil, false
		}
	}
	return current, true
}
