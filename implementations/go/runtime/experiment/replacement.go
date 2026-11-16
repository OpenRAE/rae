package experiment

import (
	"context"
	"encoding/json"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/processor/trial"
)

func (c *coordinator) restoreChildren(ctx context.Context, records []Decision) error {
	children := []map[string]any{}
	for _, record := range records {
		if record.SchemaVersion() == replacementSchema {
			m := decisionMap(record)
			if text(m, termExperimentID) == c.id {
				children = append(children, m)
			}
		}
	}
	ranks := map[string]int{}
	for _, entry := range c.schedule.Entries {
		ranks[entry.PlanEntryID] = entry.DispatchOrdinal
	}
	slices.SortStableFunc(children, func(a, b map[string]any) int {
		if rank := ranks[text(a, "root_entry_id")] - ranks[text(b, "root_entry_id")]; rank != 0 {
			return rank
		}
		return integer(a["ordinal"]) - integer(b["ordinal"])
	})
	for _, child := range children {
		if err := c.restoreChild(ctx, child); err != nil {
			return err
		}
	}

	return nil
}
func (c *coordinator) replace(ctx context.Context, s trialSlot, t Trial, records []Decision, allowed bool) (bool, error) {
	if c.options.Replacement == nil {
		return false, nil
	}
	archive := c.options.Archive
	if archive == nil {
		return false, invalidOptions()
	}
	run, err := c.archiveRun(ctx, s, t, records, archive)
	if err != nil {
		return false, err
	}
	if !allowed {
		return false, nil
	}
	root, err := transportView(c.options.Inputs.Plan)
	if err != nil {
		return false, err
	}
	runView, err := transportView(run)
	if err != nil {
		return false, err
	}
	if !slices.Contains(array(at(root, "replacement_policy", "replace_on")), any(text(runView, "run_status"))) {
		return false, nil
	}
	history, replayed, err := c.replacementHistory(ctx, s, t, records, archive)
	if err != nil || replayed {
		return false, err
	}
	if len(history) >= integer(at(root, "replacement_policy", "max_replacements")) {
		return false, nil
	}
	return c.allocateChild(ctx, s, t, records, archive, history, run)
}

func (c *coordinator) archiveRun(ctx context.Context, s trialSlot, t Trial, records []Decision, archive Archive) (binding.ExperimentRunV1, error) {
	run, archived, err := retainedArchiveRun(records, c.id, t.RunID)
	if err != nil || archived {
		return run, err
	}
	source, err := c.recordSource(ctx, s, records, slotAttempts(records, c.id, t.PlanEntryID))
	if err != nil {
		return run, err
	}
	if run.RunId.IsZero() {
		run, err = ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (binding.ExperimentRunV1, error) {
			detached, copyErr := detachSource(source)
			if copyErr != nil {
				return binding.ExperimentRunV1{}, copyErr
			}
			return archive.BuildRun(work, detached)
		})
		if err != nil {
			return run, err
		}
	}
	view, err := c.validateArchiveCandidate(s, source, run, records)
	if err != nil {
		return run, err
	}
	if _, err = c.claim(ctx, candidateSchema, map[string]any{termExperimentID: c.id, termRun: view}); err != nil {
		return run, err
	}
	if err = c.writeAndRead(ctx, archive, map[string]any{termRun: view}); err != nil {
		return run, err
	}
	if _, err = c.claim(ctx, archiveSchema, map[string]any{termExperimentID: c.id, termRun: view}); err != nil {
		return run, err
	}
	err = convert(view, &run)
	return run, err
}
func cleanupDTOs(source RecordSource) ([]binding.TrialCleanupReceiptV1, error) {
	result := []binding.TrialCleanupReceiptV1{}
	for _, raw := range sourceReceipts(source) {
		var receipt binding.TrialCleanupReceiptV1
		if json.Unmarshal(raw, &receipt) != nil {
			return nil, integrity()
		}
		result = append(result, receipt)
	}
	return result, nil
}
func archiveMatchesSource(run any, source RecordSource) bool {
	attempts := array(at(run, "trial_provenance", "execution_attempts"))
	if len(attempts) != len(source.Attempts) {
		return false
	}
	for index, decision := range source.Attempts {
		m := decisionMap(decision)
		id := text(m, termExecutionAttemptID)
		if text(attempts[index], termExecutionAttemptID) != id {
			return false
		}
		observed := attemptObservations(source.Observations, id)
		if text(attempts[index], "cleanup_receipt_ref") != text(observed[termCleanup], "observation", "receipt", "receipt_id") {
			return false
		}
		expected := nonNilStrings(source.OperationRefs[id])
		var actual []string
		raw, marshalErr := json.Marshal(at(attempts[index], termOperationRefs))
		if marshalErr != nil {
			return false
		}
		if json.Unmarshal(raw, &actual) != nil {
			return false
		}
		slices.Sort(expected)
		slices.Sort(actual)
		if !slices.Equal(expected, actual) {
			return false
		}
		if !truth(at(observed[termCapture], "observation", "complete")) && text(run, "run_status") == termCompleted {
			return false
		}
	}
	return true
}

