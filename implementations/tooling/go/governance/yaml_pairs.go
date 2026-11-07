package governance

import (
	"errors"

	"go.yaml.in/yaml/v3"
)

func constructPairs(node *yaml.Node, memo map[*yaml.Node]any, depth int) (any, error) {
	items := make([]any, len(node.Content))
	memo[node] = items
	for i, child := range node.Content {
		if child.Kind != yaml.MappingNode || len(child.Content) != 2 {
			return nil, errors.New("YAML pairs require single-entry mappings")
		}
		key, err := constructYAML(child.Content[0], memo, depth+1)
		if err != nil {
			return nil, err
		}
		value, err := constructYAML(child.Content[1], memo, depth+1)
		if err != nil {
			return nil, err
		}
		items[i] = yamlTuple{key, value}
	}
	return items, nil
}
