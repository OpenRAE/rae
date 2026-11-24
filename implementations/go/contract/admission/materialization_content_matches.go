package admission

// MaterializationContentMatches compares independently derived native common
// content, retaining registered identities and ignoring phase provenance.
func MaterializationContentMatches(source, current MaterializationCompilation) (bool, error) {
	original, err := materializationContentInput(source)
	if err != nil {
		return false, err
	}
	selected, err := materializationContentInput(current)
	if err != nil {
		return false, err
	}
	profiles := materializationComposer{identities: original.identities}
	if err := profiles.mergeProfiles(selected.identities); err != nil {
		return false, err
	}
	difference := materializationDiff{identities: profiles.identities, remaining: 100000}
	if err := difference.walk(materializationOperand{value: original.full, present: true}, materializationOperand{value: selected.full, present: true}); err != nil {
		return false, err
	}
	return len(difference.origins) == 0, nil
}
