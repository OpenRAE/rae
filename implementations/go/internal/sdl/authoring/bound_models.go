package authoring

import (
	"slices"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/internal/base/jsonpointer"
	"github.com/OpenRAE/rae/implementations/go/internal/sdl/source"
)

// Bound content can carry composition-generated qualified declaration keys.
// Each declaration still uses its unchanged published model and local rules.
func (c *composition) validateBound(value map[string]any) (map[string]any, error) {
	id := authoringContract
	walk := normalizer{parser: c.parser, id: id, remaining: c.parser.limits.MaxComposedNodes}
	normalized, err := walk.walk(c.parser.schemas[id], "#", value, nil, scalarPolicy{}, source.View{})
	if err != nil {
		return nil, err
	}
	root := object(normalized)
	for name, value := range root {
		if err := c.checkBoundSection(name, value); err != nil {
			return nil, err
		}
	}
	return root, nil
}
func (c *composition) checkBoundSection(name string, value any) error {
	switch {
	case slices.Contains(declarationSections(), name):
		pointer := c.declarationPointer(name)
		for _, declaration := range object(value) {
			if err := c.checkBoundFragment(pointer, declaration); err != nil {
				return err
			}
		}
	case name == forwardingSection:
		for _, agent := range array(value) {
			if err := c.checkBoundFragment("#/properties/forwarding_agents/items", agent); err != nil {
				return err
			}
		}
	case object(value) != nil:
		return c.checkBoundFragment("#/properties/"+jsonpointer.EscapeToken(name), value)
	}
	return nil
}
func (c *composition) declarationPointer(section string) string {
	root := c.parser.schemas[authoringContract]
	schema := object(object(root["properties"])[section])
	prefix := "#/properties/" + jsonpointer.EscapeToken(section)
	if child := object(schema["additionalProperties"]); child != nil {
		if ref := text(child["$ref"]); ref != "" {
			return ref
		}
		return prefix + "/additionalProperties"
	}
	for pattern, raw := range object(schema["patternProperties"]) {
		if ref := text(object(raw)["$ref"]); ref != "" {
			return ref
		}
		return prefix + "/patternProperties/" + jsonpointer.EscapeToken(pattern)
	}
	return ""
}
func (c *composition) checkBoundFragment(pointer string, value any) error {
	data, err := encode(value, c.parser.limits.MaxComposedBytes, false)
	if err != nil {
		return err
	}
	limits := ingress.Limits{MaxBytes: int(c.parser.limits.MaxComposedBytes), MaxDepth: c.parser.limits.MaxDepth}
	return c.parser.models.CheckModelFragment(authoringContract, pointer, data, limits)
}
