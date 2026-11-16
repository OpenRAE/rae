package trial

import (
	"encoding/json"
	"maps"
	"slices"
)

func authoringSelections(request Request, input compilationInputs, plan trialPlan) error {
	var design struct {
		Profile string `json:"profile"`
	}
	if !isNull(input.spec.Factorial) && decode(input.spec.Factorial, &design) != nil {
		return trialInvalid()
	}
	var profiles struct {
		Treatment string `json:"treatment_profile"`
	}
	if decode(plan.Profiles, &profiles) != nil {
		return trialInvalid()
	}
	typed := design.Profile == profileFactorialTreatments
	if !typed && profiles.Treatment == "" {
		return nil
	}
	if !typed || profiles.Treatment != design.Profile {
		return trialInvalid()
	}
	coordinates, err := authoringCoordinates(input.spec, request.Limits, plan)
	if err != nil {
		return err
	}
	if len(coordinates) != len(plan.Entries) {
		return trialInvalid()
	}
	if err = authoringCoordinateMembership(coordinates, plan); err != nil {
		return err
	}
	rows, err := selectionRows(request, input.spec, coordinates, input.family.Points)
	if err != nil {
		return err
	}
	records := map[string][]selectionRecord{}
	for i, c := range coordinates {
		raw, err := canonical(c)
		if err != nil {
			return err
		}
		records[string(raw)] = rows[i].selections
	}
	return checkAuthoringEntries(plan, records, input.descriptors)
}
func checkAuthoringEntries(plan trialPlan, records map[string][]selectionRecord, descriptors []admittedDescriptor) error {
	for _, entryID := range slices.Sorted(maps.Keys(plan.Entries)) {
		entry := plan.Entries[entryID]
		key, err := canonical(entry.Coordinate)
		if err != nil {
			return err
		}
		expected, err := encoded(records[string(key)])
		if err != nil {
			return err
		}
		actual, err := encoded(entry.Selections)
		if err != nil {
			return err
		}
		if !sameJSON(expected, actual) {
			return trialInvalid()
		}
		if err = authoringEntryBindings(entry, descriptors); err != nil {
			return err
		}
	}
	return nil
}
func authoringCoordinateMembership(coordinates []coordinate, plan trialPlan) error {
	expected := map[string]bool{}
	for _, c := range coordinates {
		raw, checkErr := canonical(c)
		if checkErr != nil {
			return checkErr
		}
		expected[string(raw)] = true
	}
	for _, entry := range plan.Entries {
		raw, checkErr := canonical(entry.Coordinate)
		if checkErr != nil {
			return checkErr
		}
		if !expected[string(raw)] {
			return trialInvalid()
		}
	}
	return nil
}
func authoringCoordinates(spec experimentSpec, limits Limits, plan trialPlan) ([]coordinate, error) {
	all, err := coordinates(spec, limits)
	if err != nil {
		return nil, err
	}
	if isNull(plan.ReplacementOrigin) {
		return all, nil
	}
	var origin replacementOrigin
	var policy replacementPolicy
	if decode(plan.ReplacementOrigin, &origin) != nil || decode(spec.RunPlan.ReplacementPolicy, &policy) != nil || !sameJSON(spec.RunPlan.ReplacementPolicy, plan.ReplacementPolicy) {
		return nil, trialInvalid()
	}
	index := -1
	for i, c := range all {
		id, checkErr := identity("trial-entry", struct {
			Plan       string `json:"plan_id"`
			Coordinate any    `json:"coordinate"`
		}{origin.RootPlanID, c.projection()}, false)
		if checkErr != nil {
			return nil, checkErr
		}
		if id == origin.RootEntryID {
			if index >= 0 {
				return nil, trialInvalid()
			}
			index = i
		}
	}
	if index < 0 {
		return nil, trialInvalid()
	}
	updated, err := (replacementContext{origin: origin, index: index, maximum: policy.Maximum}).coordinates(all)
	if err != nil {
		return nil, err
	}
	return []coordinate{updated[index]}, nil
}
func authoringEntryBindings(entry trialEntry, descriptors []admittedDescriptor) error {
	expected := []json.RawMessage{}
	for _, d := range descriptors {
		if d.wire.Condition == text(entry.Coordinate.ConditionID) {
			raw, err := encoded(struct {
				Descriptor json.RawMessage `json:"descriptor"`
				Origin     string          `json:"origin"`
			}{d.raw, originSelection})
			if err != nil {
				return err
			}
			expected = append(expected, raw)
		}
	}
	left, err := canonicalRows(expected)
	if err != nil {
		return err
	}
	right, err := canonicalRows(entry.Bindings)
	if err != nil {
		return err
	}
	a, err := encoded(left)
	if err != nil {
		return err
	}
	b, err := encoded(right)
	if err != nil {
		return err
	}
	if !sameJSON(a, b) {
		return trialInvalid()
	}
	return nil
}
