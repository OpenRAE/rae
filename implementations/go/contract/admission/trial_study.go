package admission

import (
	"encoding/json"
	"maps"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// TrialStudyInputs supplies the authored definition, run evidence and retained lineage.
type TrialStudyInputs struct {
	Plan, Study, Definition                        validation.Value
	Tasks, Runs, ReplacementPlans, CleanupReceipts []validation.Value
	EvidenceByRun                                  map[string]ExperimentEvidenceInputs
}

// ValidateTrialStudy checks study membership and science against exact supplied inputs.
func ValidateTrialStudy(v *Validator, inputs TrialStudyInputs) error {
	plan, err := v.experimentValue(inputs.Plan, trialPlanContract)
	if err != nil {
		return err
	}
	study, err := v.experimentValue(inputs.Study, contractExperimentStudy)
	if err != nil {
		return err
	}
	if err = validateStudyDefinition(v, study, inputs.Definition); err != nil {
		return err
	}
	tasks, err := v.experimentValues(inputs.Tasks, termExperimentTaskV1)
	if err != nil {
		return err
	}
	allRuns, err := v.experimentValues(inputs.Runs, termExperimentRunV1)
	if err != nil {
		return err
	}
	runs, err := v.studyAnalysisRuns(plan, allRuns, inputs)
	if err != nil {
		return err
	}
	sources, err := studyMembership(study, tasks, runs)
	if err != nil {
		return err
	}
	if err = v.validateStudySources(study, sources); err != nil {
		return err
	}
	if err = v.validateStudyEvidence(inputs, sources, tasks, allRuns); err != nil {
		return err
	}
	if err = studyPlanIdentity(plan, study, runs); err != nil {
		return err
	}
	return studyPlanAllocation(plan, study)
}
func (e *Validator) experimentValues(values []validation.Value, id string) ([]any, error) {
	result := make([]any, len(values))
	for index, value := range values {
		view, err := e.experimentValue(value, id)
		if err != nil {
			return nil, err
		}
		result[index] = view
	}
	return result, nil
}
func (e *Validator) studyAnalysisRuns(plan any, runs []any, inputs TrialStudyInputs) ([]any, error) {
	if len(inputs.ReplacementPlans) > 0 || countAt(plan, "replacement_policy", "max_replacements") > 0 {
		return e.replacementStudyRuns(plan, inputs.ReplacementPlans, runs, inputs.CleanupReceipts)
	}
	for _, run := range runs {
		if stringAt(run, "run_status") == statusSuperseded {
			return nil, invalid()
		}
	}
	return runs, nil
}
func (e *Validator) validateStudySources(study any, sources studySources) error {
	if err := e.studyRunTasks(sources); err != nil {
		return err
	}
	if err := studyAnalysis(study, sources); err != nil {
		return err
	}
	if err := studyAllocation(study, sources); err != nil {
		return err
	}
	return studyStochastic(study, sources.evaluation)
}
func (e *Validator) validateStudyEvidence(inputs TrialStudyInputs, sources studySources, tasks, allRuns []any) error {
	for _, run := range sources.runs {
		taskValue, runValue, err := studyEvidenceValues(inputs, run, tasks, allRuns)
		if err != nil {
			return err
		}
		var evidence *ExperimentEvidenceInputs
		if supplied, present := inputs.EvidenceByRun[stringAt(run, termRunID)]; present {
			evidence = &supplied
		}
		if err := ValidateExperimentRun(e, taskValue, runValue, evidence); err != nil {
			return err
		}
	}
	return nil
}

func studyEvidenceValues(inputs TrialStudyInputs, run any, tasks, allRuns []any) (validation.Value, validation.Value, error) {
	var taskValue validation.Value
	matches := 0
	for index, task := range tasks {
		if equal(at(run, "task_ref", fieldRefID), at(task, "task_id")) && equal(at(run, "task_ref", fieldRefVersion), at(task, "task_version")) {
			taskValue = inputs.Tasks[index]
			matches++
		}
	}
	if matches != 1 {
		return validation.Value{}, validation.Value{}, invalid()
	}
	var runValue validation.Value
	for index, candidate := range allRuns {
		if equal(run, candidate) {
			runValue = inputs.Runs[index]
			break
		}
	}
	return taskValue, runValue, nil
}

func validateStudyDefinition(v *Validator, study any, definition validation.Value) error {
	ref := at(study, "definition_ref")
	if ref == nil {
		return nil
	}
	resolved, err := v.experimentValue(definition, contractExperimentStudy)
	if err != nil {
		return err
	}
	if at(resolved, "definition_ref") != nil || !equal(at(ref, fieldRefID), at(resolved, "study_id")) || !equal(at(ref, fieldRefVersion), at(resolved, "study_version")) {
		return invalid()
	}
	raw, err := v.experimentProjection(contractExperimentStudy, definition.JSON())
	if err != nil {
		return err
	}
	var projection any
	if decodeExact(raw, &projection) != nil {
		return invalid()
	}
	digest, err := jsonDigest(projection)
	if err != nil || !equal(at(ref, "ref_digest"), digest) {
		return invalid()
	}
	left, right := maps.Clone(object(study)), maps.Clone(object(resolved))
	for _, key := range []string{"membership", "study_version", "definition_ref"} {
		delete(left, key)
		delete(right, key)
	}
	return require(equal(left, right))
}
func studyPlanIdentity(plan, study any, runs []any) error {
	ref := at(plan, "input_refs", "study_ref")
	version := at(study, "study_version")
	if at(study, "definition_ref") != nil {
		version = at(study, "definition_ref", fieldRefVersion)
	}
	if ref != nil && (!equal(at(ref, fieldRefID), at(study, "study_id")) || at(ref, fieldRefVersion) != nil && !equal(at(ref, fieldRefVersion), version)) {
		return invalid()
	}
	memberIDs := map[string]bool{}
	for _, member := range object(at(study, "membership")) {
		role := stringAt(member, "role")
		if role == "calibration-run" || role == experimentTermEvaluationRun {
			memberIDs[stringAt(member, termTargetRef, fieldRefID)] = true
		}
	}
	for _, run := range runs {
		if at(run, "trial_provenance") != nil && !memberIDs[stringAt(run, termRunID)] {
			return invalid()
		}
	}
	return nil
}
func studyPlanAllocation(plan, study any) error {
	allocation := at(study, "run_allocation")
	if allocation == nil {
		return nil
	}
	counts := map[string]int{}
	for _, entry := range object(at(plan, "entries")) {
		id := stringAt(entry, "coordinate", "condition_id")
		if id == "" {
			continue
		}
		if at(allocation, "condition_assignments", id) == nil {
			return invalid()
		}
		counts[id]++
	}
	for _, count := range counts {
		if numericGreater(json.Number(strconv.Itoa(count)), at(allocation, "target_runs_per_condition")) {
			return invalid()
		}
	}
	return nil
}
