package trial

import (
	"context"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

func allocateReplacement(ctx context.Context, request ReplacementRequest) (ReplacementResult, error) {
	root, policy, err := replacementRoot(ctx, request)
	if err != nil {
		return ReplacementResult{}, err
	}
	run, err := archiveForReplacement(request.ParentRun)
	if err != nil {
		return ReplacementResult{}, err
	}
	receipts, err := receiptsForReplacement(request.CleanupReceipts)
	if err != nil {
		return ReplacementResult{}, err
	}
	history := replacementHistoryState{parent: root}
	for index, prior := range request.PreviousAllocations {
		if err = history.observe(ctx, request, root, policy, prior, index, replacementEvidence{run, receipts}); err != nil {
			return ReplacementResult{}, err
		}
	}
	if history.replay != nil {
		return *history.replay, nil
	}
	if len(request.PreviousAllocations) >= policy.Maximum {
		return ReplacementResult{}, replacementRefusal("limit-exhausted", "the original allocation slot has exhausted its replacement limit")
	}
	compilation, err := contextForReplacement(request.Compilation, root, history.parent, request.RootEntryID, policy, replacementEvidence{run, receipts}, len(request.PreviousAllocations)+1)
	if err != nil {
		return ReplacementResult{}, err
	}
	child, err := compilePlanWithReplacement(ctx, request.Compilation, &compilation)
	if err != nil {
		return ReplacementResult{}, err
	}
	return replacementDecision(child, run, receipts)
}
func validatePreviousReplacement(ctx context.Context, request ReplacementRequest, root, parent trialPlan, policy replacementPolicy, prior ReplacementResult, ordinal int) (binding.AdmittedTrialPlanV1, replacementArchive, []replacementReceipt, error) {
	oldRun, err := archiveForReplacement(*prior.ParentRun)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, oldRun, nil, err
	}
	oldReceipts, err := receiptsForReplacement(prior.CleanupReceipts)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, oldRun, nil, err
	}
	child, err := admitPlan(*prior.Plan)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, oldRun, nil, err
	}
	compilation, err := contextForReplacement(request.Compilation, root, parent, request.RootEntryID, policy, replacementEvidence{oldRun, oldReceipts}, ordinal)
	if err != nil {
		return binding.AdmittedTrialPlanV1{}, oldRun, nil, err
	}
	expected, err := compilePlanWithReplacement(ctx, request.Compilation, &compilation)
	if err != nil {
		return expected, oldRun, nil, err
	}
	raw, err := encoded(expected)
	if err != nil {
		return expected, oldRun, nil, err
	}
	var plan trialPlan
	if decode(raw, &plan) != nil {
		return expected, oldRun, nil, trialInvalid()
	}
	var admitted trialPlan
	if decode(child.JSON(), &admitted) != nil {
		return expected, oldRun, nil, trialInvalid()
	}
	superseded, err := supersedeReplacementRun(oldRun, expected)
	if err != nil {
		return expected, oldRun, nil, err
	}
	a, err := encoded(superseded)
	if err != nil {
		return expected, oldRun, nil, err
	}
	b, err := encoded(prior.SupersededRun)
	if err != nil {
		return expected, oldRun, nil, err
	}
	if admitted.Digest != plan.Digest || !sameJSON(a, b) {
		return expected, oldRun, nil, replacementRefusal("history-invalid", "replacement history does not match its exact admitted lineage")
	}
	return expected, oldRun, oldReceipts, nil
}
func sameReplacementReceipts(a, b []replacementReceipt) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if !sameJSON(a[i].raw, b[i].raw) {
			return false
		}
	}
	return true
}
func replacementDecision(child binding.AdmittedTrialPlanV1, parent replacementArchive, receipts []replacementReceipt) (ReplacementResult, error) {
	superseded, err := supersedeReplacementRun(parent, child)
	if err != nil {
		return ReplacementResult{}, err
	}
	retained := make([]binding.TrialCleanupReceiptV1, len(receipts))
	for index, receipt := range receipts {
		retained[index] = receipt.value
	}
	return ReplacementResult{Plan: &child, SupersededRun: &superseded, ParentRun: &parent.run, CleanupReceipts: retained, Diagnostics: []diagnostic.Diagnostic{}}, nil
}
func supersedeReplacementRun(run replacementArchive, child binding.AdmittedTrialPlanV1) (binding.ExperimentRunV1, error) {
	var result binding.ExperimentRunV1
	plan, err := admitPlan(child)
	if err != nil {
		return result, err
	}
	owner, err := trialOwner()
	if err != nil {
		return result, err
	}
	raw, err := admission.SupersedeTrialRunJSON(owner, run.raw, plan)
	if err != nil {
		return result, err
	}
	err = decode(raw, &result)
	return result, err
}

type replacementHistoryState struct {
	parent trialPlan
	total  int
	replay *ReplacementResult
}

func (history *replacementHistoryState) observe(ctx context.Context, request ReplacementRequest, root trialPlan, policy replacementPolicy, prior ReplacementResult, index int, evidence replacementEvidence) error {
	if err := ctx.Err(); err != nil {
		return err
	}
	if prior.Plan == nil || prior.ParentRun == nil || prior.SupersededRun == nil || len(prior.Diagnostics) > 0 {
		return replacementRefusal("history-invalid", "replacement history contains an uncommitted allocation")
	}
	raw, checkErr := canonical(prior.Plan)
	if checkErr != nil {
		return checkErr
	}
	if len(raw) > request.Compilation.Limits.MaxPlanBytes-history.total {
		return replacementRefusal("history-limit-exceeded", "replacement history exceeds the compilation byte limit")
	}
	history.total += len(raw)
	child, oldRun, oldReceipts, checkErr := validatePreviousReplacement(ctx, request, root, history.parent, policy, prior, index+1)
	if checkErr != nil {
		return checkErr
	}
	if evidence.run.id == oldRun.id {
		if !sameJSON(evidence.run.raw, oldRun.raw) || !sameReplacementReceipts(evidence.receipts, oldReceipts) {
			return replacementRefusal("decision-conflict", "a committed replacement has different parent evidence")
		}
		decision, checkErr2 := replacementDecision(child, oldRun, oldReceipts)
		if checkErr2 != nil {
			return checkErr2
		}
		history.replay = &decision
	}
	raw, checkErr = encoded(child)
	if checkErr != nil {
		return checkErr
	}
	var next trialPlan
	if decode(raw, &next) != nil {
		return trialInvalid()
	}
	history.parent = next
	return nil
}
