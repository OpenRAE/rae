package governance

import (
	"encoding/json"
	"errors"
	"math"
	"math/big"
	"strconv"

	"go.yaml.in/yaml/v3"
)

// mapping retains non-text keys: safe_load permits hashable scalar keys.
type mapping struct {
	keys   []any
	values map[any]any
}

func newMapping() *mapping { return &mapping{values: map[any]any{}} }
func (m *mapping) get(key any) any {
	if m == nil {
		return nil
	}
	return m.values[yamlKey(key)]
}
func (m *mapping) set(key, value any) {
	index := yamlKey(key)
	if _, exists := m.values[index]; !exists {
		m.keys = append(m.keys, key)
	}
	m.values[index] = value
}
func (m *mapping) has(key any) bool {
	if m == nil {
		return false
	}
	_, exists := m.values[yamlKey(key)]
	return exists
}

func yamlKey(value any) any {
	switch v := value.(type) {
	case bool:
		if v {
			return json.Number("1")
		}
		return json.Number("0")
	case float64:
		if math.IsNaN(v) {
			return yamlNaNKey{}
		}
		if !math.IsInf(v, 0) && !math.IsNaN(v) && math.Trunc(v) == v {
			return json.Number(new(big.Rat).SetFloat64(v).Num().String())
		}
	}
	return value
}

type yamlSet struct{ items *mapping }
type yamlTuple []any
type yamlNaNKey struct{}

type yamlSyntaxError struct{ cause error }

// The locked reference's repository loader admits 491 nested sequences under
// a mapping and refuses the next one. Requirement metadata has its own bound.
const yamlConstructionDepth = 492

func (e *yamlSyntaxError) Error() string { return e.cause.Error() }
func (e *yamlSyntaxError) Unwrap() error { return e.cause }

func (m *mapping) size() int {
	if m == nil {
		return 0
	}
	return len(m.keys)
}

func yamlValue(data []byte, emptyMapping bool) (any, error) {
	node, err := yamlDocument(data)
	if err != nil {
		return nil, &yamlSyntaxError{err}
	}
	value, err := constructYAML(node, map[*yaml.Node]any{}, 0)
	if err == nil && emptyMapping && !truth(value) {
		value = newMapping()
	}
	return value, err
}

func constructYAML(node *yaml.Node, memo map[*yaml.Node]any, depth int) (any, error) {
	if value, exists := memo[node]; exists {
		return value, nil
	}
	if depth > yamlConstructionDepth {
		return nil, errors.New("YAML exceeds constructor depth")
	}
	switch node.Kind {
	case 0:
		return nil, nil //nolint:nilnil // An empty YAML document constructs the null value.
	case yaml.DocumentNode:
		return constructYAML(node.Content[0], memo, depth)
	case yaml.AliasNode:
		return constructYAML(node.Alias, memo, depth+1)
	case yaml.MappingNode:
		return constructYAMLMap(node, memo, depth)
	case yaml.SequenceNode:
		return constructYAMLSequence(node, memo, depth)
	case yaml.ScalarNode:
		return yamlScalar(node)
	default:
		return nil, errors.New("unknown YAML node")
	}
}

func constructYAMLMap(node *yaml.Node, memo map[*yaml.Node]any, depth int) (any, error) {
	if node.Tag != "!!map" && node.Tag != "!!set" {
		return nil, errors.New("YAML tag requires a different node kind")
	}
	out := newMapping()
	memo[node] = out
	result, err := constructMapping(node, memo, depth, out)
	if node.Tag == "!!set" {
		set := yamlSet{result}
		memo[node] = set
		return set, err
	}
	return result, err
}

func constructYAMLSequence(node *yaml.Node, memo map[*yaml.Node]any, depth int) (any, error) {
	if node.Tag == "!!omap" || node.Tag == "!!pairs" {
		return constructPairs(node, memo, depth)
	}
	if node.Tag != "!!seq" {
		return nil, errors.New("YAML tag requires a different node kind")
	}
	items := make([]any, len(node.Content))
	memo[node] = items
	for i, child := range node.Content {
		value, err := constructYAML(child, memo, depth+1)
		if err != nil {
			return nil, err
		}
		items[i] = value
	}
	return items, nil
}

func constructMapping(node *yaml.Node, memo map[*yaml.Node]any, depth int, out *mapping) (*mapping, error) {
	if err := flattenYAMLMap(node); err != nil {
		return nil, err
	}
	for i := 0; i < len(node.Content); i += 2 {
		key, err := constructYAMLKey(node.Content[i], memo, depth+1)
		if err != nil {
			return nil, err
		}
		value, err := constructYAML(node.Content[i+1], memo, depth+1)
		if err != nil {
			return nil, err
		}
		out.set(key, value)
	}
	return out, nil
}

func constructYAMLKey(node *yaml.Node, memo map[*yaml.Node]any, depth int) (any, error) {
	key, err := constructYAML(node, memo, depth)
	if err != nil || !yamlHashable(key) {
		return nil, errors.New("unhashable YAML key")
	}
	return key, nil
}

func yamlHashable(value any) bool {
	switch value.(type) {
	case *mapping, []any, yamlSet, yamlTuple:
		return false
	default:
		return true
	}
}

func truth(value any) bool {
	switch v := value.(type) {
	case nil:
		return false
	case bool:
		return v
	case string:
		return v != ""
	case []any:
		return len(v) != 0
	case *mapping:
		return v.size() != 0
	case yamlSet:
		return v.items.size() != 0
	case json.Number:
		f, err := strconv.ParseFloat(string(v), 64)
		return err != nil || f != 0
	case float64:
		return v != 0
	default:
		return true
	}
}
