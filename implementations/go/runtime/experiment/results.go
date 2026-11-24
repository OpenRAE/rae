package experiment

import (
	"context"
	"slices"

	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func (c *coordinator) slotResults(ctx context.Context, slot trialSlot, records []Decision) ([]Observation, error) {
	results := []Observation{}
	attempts := slotAttempts(records, c.id, slot.entry.PlanEntryID)
	var source *RecordSource
	for _, attempt := range attempts {
		id := text(attempt, termExecutionAttemptID)
		terminal := findAttemptDecision(records, terminalSchema, id)
		if terminal == nil {
			continue
		}
		if source == nil {
			retained, err := c.recordSource(ctx, slot, records, attempts)
			if err != nil {
				return nil, err
			}
			source = &retained
		}
		observed, err := assembleResult(slot, *source, id, terminal, records)
		if err != nil {
			return nil, err
		}
		results = append(results, observed)
	}
	return results, nil
}
func assembleResult(slot trialSlot, source RecordSource, id string, terminal map[string]any, records []Decision) (Observation, error) {
	observed := attemptObservations(records, id)
	result, err := observationFromMap(object(at(observed[termCleanup], "observation")))
	if err != nil {
		return result, err
	}
	result.CleanupEvidence = result.Evidence
	result.Evidence = nil
	execution := at(observed[termExecution], "observation")
	result.State = text(execution, "state")
	result.Ceased = truth(at(execution, "ceased"))
	result.EffectsAbsent = truth(at(execution, "effects_absent"))
	result.Complete = text(terminal, termCaptureStatus) == termSucceeded
	result.Reusable = truth(terminal["reusable"])
	result.Configurations = slot.realization.ParticipantConfigurations
	result.Snapshot = source.ExecutionSnapshots[id]
	for _, kind := range []string{termConfiguration, termExecution, termCapture, termRetry} {
		if observed[kind] == nil {
			continue
		}
		var evidence []binding.ExperimentEvidenceRecordV1
		if err = convert(at(observed[kind], "observation", termEvidence), &evidence); err != nil {
			return result, err
		}
		result.Evidence = append(result.Evidence, evidence...)
	}
	if text(resultReceiptView(result.CleanupReceipt), "trial_outcome") != result.State {
		return result, integrity()
	}
	if err = validateResultEvidence(source.RunID, result.Evidence); err != nil {
		return result, err
	}
	if err = validateResultEvidence(source.RunID, result.CleanupEvidence); err != nil {
		return result, err
	}
	result.OperationReceipts, err = resultReceipts(source, id)
	if err != nil {
		return result, err
	}
	if err = checkTrialResult(result); err != nil {
		return result, err
	}
	return detachObservation(result)
}
func resultReceiptView(receipt *binding.TrialCleanupReceiptV1) map[string]any {
	view, err := transportView(receipt)
	if err != nil {
		return nil
	}
	return view
}
func validateResultEvidence(runID string, evidence []binding.ExperimentEvidenceRecordV1) error {
	if len(evidence) > 4096 {
		return integrity()
	}
	seen := map[string]bool{}
	for _, record := range evidence {
		view, err := transportView(record)
		if err != nil {
			return err
		}
		id := text(view, "evidence_record_id")
		if seen[id] || text(view, "run_ref", termRefID) != runID {
			return integrity()
		}
		seen[id] = true
	}
	return nil
}
func resultReceipts(source RecordSource, id string) ([]binding.OperationReceiptV1, error) {
	receipts := []binding.OperationReceiptV1{}
	if err := validateObservationReceipts(source.RunID, source.OperationReceipts); err != nil {
		return nil, err
	}
	seen := map[string]bool{}
	for _, receipt := range source.OperationReceipts {
		view, err := transportView(receipt)
		if err != nil {
			return nil, err
		}
		operation := text(view, "operation_id")
		if seen[operation] {
			return nil, integrity()
		}
		seen[operation] = true
		if slices.Contains(source.OperationRefs[id], operation) {
			receipts = append(receipts, receipt)
		}
	}
	return receipts, nil
}

func (c *coordinator) terminalResult(ctx context.Context, slot trialSlot, t Trial, capture string, reusable bool) (Observation, error) {
	records, err := c.load(ctx)
	if err != nil {
		return Observation{}, err
	}
	source, err := c.recordSource(ctx, slot, records, slotAttempts(records, c.id, t.PlanEntryID))
	if err != nil {
		return Observation{}, err
	}
	return assembleResult(slot, source, t.ExecutionAttemptID, map[string]any{termCaptureStatus: capture, "reusable": reusable}, records)
}
