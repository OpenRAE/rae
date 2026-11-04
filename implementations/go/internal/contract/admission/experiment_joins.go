package admission

import (
	"strings"

	"github.com/OpenRAE/rae/implementations/go/internal/contract/validation"
)

func (e *Validator) experimentJoinRules() map[string]definition {
	return map[string]definition{
		"task-run-protocol-binding-valid":                          {check: e.taskRun, contextual: true, requiresContext: true},
		"study-analysis-metrics-grounded-in-task-protocols":        {check: e.studyJoins, contextual: true},
		"study-analysis-metrics-covered-by-evaluation-run-results": {check: e.studyJoins, contextual: true},
		"study-analysis-runs-eligible":                             {check: e.studyJoins, contextual: true},
		"study-run-allocation-covered-by-evaluation-run-members":   {check: e.studyJoins, contextual: true},
		"study-run-allocation-stochastic-control-consistency":      {check: e.studyJoins, contextual: true},
	}
}
func (e *Validator) taskRun(i validation.Invocation) error {
	c, ok := i.Context.(ExperimentTaskContext)
	if !ok {
		return contextRequired()
	}
	task, err := e.contextDocument(termExperimentTaskV1, c.ExperimentTask())
	if err != nil {
		return err
	}
	return e.taskRunJoin(task, i.Instance)
}
func referenceSatisfies(candidate, requirement any) bool {
	for work := 0; requirement != nil; work++ {
		if work >= 64 || candidate == nil || !matchingFields(candidate, requirement, fieldRefKind, fieldRefID) {
			return false
		}
		for _, field := range []string{fieldRefVersion, "ref_path"} {
			if at(requirement, field) != nil && !equal(at(candidate, field), at(requirement, field)) {
				return false
			}
		}
		if at(requirement, "ref_digest") != nil && !strings.EqualFold(stringAt(requirement, "ref_digest"), stringAt(candidate, "ref_digest")) {
			return false
		}
		candidate, requirement = at(candidate, "subject_ref"), at(requirement, "subject_ref")
	}
	return true
}
func identityMatches(identity, reference any) bool {
	return at(reference, "ref_digest") == nil && at(reference, "ref_path") == nil && stringAt(identity, termName) == stringAt(reference, fieldRefID) && (at(reference, fieldRefVersion) == nil || equal(at(identity, "version"), at(reference, fieldRefVersion)))
}
func referenceIn(rows, requirement any) bool {
	for _, ref := range array(rows) {
		if referenceSatisfies(ref, requirement) {
			return true
		}
	}
	return false
}
func (e *Validator) taskRunJoin(task, run any) error {
	if stringAt(run, "record_state") == statusPartial || !equal(at(run, "task_ref", fieldRefID), at(task, "task_id")) || !equal(at(run, "task_ref", fieldRefVersion), at(task, "task_version")) {
		return invalid()
	}
	if stringAt(task, "scenario_ref", fieldRefKind) == kindScenarioSnapshot {
		if !referenceSatisfies(at(run, "scenario_snapshot_ref"), at(task, "scenario_ref")) {
			return invalid()
		}
	} else if !equal(at(run, "scenario_snapshot_ref", fieldRefID), at(task, "scenario_ref", fieldRefID)) {
		return invalid()
	}
	if at(task, "apparatus_constraints") != nil {
		if err := apparatusSatisfies(at(task, "apparatus_constraints"), at(run, "apparatus_context")); err != nil {
			return err
		}
	}
	for _, result := range object(at(run, "result_summaries")) {
		if at(task, "evaluation_protocol", "metric_definitions", stringAt(result, "metric_id")) == nil {
			return invalid()
		}
	}
	return e.stochasticDraws(validation.Invocation{Instance: run})
}
func apparatusSatisfies(constraints, apparatus any) error {
	if err := apparatusAllowedIdentities(constraints, apparatus); err != nil {
		return err
	}
	for _, ref := range array(at(constraints, "required_manifest_refs")) {
		if !referenceIn(at(apparatus, "selected_manifests"), ref) {
			return invalid()
		}
	}
	available := map[string]bool{}
	add := func(rows any) {
		for _, ref := range array(rows) {
			if stringAt(ref, fieldRefKind) == "capability" {
				available[stringAt(ref, fieldRefID)] = true
			}
		}
	}
	add(at(apparatus, "compatibility_declarations"))
	for _, component := range object(at(apparatus, termComponents)) {
		add(at(component, "compatibility_refs"))
	}
	return require(subset(stringsOf(at(constraints, "required_capabilities")), available))
}

func (e *Validator) experimentDocuments(id string, raw [][]byte) ([]any, error) {
	if len(raw) > 4096 {
		return nil, invalid()
	}
	remaining := 64 * 1048576
	result := make([]any, 0, len(raw))
	for _, data := range raw {
		if len(data) > remaining {
			return nil, invalid()
		}
		remaining -= len(data)
		v, err := e.contextDocument(id, data)
		if err != nil {
			return nil, err
		}
		result = append(result, v)
	}
	return result, nil
}
func artifactReferenceMatches(ref, artifact any, kind, idField, versionField string) bool {
	return at(ref, "ref_digest") == nil && at(ref, "ref_path") == nil && stringAt(ref, fieldRefKind) == kind && equal(at(ref, fieldRefID), at(artifact, idField)) && (at(ref, fieldRefVersion) == nil || equal(at(ref, fieldRefVersion), at(artifact, versionField)))
}
func studyRunMatches(ref any, runs []any) []any {
	var matches []any
	for _, run := range runs {
		if artifactReferenceMatches(ref, run, kindRun, termRunID, "run_version") {
			matches = append(matches, run)
		}
	}
	return matches
}
func studyTaskMatches(ref any, tasks []any) []any {
	var matches []any
	for _, task := range tasks {
		if artifactReferenceMatches(ref, task, kindTask, "task_id", "task_version") {
			matches = append(matches, task)
		}
	}
	return matches
}
func analysisEligible(run any) bool {
	return text(defaultMember(run, "record_state", "archival")) == "archival" && stringAt(run, "run_status") != "invalidated" && stringAt(run, "run_status") != statusSuperseded && stringAt(run, "outcome_status") != "not-evaluated"
}

func apparatusAllowedIdentities(constraints, apparatus any) error {
	for _, kind := range []string{kindProcessor, kindBackend} {
		refs := array(at(constraints, "allowed_"+kind+"_refs"))
		if len(refs) == 0 {
			continue
		}
		matched := false
		for _, ref := range refs {
			if identityMatches(at(apparatus, termComponents, kind, termIdentity), ref) {
				matched = true
			}
		}
		if !matched {
			return invalid()
		}
	}
	return nil
}
