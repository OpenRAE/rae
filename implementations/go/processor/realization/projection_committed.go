package realization

import "slices"

func restoreCommittedRecord(record map[string]any, base []string, classification string) (map[string]any, error) {
	_, presentMarker := record[termValuePresent]
	_, commitmentMarker := record[termValueCommitment]
	if !presentMarker && !commitmentMarker {
		return record, nil
	}
	candidate := map[string]any{termValue: ""}
	for _, key := range base {
		field, supplied := record[key]
		if !supplied {
			return nil, invalidRealization()
		}
		candidate[key] = field
	}
	if len(record) != len(base)+1 && len(record) != len(base)+2 {
		return nil, invalidRealization()
	}
	for key := range record {
		if !slices.Contains(base, key) && key != termValuePresent && key != termValueCommitment {
			return nil, invalidRealization()
		}
	}
	if err := checkCommittedPresence(record, classification); err != nil {
		return nil, err
	}

	return candidate, nil
}

func checkCommittedPresence(record map[string]any, classification string) error {
	present, ok := record[termValuePresent].(bool)
	if !ok {
		return invalidRealization()
	}
	if commitment := record[termValueCommitment]; commitment != nil {
		if !present || !validCommitment(commitment) {
			return invalidRealization()
		}
	} else {
		protected, err := protectedClassification(record[classification])
		if err != nil || present != protected {
			return invalidRealization()
		}
	}
	return nil
}
