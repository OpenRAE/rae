package authoring

import (
	"bytes"
	"encoding/json"
	"fmt"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
)

type semanticString struct {
	path, value        string
	variableDefinition bool
}

// This is a value walk, not a semantic field lookup. Construction has already
// bounded and checked the JSON. Token order retains model and native-map order.
func semanticOrder(raw []byte) (map[string][]string, error) {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	walk := semanticJSONWalk{decoder: decoder, order: map[string][]string{}}
	if err := walk.value(nil); err != nil {
		return nil, err
	}
	return walk.order, nil
}

type semanticJSONWalk struct {
	decoder *json.Decoder
	order   map[string][]string
}

func (w *semanticJSONWalk) value(tokens []string) error {
	token, err := w.decoder.Token()
	if err != nil {
		return invalid()
	}
	if delimiter, ok := token.(json.Delim); ok {
		if delimiter == '{' {
			return w.mapping(tokens)
		}
		return w.sequence(tokens)
	}
	return nil
}
func (w *semanticJSONWalk) mapping(tokens []string) error {
	pointer := jsonpointer.FromTokens(tokens)
	for w.decoder.More() {
		token, err := w.decoder.Token()
		if err != nil {
			return invalid()
		}
		key, ok := token.(string)
		if !ok {
			return invalid()
		}
		w.order[pointer] = append(w.order[pointer], key)
		if err := w.value(appendPath(tokens, key)); err != nil {
			return err
		}
	}
	_, err := w.decoder.Token()
	return err
}
func (w *semanticJSONWalk) sequence(tokens []string) error {
	for i := 0; w.decoder.More(); i++ {
		if err := w.value(appendPath(tokens, strconv.Itoa(i))); err != nil {
			return err
		}
	}
	_, err := w.decoder.Token()
	return err
}

func semanticVariableNames(value string) []string {
	var result []string
	seen := map[string]bool{}
	for _, match := range variableTokens.FindAllStringSubmatch(value, -1) {
		if !seen[match[1]] {
			result = append(result, match[1])
			seen[match[1]] = true
		}
	}
	return result
}

func (m *semanticModel) checkVariables(c *semanticCollector) error {
	if err := m.loadIntent(); err != nil {
		return err
	}
	for _, leaf := range m.intent.references {
		if leaf.variableDefinition {
			continue
		}
		for _, name := range semanticVariableNames(leaf.value) {
			if !m.definitions[variablesSection][name] {
				c.report(semanticOwner{}, fmt.Sprintf("Undefined variable '%s' referenced at '%s'", name, leaf.path))
			}
		}
	}
	return nil
}

func (m *semanticModel) checkExplicitness(c *semanticCollector) {
	for _, message := range m.intent.errors {
		c.report(semanticOwner{}, message)
	}
}
