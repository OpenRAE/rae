package realization

// The legacy contract fixes depth 64 and collection identity to JSON string,
// integer, or boolean coordinates. Requirements and both values are admitted
// before this compatibility view is consulted.
func legacyStructureMatches(input, expected, actual any, depth int) bool {
	if depth > 64 {
		return false
	}
	rule := ownedProjection[map[string]any](input)
	switch rule[termKind] {
	case termExact:
		return projectionEqual(expected, actual, true)
	case termOpen:
		return rule["taxonomy_sentinel"] != true || actual != nil && actual != termUnknown && actual != "other"
	case "record":
		return legacyRecordMatches(rule, expected, actual, depth)
	case "collection":
		return legacyCollectionMatches(rule, expected, actual, depth)
	default:
		return false
	}
}
func legacyRecordMatches(rule map[string]any, expected, actual any, depth int) bool {
	first, firstOK := expected.(map[string]any)
	second, secondOK := actual.(map[string]any)
	if !firstOK || !secondOK {
		return false
	}
	fields := ownedProjection[map[string]any](rule["fields"])
	for key, child := range fields {
		before, beforePresent := first[key]
		after, afterPresent := second[key]
		if !beforePresent || !afterPresent || !legacyStructureMatches(child, before, after, depth+1) {
			return false
		}
	}
	if rule["additional"] == true {
		return true
	}
	for key, value := range second {
		if _, known := fields[key]; known {
			continue
		}
		before, present := first[key]
		if !present || !projectionEqual(before, value, true) {
			return false
		}
	}
	return true
}
func legacyCollectionMatches(rule map[string]any, expected, actual any, depth int) bool {
	fields := ownedProjection[[]any](rule["identity_fields"])
	first, firstOK := legacyIndexedCollection(expected, fields)
	second, secondOK := legacyIndexedCollection(actual, fields)
	if !firstOK || !secondOK {
		return false
	}
	members := ownedProjection[map[string]any](rule["members"])
	if len(members) != len(first) || rule["additional"] != true && len(first) != len(second) {
		return false
	}
	for identity, child := range members {
		before, beforePresent := first[identity]
		after, afterPresent := second[identity]
		if !beforePresent || !afterPresent || !legacyStructureMatches(child, before, after, depth+1) {
			return false
		}
	}
	return true
}
func legacyIndexedCollection(input any, fields []any) (map[string]any, bool) {
	items, ok := input.([]any)
	if !ok {
		return nil, false
	}
	result := map[string]any{}
	for _, item := range items {
		record, ok := item.(map[string]any)
		if !ok {
			return nil, false
		}
		identity := make([]any, len(fields))
		for index, field := range fields {
			identity[index] = record[ownedProjection[string](field)]
		}
		for _, coordinate := range identity {
			if _, err := scalarChoiceIdentity([][]any{{coordinate}}, []int{0}); err != nil {
				return nil, false
			}
		}

		key, err := projectionDigest(identity)
		if err != nil {
			return nil, false
		}
		if _, duplicate := result[key]; duplicate {
			return nil, false
		}
		result[key] = item
	}
	return result, true
}
