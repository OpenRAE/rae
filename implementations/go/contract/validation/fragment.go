package validation

import (
	"net/url"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/base/ingress"
)

// DecodeObjectFragment validates a bounded object against a reachable fragment
// of an already compiled published schema. The fresh JSON data is not admitted
// semantically. It is intended for explicit typed context subcarriers.
func (v *Validator) DecodeObjectFragment(id, pointer string, data []byte, limits ingress.Limits) (map[string]any, error) {
	if v == nil || v.contracts[id].schema == nil {
		return nil, failure(fault.InvalidInput, "contract-unknown")
	}
	if pointer != "#" && !strings.HasPrefix(pointer, "#/") {
		return nil, failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	schema := findSchemaFragment(v.contracts[id].schema, pointer)
	if schema == nil {
		return nil, failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	parsed, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return nil, err
	}
	if !boundedNumbers(parsed) {
		return nil, failure(fault.InvalidInput, "contract-number-limit")
	}
	if err := schema.Validate(parsed); err != nil {
		return nil, failure(fault.InvalidInput, "contract-schema-mismatch")
	}
	object, ok := parsed.(map[string]any)
	if !ok {
		return nil, failure(fault.InvalidInput, "contract-schema-mismatch")
	}
	return object, nil
}

// DefaultedObjectFragment returns a fresh, schema-checked object with published
// defaults applied at a reachable compiled fragment. It grants no semantic
// admission. It uses Defaulted's byte, depth and visit bounds and preserves
// original branch selection; families own serializer omissions.
func (v *Validator) DefaultedObjectFragment(id, pointer string, data []byte, limits ingress.Limits) (map[string]any, error) {
	original, err := v.DecodeObjectFragment(id, pointer, data, limits)
	if err != nil {
		return nil, err
	}
	schema := findSchemaFragment(v.contracts[id].schema, pointer)
	if schema == nil {
		return nil, failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	target, err := defaultedSchema(schema, original, limits)
	if err != nil {
		return nil, err
	}
	result, ok := target.(map[string]any)
	if !ok {
		return nil, failure(fault.Operational, codeContractDefaultInvalid)
	}
	return result, nil
}

func findSchemaFragment(root *jsonschema.Schema, pointer string) *jsonschema.Schema {
	seen := map[*jsonschema.Schema]bool{}
	pending := []*jsonschema.Schema{root}
	for work := 0; len(pending) > 0 && work < 100000; work++ {
		current := pending[len(pending)-1]
		pending = pending[:len(pending)-1]
		if current == nil || seen[current] {
			continue
		}
		seen[current] = true
		location, err := url.Parse(current.Location)
		if err == nil && "#"+location.Fragment == pointer {
			return current
		}
		pending = append(pending, compiledChildren(current)...)
	}
	return nil
}

func compiledChildren(s *jsonschema.Schema) []*jsonschema.Schema {
	children := []*jsonschema.Schema{s.Ref, s.RecursiveRef, s.Not, s.If, s.Then, s.Else, s.PropertyNames, s.UnevaluatedProperties, s.UnevaluatedItems, s.Items2020, s.Contains, s.ContentSchema}
	if s.DynamicRef != nil {
		children = append(children, s.DynamicRef.Ref)
	}
	for _, dependency := range s.Dependencies {
		if child, ok := dependency.(*jsonschema.Schema); ok {
			children = append(children, child)
		}
	}
	for _, group := range [][]*jsonschema.Schema{s.AllOf, s.AnyOf, s.OneOf, s.PrefixItems} {
		children = append(children, group...)
	}
	for _, group := range []map[string]*jsonschema.Schema{s.Properties, s.DependentSchemas} {
		for _, child := range group {
			children = append(children, child)
		}
	}
	for _, child := range s.PatternProperties {
		children = append(children, child)
	}
	for _, candidate := range []any{s.AdditionalProperties, s.AdditionalItems, s.Items} {
		switch child := candidate.(type) {
		case *jsonschema.Schema:
			children = append(children, child)
		case []*jsonschema.Schema:
			children = append(children, child...)
		}
	}
	return children
}

// CheckLocalFragment checks bounded JSON against a reachable fragment of a
// compiled published schema. It then runs the local rules annotated within
// the fragment, with the fragment as the rule root, and visits each
// applicable schema instance for owner model checks. Contextual rules are
// omitted, so the result makes no contextual or admission claim.
func (v *Validator) CheckLocalFragment(id, pointer string, data []byte, limits ingress.Limits, check func(SchemaInstance) error) error {
	if v == nil || v.contracts[id].schema == nil {
		return failure(fault.InvalidInput, "contract-unknown")
	}
	if check == nil {
		return failure(fault.Operational, "contract-model-check-required")
	}
	if !strings.HasPrefix(pointer, "#/") {
		return failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	schema := findSchemaFragment(v.contracts[id].schema, pointer)
	if schema == nil {
		return failure(fault.InvalidInput, codeContractFragmentUnknown)
	}
	root, err := ingress.Parse(data, limits, ingress.Object)
	if err != nil {
		return err
	}
	if !boundedNumbers(root) {
		return failure(fault.InvalidInput, "contract-number-limit")
	}
	if err := schema.Validate(root); err != nil {
		return failure(fault.InvalidInput, "contract-schema-mismatch")
	}
	entry := v.contracts[id]
	invoked := map[ruleIdentity]bool{}
	options := semanticInvocationOptions{source: string(data)}
	if err := walkSchema(visit{schema, root, ""}, func(current visit) error {
		return v.invoke(id, current, root, nil, entry.annotations, invoked, options)
	}); err != nil {
		return err
	}
	return walkSchema(visit{schema, root, ""}, func(current visit) error {
		return entry.visitInstance(id, current, root, check)
	})
}
