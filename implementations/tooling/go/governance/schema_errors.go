package governance

import (
	"errors"
	"net/url"
	"slices"
	"strconv"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"github.com/santhosh-tekuri/jsonschema/v6/kind"
)

func schemaErrorLocation(err error, value any) string {
	root, ok := errors.AsType[*jsonschema.ValidationError](err)
	if !ok {
		return rootLocation
	}
	paths := [][]string{}
	pending := []*jsonschema.ValidationError{root}
	for len(pending) > 0 {
		node := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if location, changed := unevaluatedLocation(node); changed {
			paths = append(paths, location)
			continue
		}
		switch node.ErrorKind.(type) {
		case *kind.Schema, *kind.Group, *kind.Reference, *kind.AllOf:
			pending = append(pending, node.Causes...)
		default:
			paths = append(paths, node.InstanceLocation)
		}
	}
	slices.SortStableFunc(paths, func(a, b []string) int { return compareSchemaLocations(value, a, b) })
	if len(paths) == 0 || len(paths[0]) == 0 {
		return rootLocation
	}
	return strings.Join(paths[0], "/")
}

func compareSchemaLocations(node any, a, b []string) int {
	for i := range min(len(a), len(b)) {
		if a[i] != b[i] {
			if _, array := node.([]any); array {
				left, _ := strconv.Atoi(a[i])
				right, _ := strconv.Atoi(b[i])
				return left - right
			}
			return strings.Compare(a[i], b[i])
		}
		if m, ok := node.(*mapping); ok {
			node = m.get(a[i])
		} else if items, ok := node.([]any); ok {
			index, _ := strconv.Atoi(a[i])
			if index >= 0 && index < len(items) {
				node = items[index]
			}
		}
	}
	return len(a) - len(b)
}

// Python reports an unevaluated-value failure at the enclosing collection.
// The maintained engine reports its child. Schema locations identify that
// applicator even when deeper child checks or references produce the error.
func unevaluatedLocation(node *jsonschema.ValidationError) ([]string, bool) {
	_, fragment, found := strings.Cut(node.SchemaURL, "#")
	if !found {
		return nil, false
	}
	fragment, err := url.PathUnescape(fragment)
	if err != nil {
		return nil, false
	}
	parts := strings.Split(fragment, "/")[1:]
	depth, inside := 0, false
	for i := 0; i < len(parts); i++ {
		switch parts[i] {
		case "properties", "patternProperties", "prefixItems":
			i++
			if inside {
				depth++
			}
		case "$defs", "definitions", "dependentSchemas", "dependencies":
			i++
		case "unevaluatedProperties", "unevaluatedItems":
			inside = true
			depth++
		case "items", "additionalItems", "additionalProperties", "contains":
			if inside {
				depth++
			}
		}
	}
	if !inside || depth > len(node.InstanceLocation) {
		return nil, false
	}
	return node.InstanceLocation[:len(node.InstanceLocation)-depth], true
}
