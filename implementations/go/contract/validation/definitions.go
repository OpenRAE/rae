package validation

import (
	"maps"
	"net/url"
	"reflect"
	"slices"
	"strconv"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

const definitionsPrefix = "/$defs/"

// DefinitionVisit is one object instance that the contract schema types as
// its root model or as a member of its $defs. Value is the parsed object, so
// a visit can change it. Path is the JSON pointer of the instance.
type DefinitionVisit struct {
	Definition, Path string
	Value            map[string]any
}

// VisitDefinitions parses bounded input without schema admission and visits
// each object instance typed by the contract root or a $defs member, inner
// instances first. A union selects the first member whose constant
// properties match the instance, otherwise the first member that validates
// it. It returns the parsed root, with the changes that the visits made.
// This method grants no admission.
func (v *Validator) VisitDefinitions(id string, data []byte, limits ingress.Limits, visit func(DefinitionVisit) error) (any, error) {
	if v == nil || v.contracts[id].schema == nil {
		return nil, failure(fault.InvalidInput, "contract-unknown")
	}
	if visit == nil {
		return nil, failure(fault.Operational, "contract-model-check-required")
	}
	entry := v.contracts[id]
	kind := ingress.Object
	if entry.raw[keywordType] == "array" {
		kind = ingress.Array
	}
	root, err := ingress.Parse(data, limits, kind)
	if err != nil {
		return nil, err
	}
	if !boundedNumbers(root) {
		return nil, failure(fault.InvalidInput, "contract-number-limit")
	}
	depth := 64
	if limits.MaxDepth > 0 {
		depth = min(depth, limits.MaxDepth)
	}
	walk := definitionWalk{root: entry.schema, visit: visit, bound: entry.walkBound(len(data)), depth: depth}
	if err := walk.value(entry.schema, root, "", 0); err != nil {
		return nil, err
	}
	return root, nil
}

type definitionWalk struct {
	root               *jsonschema.Schema
	visit              func(DefinitionVisit) error
	work, bound, depth int
}

func (w *definitionWalk) value(schema *jsonschema.Schema, value any, path string, depth int) error {
	w.work++
	if w.work > w.bound || depth > w.depth {
		return failure(fault.InvalidInput, "contract-evaluation-limit")
	}
	leaves := schemaLeaves(schema)
	switch typed := value.(type) {
	case []any:
		return w.items(leaves, typed, path, depth)
	case map[string]any:
		for _, leaf := range leaves {
			if members, ok := leaf.AdditionalProperties.(*jsonschema.Schema); ok && len(leaf.Properties) == 0 && w.definition(leaf) == "" {
				for _, name := range slices.Sorted(maps.Keys(typed)) {
					if err := w.value(members, typed[name], path+"/"+escape(name), depth+1); err != nil {
						return err
					}
				}
				return nil
			}
		}
		model := w.selectModel(leaves, typed)
		if model == nil {
			return nil
		}
		for _, name := range slices.Sorted(maps.Keys(model.Properties)) {
			if child, ok := typed[name]; ok {
				if err := w.value(model.Properties[name], child, path+"/"+escape(name), depth+1); err != nil {
					return err
				}
			}
		}
		if err := w.visit(DefinitionVisit{Definition: w.definition(model), Path: path, Value: typed}); err != nil {
			return failure(fault.InvalidInput, "contract-model-mismatch")
		}
	}
	return nil
}

func (w *definitionWalk) items(leaves []*jsonschema.Schema, array []any, path string, depth int) error {
	for _, leaf := range leaves {
		if leaf.Items2020 == nil && len(leaf.PrefixItems) == 0 {
			continue
		}
		for index, child := range array {
			item := leaf.Items2020
			if index < len(leaf.PrefixItems) {
				item = leaf.PrefixItems[index]
			}
			if item == nil {
				continue
			}
			if err := w.value(item, child, path+"/"+strconv.Itoa(index), depth+1); err != nil {
				return err
			}
		}
		return nil
	}
	return nil
}

// selectModel follows the reference walk: one candidate is used as it is;
// several candidates are narrowed by constant properties, then by validation.
func (w *definitionWalk) selectModel(leaves []*jsonschema.Schema, value map[string]any) *jsonschema.Schema {
	var models []*jsonschema.Schema
	for _, leaf := range leaves {
		if w.definition(leaf) != "" {
			models = append(models, leaf)
		}
	}
	if len(models) <= 1 {
		if len(models) == 0 {
			return nil
		}
		return models[0]
	}
	for _, model := range models {
		if discriminated(model, value) {
			return model
		}
	}
	for _, model := range models {
		if model.Validate(value) == nil {
			return model
		}
	}
	return nil
}

func (w *definitionWalk) definition(schema *jsonschema.Schema) string {
	if schema.Properties == nil {
		return ""
	}
	location, err := url.Parse(schema.Location)
	if err != nil {
		return ""
	}
	if location.Fragment == "" && schema == w.root {
		return schema.Title
	}
	name, ok := strings.CutPrefix(location.Fragment, definitionsPrefix)
	if !ok || name == "" || strings.Contains(name, "/") {
		return ""
	}
	return name
}

// discriminated reports whether every constant property present in value
// matches, with at least one present. Enumerated types behind a reference
// are not constants.
func discriminated(model *jsonschema.Schema, value map[string]any) bool {
	matched := false
	for name, property := range model.Properties {
		var allowed []any
		switch {
		case property.Const != nil:
			allowed = []any{*property.Const}
		case property.Enum != nil:
			allowed = property.Enum.Values
		default:
			continue
		}
		actual, present := value[name]
		if !present {
			continue
		}
		if !slices.ContainsFunc(allowed, func(candidate any) bool { return literalEqual(candidate, actual) }) {
			return false
		}
		matched = true
	}
	return matched
}

func literalEqual(left, right any) bool {
	if leftText, ok := left.(string); ok {
		rightText, ok := right.(string)
		return ok && leftText == rightText
	}
	return reflect.DeepEqual(left, right)
}

// schemaLeaves flattens references and combinators into the schemas that
// describe instance structure, in declaration order and without repeats.
func schemaLeaves(schema *jsonschema.Schema) []*jsonschema.Schema {
	var leaves []*jsonschema.Schema
	seen := map[*jsonschema.Schema]bool{}
	var add func(*jsonschema.Schema)
	add = func(s *jsonschema.Schema) {
		if s == nil || seen[s] {
			return
		}
		seen[s] = true
		if s.Properties != nil || s.Items2020 != nil || len(s.PrefixItems) > 0 || s.AdditionalProperties != nil {
			leaves = append(leaves, s)
		}
		add(s.Ref)
		for _, group := range [][]*jsonschema.Schema{s.AllOf, s.AnyOf, s.OneOf} {
			for _, member := range group {
				add(member)
			}
		}
	}
	add(schema)
	return leaves
}
