package validation

func (e *inertEvaluator) object(schema *inertNode, key string, value *inertNode, first bool) bool {
	if _, ok := value.value.(map[string]any); !ok {
		return true
	}
	child := schema.members[key]
	valid := true
	for _, name := range e.objectKeys(schema, key, value) {
		next, instance := child, value.members[name]
		switch key {
		case keywordProperties:
			next = child.members[name]
		case keywordPropertyNames:
			instance = &inertNode{value: name}
		case keywordDependentSchemas:
			next = child.members[name]
			instance = value
		}
		if !e.check(next, instance, first) {
			valid = false
			if first {
				return false
			}
		}
	}
	return valid
}
func (e *inertEvaluator) objectKeys(schema *inertNode, key string, value *inertNode) []string {
	child := schema.members[key]
	keys := []string{}
	switch key {
	case keywordPropertyNames:
		return value.keys
	case keywordProperties, keywordDependentSchemas:
		for _, name := range child.keys {
			if value.members[name] != nil {
				keys = append(keys, name)
			}
		}
	case keywordAdditionalProperties:
		properties := schema.members[keywordProperties]
		for _, name := range value.keys {
			if properties == nil || properties.members[name] == nil {
				keys = append(keys, name)
			}
		}
	}
	return keys
}
func (e *inertEvaluator) array(schema *inertNode, key string, value *inertNode, first bool) bool {
	if _, ok := value.value.([]any); !ok {
		return true
	}
	child := schema.members[key]
	if key == keywordContains {
		return e.contains(schema, value)
	}
	valid := true
	start := 0
	end := len(value.items)
	if prefix := schema.members[keywordPrefixItems]; prefix != nil && key == keywordItems {
		start = len(prefix.items)
	}
	if key == keywordPrefixItems {
		end = min(end, len(child.items))
	}
	for i := start; i < end; i++ {
		next := child
		if key == keywordPrefixItems {
			next = child.items[i]
		}
		if !e.check(next, value.items[i], first) {
			valid = false
			if first {
				return false
			}
		}
	}
	return valid
}
func (e *inertEvaluator) contains(schema, value *inertNode) bool {
	count := 0
	maximum := inertInt(schema, "maxContains", len(value.items))
	for _, item := range value.items {
		if e.check(schema.members[keywordContains], item, true) {
			count++
			if count > maximum {
				return false
			}
		}
		if e.err != nil {
			return false
		}
	}
	return count >= inertInt(schema, "minContains", 1)
}
