package sdl

import "encoding/json"

// SafeStates resolves the nearest authored safe state of each eligible
// declaration, with the exact observed proof of each assertion. The result is
// a separate declaration; it grants no effect permission.
func SafeStates(scenario Scenario) ([]json.RawMessage, error) {
	input, err := nativeScenario(scenario)
	if err != nil {
		return nil, err
	}
	resolved, err := input.document.SafeStates()
	if err != nil {
		return nil, err
	}
	result := make([]json.RawMessage, len(resolved))
	for i, state := range resolved {
		if result[i], err = json.Marshal(state); err != nil {
			return nil, invalidScenario()
		}
	}
	return result, nil
}
