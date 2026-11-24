package experiment

import (
	"maps"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type scientificOriginal struct {
	run      map[string]any
	priority int
}

func canonicalArchivalRuns(records []Decision, id string) (map[string]scientificOriginal, error) {
	originals := map[string]scientificOriginal{}
	for _, record := range records {
		m := decisionMap(record)
		if text(m, termExperimentID) != id {
			continue
		}
		priority, eligible := scientificPriority(record.SchemaVersion(), m)
		if !eligible {
			continue
		}
		run := object(m[termRun])
		key := versionKey(termRun, run)
		if prior, ok := originals[key]; ok {
			if !same(prior.run, run) {
				return nil, integrity()
			}
			priority = max(priority, prior.priority)
		}
		originals[key] = scientificOriginal{run: run, priority: priority}
	}
	return originals, nil
}
func scientificPriority(schema string, m map[string]any) (int, bool) {
	priority := 2
	switch schema {
	case candidateSchema, archiveSchema:
	case publicationSchema:
		if m[termRun] == nil || !archivalRun(m[termRun]) || hasScientificParent(m[termRun]) {
			return 0, false
		}
		priority = 0
		if text(m, "validation_status") == termPassed {
			priority = 1
		}
	default:
		return 0, false
	}
	return priority, true
}
func hasScientificParent(run any) bool {
	for _, ref := range array(at(run, "derived_from_refs")) {
		if text(ref, termRefKind) == termRun && text(ref, termRefID) == text(run, termRunID) && text(ref, termRefDigest) != "" {
			return true
		}
	}
	return false
}
func scientificFacts(run map[string]any) map[string]any {
	facts := maps.Clone(run)
	delete(facts, "run_version")
	delete(facts, "execution_accounting")
	return facts
}
func matchingScientificOriginal(run map[string]any, originals map[string]scientificOriginal) map[string]any {
	if _, sameVersion := originals[versionKey(termRun, run)]; sameVersion || !archivalRun(run) || run["execution_accounting"] == nil {
		return nil
	}
	priority, matches := -1, 0
	var chosen map[string]any
	facts := scientificFacts(run)
	for _, candidate := range originals {
		if text(candidate.run, termRunID) != text(run, termRunID) || !archivalRun(candidate.run) || !same(facts, scientificFacts(candidate.run)) {
			continue
		}
		if candidate.priority > priority {
			chosen, priority, matches = candidate.run, candidate.priority, 1
		} else if candidate.priority == priority {
			matches++
		}
	}
	if matches == 1 {
		return chosen
	}
	return nil
}
func accountingValidationRecord(run binding.ExperimentRunV1, originals map[string]scientificOriginal) (binding.ExperimentRunV1, binding.ExperimentRunV1, error) {
	view, err := transportView(run)
	if err != nil {
		return run, run, err
	}
	original := matchingScientificOriginal(view, originals)
	if original == nil {
		return run, run, nil
	}
	raw, err := canonical(original)
	if err != nil {
		return run, run, err
	}
	view["derived_from_refs"] = append(array(view["derived_from_refs"]), map[string]any{termRefKind: termRun, termRefID: original[termRunID], termRefVersion: original["run_version"], termRefDigest: digest.SHA256(raw), "ref_path": nil})
	var linked, checked binding.ExperimentRunV1
	if convert(view, &linked) != nil || convert(original, &checked) != nil {
		return run, run, integrity()
	}
	return linked, checked, nil
}