func (c *coordinator) restoreChild(ctx context.Context, child map[string]any) error {
	exists := false
	for _, slot := range c.slotSnapshot() {
		view, _ := transportView(slot.plan)
		exists = exists || text(view, termPlanID) == text(child, "plan", termPlanID)
	}
	if exists {
		return nil
	}
	if c.options.Replacement == nil {
		return integrity()
	}
	var plan binding.AdmittedTrialPlanV1
	if convert(child["plan"], &plan) != nil {
		return integrity()
	}
	slots, err := c.planSlots(ctx, plan, text(child, "root_entry_id"))
	if err != nil {
		return err
	}
	if len(slots) != 1 {
		return integrity()
	}
	if err = c.appendSlots(slots); err != nil {
		return err
	}
	return nil
}

func (c *coordinator) replacementHistory(ctx context.Context, s trialSlot, t Trial, records []Decision, archive Archive) ([]trial.ReplacementResult, bool, error) {
	history := []trial.ReplacementResult{}
	for _, record := range records {
		if record.SchemaVersion() != replacementSchema {
			continue
		}
		m := decisionMap(record)
		if text(m, termExperimentID) != c.id || text(m, "root_entry_id") != s.root {
			continue
		}
		if text(m, "parent_run", termRunID) == t.RunID {
			return nil, true, c.writeAndRead(ctx, archive, map[string]any{termRun: m["superseded_run"]})
		}
		var result trial.ReplacementResult
		result.Plan = new(binding.AdmittedTrialPlanV1)
		result.ParentRun = new(binding.ExperimentRunV1)
		result.SupersededRun = new(binding.ExperimentRunV1)
		if convert(m["plan"], result.Plan) != nil || convert(m["parent_run"], result.ParentRun) != nil || convert(m["superseded_run"], result.SupersededRun) != nil || convert(m["cleanup_receipts"], &result.CleanupReceipts) != nil {
			return nil, false, integrity()
		}
		history = append(history, result)
	}
	slices.SortFunc(history, func(a, b trial.ReplacementResult) int {
		av, _ := transportView(a.Plan)
		bv, _ := transportView(b.Plan)
		return integer(at(av, "replacement_origin", "ordinal")) - integer(at(bv, "replacement_origin", "ordinal"))
	})

	return history, false, nil
}

func (c *coordinator) allocateChild(ctx context.Context, s trialSlot, t Trial, records []Decision, archive Archive, history []trial.ReplacementResult, run binding.ExperimentRunV1) (bool, error) {
	source, err := c.recordSource(ctx, s, records, slotAttempts(records, c.id, t.PlanEntryID))
	if err != nil {
		return false, err
	}
	receipts, err := cleanupDTOs(source)
	if err != nil {
		return false, err
	}
	result, err := trial.CompileReplacement(ctx, trial.ReplacementRequest{Compilation: *c.options.Replacement, OriginalPlan: c.options.Inputs.Plan, RootEntryID: s.root, ParentRun: run, CleanupReceipts: receipts, PreviousAllocations: history})
	if err != nil {
		return false, err
	}
	if result.Plan == nil {
		return false, integrity()
	}
	versions, err := retainedVersions(records, c.id)
	if err != nil {
		return false, err
	}
	superseded, err := transportView(result.SupersededRun)
	if err != nil {
		return false, err
	}
	if err = retainVersion(versions, termRun, superseded); err != nil {
		return false, err
	}
	childView, err := transportView(result.Plan)
	if err != nil {
		return false, err
	}
	_, err = c.claim(ctx, replacementSchema, map[string]any{termExperimentID: c.id, "root_entry_id": s.root, "ordinal": at(childView, "replacement_origin", "ordinal"), "plan": result.Plan, "superseded_run": result.SupersededRun, "parent_run": result.ParentRun, "cleanup_receipts": result.CleanupReceipts})
	if err != nil {
		return false, err
	}
	if err = c.writeAndRead(ctx, archive, map[string]any{termRun: superseded}); err != nil {
		return false, err
	}
	return true, nil
}
func (c *coordinator) validateArchiveCandidate(s trialSlot, source RecordSource, run binding.ExperimentRunV1, records []Decision) (map[string]any, error) {
	plan, err := planAdmission(s.plan)
	if err != nil {
		return nil, err
	}
	owner, err := experimentOwner()
	if err != nil {
		return nil, err
	}
	raw, err := json.Marshal(run)
	if err != nil {
		return nil, err
	}
	projected, err := admission.ExperimentModelProjection(owner, "experiment-run-v1", raw)
	if err != nil {
		return nil, err
	}
	if err = admission.ValidateTrialRunJSON(owner, plan, projected, sourceReceipts(source)); err != nil {
		return nil, err
	}
	view, err := transportView(json.RawMessage(projected))
	if err != nil {
		return nil, err
	}
	if !archiveMatchesSource(view, source) {
		return nil, integrity()
	}
	versions, err := retainedVersions(records, c.id)
	if err != nil {
		return nil, err
	}
	if err = retainVersion(versions, termRun, view); err != nil {
		return nil, err
	}

	return view, nil
}

func retainedArchiveRun(records []Decision, experimentID, runID string) (binding.ExperimentRunV1, bool, error) {
	var run binding.ExperimentRunV1
	for _, record := range records {
		schema := record.SchemaVersion()
		if schema != archiveSchema && schema != candidateSchema {
			continue
		}
		m := decisionMap(record)
		if text(m, termExperimentID) != experimentID || text(m, termRun, termRunID) != runID {
			continue
		}
		if convert(m[termRun], &run) != nil {
			return run, false, integrity()
		}
		if schema == archiveSchema {
			return run, true, nil
		}
	}
	return run, false, nil
}
