package validation

import (
	"encoding/json"
	"maps"
	"net/url"
	"reflect"
	"slices"
	"strconv"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

func collect(node map[string]any, pointer string, result map[string][]annotation) error {
	if raw, ok := node["x-raes-invariants"]; ok {
		rows, err := parseAnnotations(raw)
		if err != nil {
			return err
		}
		result[pointer] = rows
	}
	for childPath, child := range schemaChildren(node) {
		if err := collect(child, pointer+childPath, result); err != nil {
			return err
		}
	}
	return nil
}

func parseAnnotations(raw any) ([]annotation, error) {
	encoded, err := json.Marshal(raw)
	if err != nil {
		return nil, failure(fault.Operational, codeContractInvariantInvalid)
	}
	var rows []annotation
	if err := json.Unmarshal(encoded, &rows); err != nil {
		return nil, failure(fault.Operational, codeContractInvariantInvalid)
	}
	seen := map[string]bool{}
	for _, row := range rows {
		if row.ID == "" || seen[row.ID] || len(row.Inputs) == 0 {
			return nil, failure(fault.Operational, codeContractInvariantInvalid)
		}
		for _, input := range row.Inputs {
			if input.ContractID == "" || input.Path != "#" && !strings.HasPrefix(input.Path, "#/") {
				return nil, failure(fault.Operational, codeContractInvariantInvalid)
			}
		}
		seen[row.ID] = true
	}
	return rows, nil
}

func schemaChildren(node map[string]any) map[string]map[string]any {
	result := map[string]map[string]any{}
	add := func(pointer string, value any) {
		if child, ok := value.(map[string]any); ok {
			result[pointer] = child
		}
	}
	for _, key := range []string{keywordDefs, keywordProperties, "patternProperties", keywordDependentSchemas} {
		children, _ := node[key].(map[string]any)
		for name, value := range children {
			add("/"+key+"/"+escape(name), value)
		}
	}
	for _, key := range []string{keywordItems, keywordAdditionalProperties, keywordContains, keywordPropertyNames, "if", keywordThen, keywordElse, keywordNot, "unevaluatedProperties", "unevaluatedItems"} {
		add("/"+key, node[key])
	}
	for _, key := range []string{keywordAllOf, keywordAnyOf, keywordOneOf, keywordPrefixItems} {
		children, _ := node[key].([]any)
		for index, value := range children {
			add("/"+key+"/"+strconv.Itoa(index), value)
		}
	}
	return result
}

func escape(s string) string { return strings.ReplaceAll(strings.ReplaceAll(s, "~", "~0"), "/", "~1") }

type visit struct {
	schema *jsonschema.Schema
	value  any
	path   string
}

func (v *Validator) semantic(id string, root, context any) error {
	return v.semanticMode(id, root, context, true)
}

func (v *Validator) semanticMode(id string, root, context any, complete bool) error {
	return v.semanticSource(id, root, context, complete, "")
}

func (v *Validator) semanticSource(id string, root, context any, complete bool, source string) error {
	if missingContext(context) {
		context = nil
	}
	contract := v.contracts[id]
	invoked := map[ruleIdentity]bool{}
	return walkSchema(visit{contract.schema, root, ""}, func(current visit) error {
		return v.invoke(id, current, root, context, contract.annotations, invoked, semanticInvocationOptions{complete: complete, source: source})
	})
}

func walkSchema(root visit, check func(visit) error) error {
	stack := []visit{root}
	seen := map[visitIdentity]bool{}
	for work := 0; len(stack) > 0; work++ {
		if work >= 100000 {
			return failure(fault.InvalidInput, "contract-evaluation-limit")
		}
		current := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		identity := visitIdentity{current.schema, current.path}
		if seen[identity] {
			continue
		}
		seen[identity] = true
		if err := check(current); err != nil {
			return err
		}
		stack = append(stack, applicable(current)...)
	}
	return nil
}

func missingContext(context any) bool {
	if context == nil {
		return true
	}
	value := reflect.ValueOf(context)
	kind := value.Kind()
	return (kind == reflect.Chan || kind == reflect.Func || kind == reflect.Interface || kind == reflect.Map || kind == reflect.Pointer || kind == reflect.Slice) && value.IsNil()
}

type visitIdentity struct {
	schema *jsonschema.Schema
	path   string
}
type ruleIdentity struct{ id, path string }

type semanticInvocationOptions struct {
	complete bool
	source   string
}

func (v *Validator) invoke(id string, current visit, root, context any, annotations map[string][]annotation, invoked map[ruleIdentity]bool, options semanticInvocationOptions) error {
	location, err := url.Parse(current.schema.Location)
	if err != nil {
		return failure(fault.Operational, codeContractInvariantInvalid)
	}
	pointer := "#" + location.Fragment
	for _, row := range annotations[pointer] {
		identity := ruleIdentity{row.ID, current.path}
		if invoked[identity] {
			continue
		}
		invoked[identity] = true
		key := Key{id, row.ID}
		rule := v.rules[key]
		if rule.Check == nil {
			return failure(fault.InvalidInput, "contract-semantic-rule-required")
		}
		if !options.complete && (rule.Contextual || rule.RequiresContext) {
			continue
		}
		if rule.RequiresContext && context == nil {
			return failure(fault.InvalidInput, "contract-semantic-context-required")
		}
		if err := rule.Check(Invocation{Key: key, Path: current.path, Root: root, Instance: current.value, Context: context, Inputs: slices.Clone(row.Inputs), Source: options.source}); err != nil {
			return failure(fault.InvalidInput, "contract-semantic-mismatch")
		}
	}
	return nil
}

func applicable(current visit) []visit {
	result := keywordThenVisits(current)
	if object, ok := current.value.(map[string]any); ok {
		result = append(result, objectVisits(current, object)...)
	}
	if array, ok := current.value.([]any); ok {
		result = append(result, arrayVisits(current, array)...)
	}
	slices.SortFunc(result, func(a, b visit) int {
		if c := strings.Compare(b.path, a.path); c != 0 {
			return c
		}
		return strings.Compare(b.schema.Location, a.schema.Location)
	})
	return result
}

func keywordThenVisits(current visit) []visit {
	s := current.schema
	var result []visit
	add := func(schema *jsonschema.Schema) {
		if schema != nil {
			result = append(result, visit{schema, current.value, current.path})
		}
	}
	add(s.Ref)
	for _, schema := range s.AllOf {
		add(schema)
	}
	for _, keywordThenes := range [][]*jsonschema.Schema{s.AnyOf, s.OneOf} {
		for _, schema := range keywordThenes {
			if schema.Validate(current.value) == nil {
				add(schema)
			}
		}
	}
	if s.If != nil {
		if s.If.Validate(current.value) == nil {
			add(s.If)
			add(s.Then)
		} else {
			add(s.Else)
		}
	}
	return result
}

func objectVisits(current visit, object map[string]any) []visit {
	s := current.schema
	var result []visit
	for _, name := range slices.Sorted(maps.Keys(object)) {
		result = append(result, memberVisits(current, name, object[name])...)
	}
	for _, name := range slices.Sorted(maps.Keys(s.DependentSchemas)) {
		if _, ok := object[name]; ok {
			result = append(result, visit{s.DependentSchemas[name], current.value, current.path})
		}
	}
	return result
}

func memberVisits(current visit, name string, child any) []visit {
	s := current.schema
	pointer := current.path + "/" + escape(name)
	var result []visit
	if schema := s.Properties[name]; schema != nil {
		result = append(result, visit{schema, child, pointer})
	}
	for pattern, schema := range s.PatternProperties {
		if pattern.MatchString(name) {
			result = append(result, visit{schema, child, pointer})
		}
	}
	if len(result) == 0 {
		if schema, ok := s.AdditionalProperties.(*jsonschema.Schema); ok {
			result = append(result, visit{schema, child, pointer})
		}
	}
	if s.PropertyNames != nil {
		result = append(result, visit{s.PropertyNames, name, pointer})
	}
	return result
}

func arrayVisits(current visit, array []any) []visit {
	s := current.schema
	var result []visit
	for index, child := range array {
		pointer := current.path + "/" + strconv.Itoa(index)
		if index < len(s.PrefixItems) {
			result = append(result, visit{s.PrefixItems[index], child, pointer})
		} else if s.Items2020 != nil {
			result = append(result, visit{s.Items2020, child, pointer})
		}
		if s.Contains != nil && s.Contains.Validate(child) == nil {
			result = append(result, visit{s.Contains, child, pointer})
		}
	}
	return result
}
