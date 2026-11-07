package authoring

func (c materializedChecks) variables() error {
	defined := object(c.value["variables"])
	return checkVariableUses(c.value, defined)
}

func checkVariableUses(value any, defined map[string]any) error {
	switch v := value.(type) {
	case string:
		return checkStringVariableUses(v, defined)
	case map[string]any:
		for _, child := range v {
			if err := checkVariableUses(child, defined); err != nil {
				return err
			}
		}
	case []any:
		for _, child := range v {
			if err := checkVariableUses(child, defined); err != nil {
				return err
			}
		}
	}
	return nil
}

func checkStringVariableUses(value string, defined map[string]any) error {
	for {
		match := variableTokens.FindStringSubmatchIndex(value)
		if match == nil {
			return nil
		}
		if _, present := defined[value[match[2]:match[3]]]; !present {
			return semanticInvalid()
		}
		value = value[match[1]:]
	}
}
