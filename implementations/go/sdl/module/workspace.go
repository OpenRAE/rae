package module

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

type workspaceReader struct {
	values    map[source.View]any
	flattened map[source.View][]source.ViewMember
}

func workspacePolicy(raw []byte, name string) (map[string]any, error) {
	root, err := source.ParseSyntax(raw, source.DefaultLimits(), name)
	if err != nil {
		return nil, err
	}
	reader := workspaceReader{values: map[source.View]any{}, flattened: map[source.View][]source.ViewMember{}}
	value, err := reader.value(root)
	if err != nil {
		return nil, err
	}
	result := object(value)
	if result == nil {
		return nil, invalid()
	}
	return result, nil
}
func (w *workspaceReader) value(node source.View) (any, error) {
	if value, present := w.values[node]; present {
		return value, nil
	}
	switch node.Kind() {
	case scalarSyntax:
		raw, quoted := node.Scalar()
		var value any = raw
		var err error
		if !quoted {
			value, err = workspaceScalar(raw)
		}
		if err == nil {
			w.values[node] = value
		}
		return value, err
	case sequenceSyntax:
		children := node.Elements()
		result := make([]any, len(children))
		w.values[node] = result
		for i, child := range children {
			value, err := w.value(child)
			if err != nil {
				return nil, err
			}
			result[i] = value
		}
		return result, nil
	case mappingSyntax:
		return w.mapping(node)
	}
	return nil, invalid()
}
func (w *workspaceReader) mapping(node source.View) (any, error) {
	pairs, err := w.flatten(node)
	if err != nil {
		return nil, err
	}
	result := map[string]any{}
	w.values[node] = result
	for _, pair := range pairs {
		key, err := w.key(pair.Key)
		if err != nil {
			return nil, err
		}
		value, err := w.value(pair.Value)
		if err != nil {
			return nil, err
		}
		result[key] = value
	}
	return result, nil
}
func (w *workspaceReader) key(node source.View) (string, error) {
	if node.Kind() != scalarSyntax {
		return "", invalid()
	}
	text, quoted := node.Scalar()
	// SafeLoader treats the implicit value tag as a string only in key position.
	if text == "=" && !quoted {
		return text, nil
	}
	value, err := w.value(node)
	if err != nil {
		return "", err
	}
	key, ok := value.(string)
	if !ok {
		return "", invalid()
	}
	return key, nil
}
func (w *workspaceReader) flatten(node source.View) ([]source.ViewMember, error) {
	if node.Kind() != mappingSyntax {
		return nil, invalid()
	}
	if _, present := w.flattened[node]; !present {
		w.flattened[node] = node.Members()
	}
	var merged []source.ViewMember
	for index := 0; index < len(w.flattened[node]); {
		pair := w.flattened[node][index]
		key, quoted := pair.Key.Scalar()
		if pair.Key.Kind() != scalarSyntax || key != "<<" || quoted {
			index++
			continue
		}
		// SafeLoader removes a merge pair before descending, including a self edge.
		pairs := w.flattened[node]
		w.flattened[node] = append(pairs[:index:index], pairs[index+1:]...)
		additions, err := w.merge(pair.Value)
		if err != nil {
			return nil, err
		}
		merged = append(merged, additions...)
	}
	merged = append(merged, w.flattened[node]...)
	w.flattened[node] = merged
	return merged, nil
}
func (w *workspaceReader) merge(value source.View) ([]source.ViewMember, error) {
	if value.Kind() == mappingSyntax {
		return w.flatten(value)
	}
	if value.Kind() != sequenceSyntax {
		return nil, invalid()
	}
	var result []source.ViewMember
	items := value.Elements()
	for _, item := range slices.Backward(items) {
		pairs, err := w.flatten(item)
		if err != nil {
			return nil, err
		}
		result = append(result, pairs...)
	}
	return result, nil
}
