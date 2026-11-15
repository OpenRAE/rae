package experiment

import (
	"context"
	"encoding/json"
	"io"
	"maps"
	"slices"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/digest"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

func (c *coordinator) assembleStudy(ctx context.Context, bundle *RecordBundle, definition binding.ExperimentStudyV1, reader EvidenceReader, records []Decision) error {
	view, err := c.authoredStudy(definition)
	if err != nil {
		return err
	}
	if _, err = c.claim(ctx, studySchema, map[string]any{termExperimentID: c.id, termStudy: view}); err != nil {
		return err
	}
	definitionView, err := transportView(view)
	if err != nil {
		return err
	}
	members := object(view["membership"])
	if members == nil {
		members = map[string]any{}
	}
	for index := range bundle.Runs {
		if err = addStudyRun(members, *bundle, index); err != nil {
			return err
		}
	}
	definitionRaw, err := canonical(definitionView)
	if err != nil {
		return err
	}
	view["definition_ref"] = map[string]any{termRefKind: termStudy, termRefID: view["study_id"], termRefVersion: view["study_version"], termRefDigest: digest.SHA256(definitionRaw)}
	view["membership"] = members
	hashRaw, err := canonical(view)
	if err != nil {
		return err
	}
	view["study_version"] = text(view, "study_version") + "-" + strings.TrimPrefix(digest.SHA256(hashRaw), "sha256:")
	snapshotRaw, err := json.Marshal(view)
	if err != nil {
		return err
	}
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	snapshotRaw, err = admission.ExperimentModelProjection(owner, contractExperimentStudy, snapshotRaw)
	if err != nil {
		return err
	}
	var snapshot binding.ExperimentStudyV1
	if json.Unmarshal(snapshotRaw, &snapshot) != nil {
		return integrity()
	}
	bundle.Study = &snapshot
	bundle.StudyValidation = termPassed
	if err = c.validateStudy(ctx, *bundle, definitionView, reader, records); err != nil {
		bundle.StudyValidation = termFailed
		bundle.ValidationFailures[termStudy] = []string{"study-validation-failed"}
	}
	return nil
}
func (c *coordinator) authoredStudy(definition binding.ExperimentStudyV1) (map[string]any, error) {
	owner, err := experimentOwner()
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(definition)
	if err != nil {
		return nil, err
	}
	raw, err = admission.ExperimentModelProjection(owner, contractExperimentStudy, raw)
	if err != nil {
		return nil, err
	}
	var view map[string]any
	if json.Unmarshal(raw, &view) != nil || view["definition_ref"] != nil {
		return nil, integrity()
	}
	root, err := transportView(c.options.Inputs.Plan)
	if err != nil {
		return nil, err
	}
	if ref := at(root, "input_refs", "study_ref"); ref != nil {
		if text(ref, termRefID) != text(view, "study_id") || at(ref, termRefVersion) != nil && text(ref, termRefVersion) != text(view, "study_version") {
			return nil, integrity()
		}
	}
	return view, nil
}
func addStudyRun(members map[string]any, bundle RecordBundle, index int) error {
	runView, viewErr := transportView(bundle.Runs[index])
	if viewErr != nil {
		return viewErr
	}
	id := text(runView, termRunID)
	key := "runtime:" + id
	if _, exists := members[key]; exists {
		return integrity()
	}
	sourcePlan, _ := transportView(bundle.Sources[index].Plan)
	entryID := text(decisionMap(bundle.Sources[index].Attempts[0]), termPlanEntryID)
	role, rationale := "other", "Retained execution; scientific eligibility not established."
	if slices.Contains(bundle.EligibleRunIDs, id) {
		role, rationale = "evaluation-run", "Validated evaluation run."
		checked, checkedErr := transportView(bundle.ValidationRecords[index])
		if checkedErr != nil {
			return checkedErr
		}
		if text(checked, "run_version") != text(runView, "run_version") {
			accountingKey := key + ":accounting"
			if _, exists := members[accountingKey]; exists {
				return integrity()
			}
			members[accountingKey] = map[string]any{"target_ref": map[string]any{termRefKind: termRun, termRefID: id, termRefVersion: runView["run_version"]}, "role": "other", "grouping": at(sourcePlan, "entries", entryID, "coordinate", "condition_id"), "inclusion_rationale": "Additional accounting linked to the exact evaluation artifact."}
		}
		runView = checked
	}
	members[key] = map[string]any{"target_ref": map[string]any{termRefKind: termRun, termRefID: id, termRefVersion: at(runView, "run_version")}, "role": role, "grouping": at(sourcePlan, "entries", entryID, "coordinate", "condition_id"), "inclusion_rationale": rationale}
	return nil
}

type studyValidation struct {
	coordinator *coordinator
	bundle      RecordBundle
	owner       *admission.Validator
	inputs      admission.TrialStudyInputs
	authority   recordContext
	closers     []io.Closer
	versions    map[string]any
	plans       []any
}

func (c *coordinator) validateStudy(ctx context.Context, bundle RecordBundle, definition any, reader EvidenceReader, records []Decision) error {
	if len(bundle.Runs) > 0 && len(bundle.EligibleRunIDs) == 0 {
		return integrity()
	}
	_, err := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (result struct{}, checkErr error) {
		check := studyValidation{coordinator: c, bundle: bundle, versions: map[string]any{}}
		defer func() {
			if closeErr := closeReaders(work, check.closers); checkErr == nil {
				checkErr = closeErr
			}
		}()
		if checkErr = check.prepare(); checkErr != nil {
			return result, checkErr
		}
		if checkErr = check.evaluationRuns(work, reader); checkErr != nil {
			return result, checkErr
		}
		if checkErr = check.replacementHistory(records); checkErr != nil {
			return result, checkErr
		}
		if checkErr = check.studyModels(definition); checkErr != nil {
			return result, checkErr
		}
		return result, admission.ValidateTrialStudy(check.owner, check.inputs)
	})
	return err
}
func (s *studyValidation) prepare() error {
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	s.owner = owner
	plan, err := planAdmission(s.coordinator.options.Inputs.Plan)
	if err != nil {
		return err
	}
	s.inputs = admission.TrialStudyInputs{Plan: plan, EvidenceByRun: map[string]admission.ExperimentEvidenceInputs{}}
	s.authority.task, err = json.Marshal(s.coordinator.options.Inputs.Task)
	if err != nil {
		return err
	}
	s.authority.tasks = [][]byte{s.authority.task}
	task, err := owner.Validate("experiment-task-v1", s.authority.task, runtimeIngress(), s.authority)
	if err != nil {
		return err
	}
	s.inputs.Tasks = []validation.Value{task}
	root, err := transportView(s.coordinator.options.Inputs.Plan)
	if err != nil {
		return err
	}
	s.plans = []any{root}
	return nil
}
func (s *studyValidation) evaluationRuns(ctx context.Context, reader EvidenceReader) error {
	for index, run := range s.bundle.ValidationRecords {
		view, err := transportView(run)
		if err != nil {
			return err
		}
		id := text(view, termRunID)
		if !slices.Contains(s.bundle.EligibleRunIDs, id) {
			continue
		}
		source := s.bundle.Sources[index]
		evidence, closers, err := s.coordinator.openEvidence(ctx, source, run, reader)
		s.closers = append(s.closers, closers...)
		if err != nil {
			return err
		}
		if evidence != nil {
			s.inputs.EvidenceByRun[id] = *evidence
		}
		if err = s.addRun(view); err != nil {
			return err
		}
	}
	return nil
}
func (s *studyValidation) addRun(view map[string]any) error {
	key := versionKey(termRun, view)
	if prior, exists := s.versions[key]; exists {
		if !same(prior, view) {
			return integrity()
		}
		return nil
	}
	for _, source := range s.bundle.Sources {
		if source.RunID != text(view, termRunID) {
			continue
		}
		authority, err := s.coordinator.recordContext(source)
		if err != nil {
			return err
		}
		raw, err := json.Marshal(view)
		if err != nil {
			return err
		}
		value, err := s.owner.Validate(contractExperimentRun, raw, runtimeIngress(), authority)
		if err != nil {
			return err
		}
		s.inputs.Runs = append(s.inputs.Runs, value)
		s.authority.runs = append(s.authority.runs, raw)
		s.versions[key] = view
		return nil
	}
	return integrity()
}
func (s *studyValidation) replacementHistory(records []Decision) error {
	root := s.plans[0]
	if integer(at(root, "replacement_policy", "max_replacements")) == 0 {
		return nil
	}
	history, err := retainedStudyRuns(records, s.coordinator.id)
	if err != nil {
		return err
	}
	for _, record := range records {
		m := decisionMap(record)
		if record.SchemaVersion() != replacementSchema || text(m, termExperimentID) != s.coordinator.id {
			continue
		}
		raw, encodeErr := json.Marshal(m["plan"])
		if encodeErr != nil {
			return encodeErr
		}
		child, childErr := s.owner.Validate("admitted-trial-plan-v1", raw, runtimeIngress(), nil)
		if childErr != nil {
			return childErr
		}
		s.inputs.ReplacementPlans = append(s.inputs.ReplacementPlans, child)
		s.plans = append(s.plans, m["plan"])
	}
	for _, key := range slices.Sorted(maps.Keys(history)) {
		if err = s.addRun(object(history[key])); err != nil {
			return err
		}
	}
	return s.cleanupReceipts()
}
func retainedStudyRuns(records []Decision, id string) (map[string]any, error) {
	runs := map[string]any{}
	for _, record := range records {
		m := decisionMap(record)
		if text(m, termExperimentID) != id {
			continue
		}
		var subjects []any
		switch record.SchemaVersion() {
		case replacementSchema:
			subjects = []any{m["parent_run"], m["superseded_run"]}
		case candidateSchema, archiveSchema:
			subjects = []any{m[termRun]}
		default:
			continue
		}
		for _, run := range subjects {
			if err := retainVersion(runs, termRun, run); err != nil {
				return nil, err
			}
		}
	}
	return runs, nil
}
func (s *studyValidation) cleanupReceipts() error {
	for _, source := range s.bundle.Sources {
		for _, raw := range sourceReceipts(source) {
			view, err := transportView(json.RawMessage(raw))
			if err != nil {
				return err
			}
			plan, err := studyCleanupPlan(s.plans, text(view, "cleanup_plan_ref"))
			if err != nil {
				return err
			}
			value, err := s.owner.Validate(contractTrialCleanupReceipt, raw, runtimeIngress(), cleanupContext{plan})
			if err != nil {
				return err
			}
			s.inputs.CleanupReceipts = append(s.inputs.CleanupReceipts, value)
		}
	}
	return nil
}
func studyCleanupPlan(plans []any, id string) ([]byte, error) {
	var found any
	for _, plan := range plans {
		candidate := at(plan, "cleanup_plans", id)
		if candidate == nil {
			continue
		}
		if found != nil && !same(found, candidate) {
			return nil, integrity()
		}
		found = candidate
	}
	if found == nil {
		return nil, integrity()
	}
	return json.Marshal(found)
}
func (s *studyValidation) studyModels(definition any) error {
	raw, err := json.Marshal(s.bundle.Study)
	if err != nil {
		return err
	}
	s.inputs.Study, err = s.owner.Validate(contractExperimentStudy, raw, runtimeIngress(), s.authority)
	if err != nil {
		return err
	}
	raw, err = json.Marshal(definition)
	if err != nil {
		return err
	}
	s.inputs.Definition, err = s.owner.Validate(contractExperimentStudy, raw, runtimeIngress(), s.authority)
	return err
}
