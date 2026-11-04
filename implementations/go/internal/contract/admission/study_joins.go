package admission

import "github.com/OpenRAE/rae/implementations/go/internal/contract/validation"

type studySources struct{ tasks, runs, evaluation, members []any }

func (e *Validator) studyJoins(i validation.Invocation) error {
	v := i.Instance
	if len(object(at(v, "membership"))) == 0 && at(v, "analysis_plan") == nil && at(v, "run_allocation") == nil {
		return nil
	}
	c, ok := i.Context.(ExperimentStudyContext)
	if !ok {
		return contextRequired()
	}
	tasks, err := e.experimentDocuments(termExperimentTaskV1, c.ExperimentTasks())
	if err != nil {
		return err
	}
	runs, err := e.experimentDocuments(termExperimentRunV1, c.ExperimentRuns())
	if err != nil {
		return err
	}
	sources, err := studyMembership(v, tasks, runs)
	if err != nil {
		return err
	}
	if err := e.studyRunTasks(sources); err != nil {
		return err
	}
	if err := studyAnalysis(v, sources); err != nil {
		return err
	}
	if err := studyAllocation(v, sources); err != nil {
		return err
	}
	return studyStochastic(v, sources.evaluation)
}
func studyMembership(v any, tasks, runs []any) (studySources, error) {
	s := studySources{}
	var taskRefs, runRefs, evaluationRefs []any
	for _, member := range object(at(v, "membership")) {
		role, ref := stringAt(member, "role"), at(member, termTargetRef)
		switch role {
		case "primary-task", "comparison-task":
			if len(studyTaskMatches(ref, tasks)) == 0 {
				return s, invalid()
			}
			taskRefs = append(taskRefs, ref)
		case "calibration-run", "evaluation-run":
			if len(studyRunMatches(ref, runs)) == 0 {
				return s, invalid()
			}
			runRefs = append(runRefs, ref)
			if role == "evaluation-run" {
				s.members = append(s.members, member)
				evaluationRefs = append(evaluationRefs, ref)
			}
		}
	}
	s.tasks = studySelectedArtifacts(tasks, taskRefs, kindTask, "task_id", "task_version")
	s.runs = studySelectedArtifacts(runs, runRefs, kindRun, termRunID, "run_version")
	s.evaluation = studySelectedArtifacts(runs, evaluationRefs, kindRun, termRunID, "run_version")
	return s, nil
}
func studySelectedArtifacts(artifacts, refs []any, kind, idField, versionField string) []any {
	selected := make([]any, 0)
	for _, artifact := range artifacts {
		for _, ref := range refs {
			if artifactReferenceMatches(ref, artifact, kind, idField, versionField) {
				selected = append(selected, artifact)
				break
			}
		}
	}
	return selected
}

func (e *Validator) studyRunTasks(s studySources) error {
	byKey := map[string]any{}
	for _, task := range s.tasks {
		byKey[join(stringAt(task, "task_id"), stringAt(task, "task_version"))] = task
	}
	for _, run := range s.runs {
		task := byKey[join(stringAt(run, "task_ref", fieldRefID), stringAt(run, "task_ref", fieldRefVersion))]
		if task == nil {
			return invalid()
		}
		if err := e.taskRunJoin(task, run); err != nil {
			return err
		}
	}
	return nil
}
func studyAnalysis(v any, s studySources) error {
	if at(v, "analysis_plan") == nil {
		return nil
	}
	if len(s.members) == 0 {
		return invalid()
	}
	for _, member := range s.members {
		matches := studyRunMatches(at(member, termTargetRef), s.evaluation)
		if len(matches) != 1 || !analysisEligible(matches[0]) {
			return invalid()
		}
	}
	return studyMetrics(v, s)
}

func studyAllocation(v any, s studySources) error {
	allocation := at(v, "run_allocation")
	if allocation == nil {
		return nil
	}
	if len(s.members) == 0 {
		return invalid()
	}
	counts := map[string]int{}
	seen := map[string]bool{}
	conditions := set(at(allocation, "compared_conditions"))
	for _, member := range s.members {
		if err := studyAllocationMember(member, allocation, s, conditions, counts, seen); err != nil {
			return err
		}
	}
	for condition := range conditions {
		if counts[condition] < countAt(allocation, "target_runs_per_condition") {
			return invalid()
		}
	}
	return nil
}
func studyStochastic(v any, runs []any) error {
	if at(v, "run_allocation") == nil {
		return nil
	}
	identities := map[string]string{}
	unbound := map[string]bool{}
	for _, run := range runs {
		for _, control := range array(at(run, "stochastic_controls")) {
			id := stringAt(control, "control_id")
			binding := at(control, "executable_binding")
			if binding == nil {
				unbound[id] = true
				continue
			}
			identity := join(referenceKey(at(binding, "profile_ref")), stringAt(binding, "namespace"))
			if previous, ok := identities[id]; ok && previous != identity {
				return invalid()
			}
			identities[id] = identity
		}
	}
	for id := range unbound {
		if _, ok := identities[id]; ok {
			return invalid()
		}
	}
	return nil
}

func studyMetrics(v any, s studySources) error {
	metrics := map[string]bool{}
	for _, task := range s.tasks {
		for key := range object(at(task, "evaluation_protocol", "metric_definitions")) {
			metrics[key] = true
		}
	}
	if len(metrics) == 0 || !subset(stringsOf(at(v, "analysis_plan", "metrics")), metrics) {
		return invalid()
	}
	for _, run := range s.evaluation {
		actual := map[string]bool{}
		for _, result := range object(at(run, "result_summaries")) {
			actual[stringAt(result, "metric_id")] = true
		}
		if !subset(stringsOf(at(v, "analysis_plan", "metrics")), actual) {
			return invalid()
		}
	}
	return nil
}

func studyAllocationMember(member, allocation any, s studySources, conditions map[string]bool, counts map[string]int, seen map[string]bool) error {
	group := stringAt(member, "grouping")
	if !conditions[group] {
		return invalid()
	}
	matches := studyRunMatches(at(member, termTargetRef), s.evaluation)
	if len(matches) != 1 {
		return invalid()
	}
	run := matches[0]
	key := join(stringAt(run, termRunID), stringAt(run, "run_version"))
	if seen[key] || !analysisEligible(run) {
		return invalid()
	}
	seen[key] = true
	if !runCondition(run, at(allocation, "condition_assignments", group)) {
		return invalid()
	}
	for id, assignment := range object(at(allocation, "condition_assignments")) {
		if id != group && runCondition(run, assignment) {
			return invalid()
		}
	}
	counts[group]++
	return nil
}
