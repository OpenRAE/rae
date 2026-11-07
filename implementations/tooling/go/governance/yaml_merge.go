package governance

import (
	"errors"
	"slices"

	"go.yaml.in/yaml/v3"
)

// Flatten merge syntax before construction, as SafeLoader does. Removing the
// merge pair before visiting its target also preserves recursive merge aliases.
func flattenYAMLMap(node *yaml.Node) error {
	merged := []*yaml.Node{}
	for i := 0; i < len(node.Content); {
		key, value := node.Content[i], node.Content[i+1]
		if key.Tag != "!!merge" {
			i += 2
			continue
		}
		node.Content = append(node.Content[:i], node.Content[i+2:]...)
		pairs, err := yamlMergePairs(value)
		if err != nil {
			return err
		}
		merged = append(merged, pairs...)
	}
	if len(merged) > 0 {
		node.Content = append(merged, node.Content...)
	}
	return nil
}

func yamlMergePairs(node *yaml.Node) ([]*yaml.Node, error) {
	if node.Kind == yaml.AliasNode {
		node = node.Alias
	}
	if node.Kind == yaml.MappingNode {
		if err := flattenYAMLMap(node); err != nil {
			return nil, err
		}
		return node.Content, nil
	}
	if node.Kind != yaml.SequenceNode {
		return nil, errors.New("YAML merge requires mappings")
	}
	groups := make([][]*yaml.Node, len(node.Content))
	for i, child := range node.Content {
		if child.Kind == yaml.AliasNode {
			child = child.Alias
		}
		if child.Kind != yaml.MappingNode {
			return nil, errors.New("YAML merge sequence requires mappings")
		}
		if err := flattenYAMLMap(child); err != nil {
			return nil, err
		}
		groups[i] = child.Content
	}
	slices.Reverse(groups)
	pairs := []*yaml.Node{}
	for _, group := range groups {
		pairs = append(pairs, group...)
	}
	return pairs, nil
}
