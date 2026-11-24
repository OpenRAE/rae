package trial

import (
	"github.com/OpenRAE/rae/implementations/go/sdl"
)

func validateMixedSource(request Request, input compilationInputs, ref mixedSource, selected sdl.InstantiatedScenario) error {
	source, present := request.SourcePlans[ref.PlanID]
	if !present {
		return compositionRefusal("composition-source-plan-unresolved", "linked realization source plan is unresolved")
	}
	admitted, err := admitPlan(source)
	if err != nil {
		return compositionRefusal("composition-source-plan-invalid", "linked realization source plan failed closed reconstruction")
	}
	var plan trialPlan
	if decode(admitted.JSON(), &plan) != nil {
		return trialInvalid()
	}
	entry, present := plan.Entries[ref.EntryID]
	if !present || plan.ID != ref.PlanID || plan.Digest != ref.PlanDigest || entry.Digest != ref.EntryDigest || entry.RunID != ref.RunID {
		return compositionRefusal("composition-source-trial-mismatch", "linked realization source tuple does not match the sealed source plan")
	}
	var sourceRefs inputReferences
	if decode(plan.Refs, &sourceRefs) != nil {
		return trialInvalid()
	}
	if err = matchingMixedSourceInputs(sourceRefs, input.refs); err != nil {
		return err
	}
	outcomes := map[string]selectionOutcome{}
	for _, selection := range entry.Selections {
		outcomes[selection.Point] = selection.Outcome
	}
	fragment, err := fragmentDocument(input.owner, outcomes)
	if err != nil {
		return err
	}
	reconstructed, err := sdl.Select(request.Family, fragment, nil)
	if err != nil {
		return compositionRefusal("composition-source-selection-invalid", "linked realization source selection failed scenario admission")
	}
	expected, err := sdl.CanonicalDigest(reconstructed)
	if err != nil {
		return err
	}
	actual, err := sdl.CanonicalDigest(selected)
	if err != nil {
		return err
	}
	if expected != actual {
		return compositionRefusal("composition-source-selection-mismatch", "linked realization source does not bind the same admitted scenario selection")
	}
	return nil
}

func matchingMixedSourceInputs(sourceRefs, refs inputReferences) error {
	for _, pair := range [][2]any{{sourceRefs.Authoring, refs.Authoring}, {sourceRefs.Task, refs.Task}, {sourceRefs.TaskDigest, refs.TaskDigest}, {sourceRefs.Family, refs.Family}} {
		a, checkErr := encoded(pair[0])
		if checkErr != nil {
			return checkErr
		}
		b, checkErr := encoded(pair[1])
		if checkErr != nil {
			return checkErr
		}
		if !sameJSON(a, b) {
			return compositionRefusal("composition-source-input-mismatch", "linked realization source does not bind the same authoring, task, and scenario-family inputs")
		}
	}
	return nil
}
