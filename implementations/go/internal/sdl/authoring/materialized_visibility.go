package authoring

func boundaryVisibility(boundary map[string]any) error {
	declared := map[string]any{}
	for _, field := range []string{observableRefsField, hiddenRefsField, evidenceRefsField} {
		for _, ref := range array(boundary[field]) {
			declared[text(ref)] = true
		}
	}
	evidence := map[string]any{}
	for _, ref := range array(boundary[evidenceRefsField]) {
		evidence[text(ref)] = true
	}
	for _, field := range []string{viewRulesField, viewTransitionsField} {
		for _, raw := range array(boundary[field]) {
			item := object(raw)
			if err := referencesPresent([]any{item[informationRefField]}, declared); err != nil {
				return err
			}
			if err := referencesPresent(array(item[evidenceRefsField]), evidence); err != nil {
				return err
			}
		}
	}
	return nil
}
