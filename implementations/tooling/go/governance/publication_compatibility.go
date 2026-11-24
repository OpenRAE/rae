package governance

import (
	"maps"
	"slices"
	"strconv"
	"strings"
)

func publicationPointer(base string, parts ...string) string {
	for _, part := range parts {
		if part == "" {
			continue
		}
		if base != "" {
			base += "/"
		}
		base += strings.ReplaceAll(strings.ReplaceAll(part, "~", "~0"), "/", "~1")
	}
	return base
}

func publicationObjectKeyword(key string) bool {
	switch key {
	case "additionalProperties", "patternProperties", "properties", "required":
		return true
	default:
		return false
	}
}

func publicationObjectNodes(value any) (map[string]*mapping, error) {
	nodes := map[string]*mapping{}
	err := collectPublicationNodes(nodes, "", value, 0)
	return nodes, err
}

func collectPublicationNodes(nodes map[string]*mapping, pointer string, value any, depth int) error {
	if depth >= publicationComparisonDepth {
		return publicationComparisonError{}
	}
	raw := object(value)
	if raw == nil {
		return nil
	}
	if raw.has("additionalProperties") || raw.has("patternProperties") || raw.has("properties") || raw.has("required") {
		nodes[pointer] = raw
	}
	// Dict insertion order controls collisions caused by the reference's
	// empty pointer-component handling; visit children in that same order.
	for _, key := range raw.keys {
		name, _ := key.(string)
		if err := visitPublicationChild(nodes, publicationPointer(pointer, name), raw.get(key), depth+1); err != nil {
			return err
		}
	}
	return nil
}

func visitPublicationChild(nodes map[string]*mapping, pointer string, value any, depth int) error {
	switch raw := value.(type) {
	case *mapping:
		return collectPublicationNodes(nodes, pointer, raw, depth)
	case []any:
		for i, row := range raw {
			if err := collectPublicationNodes(nodes, publicationPointer(pointer, strconv.Itoa(i)), row, depth); err != nil {
				return err
			}
		}
	}
	return nil
}

func publicationRequired(raw *mapping) map[string]bool {
	values, _ := raw.get("required").([]any)
	required := map[string]bool{}
	for _, value := range values {
		if key, ok := value.(string); ok {
			required[key] = true
		}
	}
	return required
}

// Callers compare successfully hashed schemas, so each surviving string has
// a UTF-8 form. Enum identity deliberately uses JSON spelling, while defaults
// and property cores use the reference's numeric structural equality.
func publicationPropertyChanges(pointer string, oldValue, newValue any) ([]string, error) {
	oldProperty, newProperty := object(oldValue), object(newValue)
	if oldProperty == nil || newProperty == nil {
		equal, err := publicationAnnotationEqual(oldValue, newValue, false)
		if err != nil {
			return nil, err
		}
		if !equal {
			return []string{pointer + " schema changed"}, nil
		}
		return nil, nil
	}
	changes := []string{}
	if oldProperty.has("default") != newProperty.has("default") || !publicationEqual(oldProperty.get("default"), newProperty.get("default")) {
		changes = append(changes, pointer+" default changed")
	}
	enums, err := publicationEnumChanges(pointer, oldProperty.get("enum"), newProperty.get("enum"))
	if err != nil {
		return nil, err
	}
	changes = append(changes, enums...)
	equal, err := publicationAnnotationEqual(oldProperty, newProperty, true)
	if err != nil {
		return nil, err
	}
	if !equal {
		changes = append(changes, pointer+" schema changed")
	}
	return changes, nil
}

func publicationEnumChanges(pointer string, oldValue, newValue any) ([]string, error) {
	oldEnum, hadEnum := oldValue.([]any)
	newEnum, hasEnum := newValue.([]any)
	switch {
	case !hadEnum && hasEnum:
		return []string{pointer + " enum constraint added"}, nil
	case hadEnum && !hasEnum:
		return []string{pointer + " enum constraint removed"}, nil
	case !hadEnum:
		return nil, nil
	}
	keys := map[string]bool{}
	for _, value := range newEnum {
		data, err := publicationJSON(value)
		if err != nil {
			return nil, err
		}
		keys[string(data)] = true
	}
	removed := []string{}
	for _, value := range oldEnum {
		data, err := publicationJSON(value)
		if err != nil {
			return nil, err
		}
		if !keys[string(data)] {
			text, isText := value.(string)
			if !isText {
				text = string(data)
			}
			removed = append(removed, text)
		}
	}
	if len(removed) > 0 {
		return []string{pointer + " enum values removed: " + strings.Join(removed, ", ")}, nil
	}
	return nil, nil
}

func publicationBreakingChanges(oldValue, newValue any) ([]string, error) {
	oldNodes, err := publicationObjectNodes(oldValue)
	if err != nil {
		return nil, err
	}
	newNodes, err := publicationObjectNodes(newValue)
	if err != nil {
		return nil, err
	}
	changes := []string{}
	for _, pointer := range slices.Sorted(maps.Keys(oldNodes)) {
		oldNode, newNode := oldNodes[pointer], newNodes[pointer]
		label := pointer
		if label == "" {
			label = rootLocation
		}
		if newNode == nil {
			changes = append(changes, label+" object schema removed")
			continue
		}
		properties, err := publicationObjectChanges(pointer, oldNode, newNode)
		if err != nil {
			return nil, err
		}
		changes = append(changes, properties...)
		changes = append(changes, publicationConstraintChanges(pointer, oldNode, newNode)...)
	}
	return changes, nil
}

func publicationConstraintChanges(pointer string, oldNode, newNode *mapping) []string {
	changes := []string{}
	oldRequired, newRequired := publicationRequired(oldNode), publicationRequired(newNode)
	for _, key := range slices.Sorted(maps.Keys(newRequired)) {
		if !oldRequired[key] {
			changes = append(changes, publicationPointer(pointer, "required", key)+" newly required")
		}
	}
	if oldNode.get("additionalProperties") != false && newNode.get("additionalProperties") == false {
		label := pointer
		if label == "" {
			label = rootLocation
		}
		changes = append(changes, label+" additionalProperties tightened")
	}
	return changes
}

func publicationObjectChanges(pointer string, oldNode, newNode *mapping) ([]string, error) {
	oldProperties, newProperties := object(oldNode.get("properties")), object(newNode.get("properties"))
	changes := []string{}
	for _, key := range sortedMappingKeys(oldProperties) {
		if !newProperties.has(key) {
			changes = append(changes, publicationPointer(pointer, "properties", key)+" removed")
		}
	}
	for _, key := range sortedMappingKeys(oldProperties) {
		if newProperties.has(key) {
			property, err := publicationPropertyChanges(publicationPointer(pointer, "properties", key), oldProperties.get(key), newProperties.get(key))
			if err != nil {
				return nil, err
			}
			changes = append(changes, property...)
		}
	}
	return changes, nil
}
