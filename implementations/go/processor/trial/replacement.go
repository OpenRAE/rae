package trial

import (
	"context"
	"encoding/json"
	"errors"
	"slices"
	"strconv"
	"strings"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/diagnostic"
)

type replacementOrigin struct {
	RootPlanID       string `json:"root_plan_id"`
	RootPlanDigest   string `json:"root_plan_digest"`
	RootEntryID      string `json:"root_entry_id"`
	Ordinal          int    `json:"ordinal"`
	ParentPlanID     string `json:"parent_plan_id"`
	ParentPlanDigest string `json:"parent_plan_digest"`
	ParentEntryID    string `json:"parent_entry_id"`
	ParentRunID      string `json:"parent_run_id"`
	ParentRunVersion string `json:"parent_run_version"`
	ParentRunDigest  string `json:"parent_run_digest"`
	Receipt          string `json:"cleanup_receipt_ref"`
}
type replacementPolicy struct {
	Maximum  int      `json:"max_replacements"`
	Triggers []string `json:"replace_on"`
}
type replacementContext struct {
	origin         replacementOrigin
	index, maximum int
}

func (r replacementContext) planID() (string, error) {
	return identity("replacement-plan", struct {
		Profile string `json:"profile"`
		Root    string `json:"root_plan_id"`
		Digest  string `json:"root_plan_digest"`
		Entry   string `json:"root_entry_id"`
		Ordinal int    `json:"ordinal"`
	}{"trial-compiler-replacement-v1", r.origin.RootPlanID, r.origin.RootPlanDigest, r.origin.RootEntryID, r.origin.Ordinal}, false)
}
func (r replacementContext) coordinates(original []coordinate) ([]coordinate, error) {
	if r.index < 0 || r.index >= len(original) {
		return nil, trialInvalid()
	}
	maximum := 0
	for _, c := range original {
		n, err := strconv.Atoi(strings.TrimPrefix(text(c.ReplicateID), "replicate-"))
		if err != nil {
			return nil, trialInvalid()
		}
		maximum = max(maximum, n)
	}
	// The profile admits at most 1000 replacements per original slot.
	ordinal := maximum + r.index*r.maximum + r.origin.Ordinal
	if ordinal <= 0 || ordinal >= 1000000 {
		return nil, trialInvalid()
	}
	result := slices.Clone(original)
	id := "replicate-" + fmtReplicate(ordinal)
	result[r.index].ReplicateID = &id
	return result, nil
}
func replacementRefusal(code, message string) error {
	return refuse("replacement-"+code, "/run_plan/replacement_policy", message)
}

// CompileReplacement replays the complete committed prefix and allocates one successor.
// It has no effects and does not claim a slot or authorize dispatch.
func CompileReplacement(ctx context.Context, request ReplacementRequest) (ReplacementResult, error) {
	request.Compilation = defaultRequestLimits(request.Compilation)
	result, err := allocateReplacement(ctx, request)
	if err == nil {
		return result, nil
	}
	var refusal *compilationRefusalError
	if !errors.As(err, &refusal) {
		category, known := fault.CategoryOf(err)
		if !known || category != fault.InvalidInput {
			return ReplacementResult{}, err
		}
		refusal = &compilationRefusalError{"replacement-input-invalid", "/run_plan/replacement_policy", "replacement input failed closed validation"}
	}
	return ReplacementResult{CleanupReceipts: []binding.TrialCleanupReceiptV1{}, Diagnostics: []diagnostic.Diagnostic{{Code: "trial-compiler." + refusal.code, Domain: compilerDomain, Address: refusal.address, Message: refusal.message, Severity: "error"}}}, nil
}
func defaultRequestLimits(request Request) Request {
	if request.Limits == (Limits{}) {
		request.Limits = DefaultLimits()
	}
	if request.MixedCompositionLimits == (MixedCompositionLimits{}) {
		request.MixedCompositionLimits = DefaultMixedCompositionLimits()
	}
	return request
}

type replacementArchive struct {
	raw                                  json.RawMessage
	run                                  binding.ExperimentRunV1
	id, version, status, entry, terminal string
	attempts                             []attemptReference
}
type attemptReference struct {
	ID      string `json:"execution_attempt_id"`
	Receipt string `json:"cleanup_receipt_ref"`
}
type replacementReceipt struct {
	raw                json.RawMessage
	value              binding.TrialCleanupReceiptV1
	id, attempt, entry string
	status             string
	disposition        string
	boundaries         []string
}

func archiveForReplacement(run binding.ExperimentRunV1) (replacementArchive, error) {
	var result replacementArchive
	owner, err := trialOwner()
	if err != nil {
		return result, err
	}
	if err = admission.CheckTransport(run, trialIngress()); err != nil {
		return result, err
	}
	raw, err := encoded(run)
	if err != nil {
		return result, err
	}
	result.raw, err = admission.ExperimentModelProjection(owner, "experiment-run-v1", raw)
	if err != nil {
		return result, err
	}
	var view struct {
		ID         string `json:"run_id"`
		Version    string `json:"run_version"`
		Status     string `json:"run_status"`
		Provenance *struct {
			Entry    string             `json:"plan_entry_id"`
			Terminal string             `json:"terminal_attempt_id"`
			Attempts []attemptReference `json:"execution_attempts"`
		} `json:"trial_provenance"`
	}
	if decode(result.raw, &view) != nil || view.Provenance == nil {
		return result, trialInvalid()
	}
	result.id, result.version, result.status, result.entry, result.terminal, result.attempts = view.ID, view.Version, view.Status, view.Provenance.Entry, view.Provenance.Terminal, view.Provenance.Attempts
	err = decode(result.raw, &result.run)
	return result, err
}
func receiptsForReplacement(receipts []binding.TrialCleanupReceiptV1) ([]replacementReceipt, error) {
	owner, err := trialOwner()
	if err != nil {
		return nil, err
	}
	result := make([]replacementReceipt, len(receipts))
	for i, value := range receipts {
		if err = admission.CheckTransport(value, trialIngress()); err != nil {
			return nil, err
		}
		raw, err := encoded(value)
		if err != nil {
			return nil, err
		}
		raw, err = admission.ExperimentModelProjection(owner, "trial-cleanup-receipt-v1", raw)
		if err != nil {
			return nil, err
		}
		var view struct {
			ID      string `json:"receipt_id"`
			Attempt string `json:"execution_attempt_id"`
			Entry   string `json:"plan_entry_id"`
			Status  string `json:"cleanup_status"`
			Claim   *struct {
				Disposition string   `json:"disposition"`
				Boundaries  []string `json:"boundary_refs"`
			} `json:"clean_state_claim"`
		}
		if decode(raw, &view) != nil {
			return nil, trialInvalid()
		}
		result[i] = replacementReceipt{raw: raw, id: view.ID, attempt: view.Attempt, entry: view.Entry, status: view.Status}
		if decode(raw, &result[i].value) != nil {
			return nil, trialInvalid()
		}
		if view.Claim != nil {
			result[i].disposition = view.Claim.Disposition
			result[i].boundaries = view.Claim.Boundaries
		}
	}
	slices.SortFunc(result, func(a, b replacementReceipt) int { return strings.Compare(a.attempt, b.attempt) })
	return result, nil
}
func replacementRoot(ctx context.Context, request ReplacementRequest) (trialPlan, replacementPolicy, error) {
	var root trialPlan
	var policy replacementPolicy
	value, err := admitPlan(request.OriginalPlan)
	if err != nil {
		return root, policy, err
	}
	if decode(value.JSON(), &root) != nil {
		return root, policy, trialInvalid()
	}
	if !isNull(root.ReplacementOrigin) || root.Entries[request.RootEntryID].ID == "" {
		return root, policy, replacementRefusal("root-invalid", "replacement requires an original admitted allocation slot")
	}
	if isNull(root.ReplacementPolicy) || decode(root.ReplacementPolicy, &policy) != nil || policy.Maximum == 0 {
		return root, policy, replacementRefusal("not-authorized", "the original experiment authorizes no replacement trials")
	}
	if len(request.PreviousAllocations) > policy.Maximum {
		return root, policy, replacementRefusal("history-invalid", "replacement history exceeds the authored lineage bound")
	}
	if len(root.Entries) > request.Compilation.Limits.MaxCoordinates/(len(request.PreviousAllocations)+2) {
		return root, policy, replacementRefusal("work-limit-exceeded", "replacement traversal exceeds the compilation work limit")
	}
	expected, err := compilePlan(ctx, request.Compilation)
	if err != nil {
		return root, policy, err
	}
	var fresh trialPlan
	raw, err := encoded(expected)
	if err != nil {
		return root, policy, err
	}
	if decode(raw, &fresh) != nil || root.Digest != fresh.Digest {
		return root, policy, replacementRefusal("root-invalid", "replacement inputs differ from the original admitted experiment")
	}
	return root, policy, nil
}

type replacementEvidence struct {
	run      replacementArchive
	receipts []replacementReceipt
}

func contextForReplacement(request Request, root, parent trialPlan, rootEntry string, policy replacementPolicy, evidence replacementEvidence, ordinal int) (replacementContext, error) {
	run := evidence.run
	var result replacementContext
	if !slices.Contains(policy.Triggers, run.status) {
		return result, replacementRefusal("not-authorized", "the authored policy does not replace this trial disposition")
	}
	experiment, err := replacementTask(request, run)
	if err != nil {
		return result, err
	}
	if !isNull(parent.ReplacementOrigin) && run.version != "1" {
		return result, replacementRefusal(codeReplacementParentInvalid, "replacement parent must resolve its reserved first archival version")
	}
	receipt, err := cleanReplacementParent(parent, run, evidence.receipts)
	if err != nil {
		return result, err
	}
	expected := rootEntry
	if parent.ID != root.ID {
		for id := range parent.Entries {
			expected = id
		}
	}
	if run.entry != expected {
		return result, replacementRefusal(codeReplacementParentInvalid, "replacement parent does not match the original allocation slot")
	}
	originalCoordinates, err := coordinates(experiment, request.Limits)
	if err != nil {
		return result, err
	}
	result.index = -1
	for index, c := range originalCoordinates {
		a, _ := encoded(c)
		b, _ := encoded(root.Entries[rootEntry].Coordinate)
		if sameJSON(a, b) {
			result.index = index
			break
		}
	}
	if result.index < 0 {
		return result, trialInvalid()
	}
	runDigest, err := hash(run.raw)
	if err != nil {
		return result, err
	}
	result.maximum = policy.Maximum
	result.origin = replacementOrigin{root.ID, root.Digest, rootEntry, ordinal, parent.ID, parent.Digest, run.entry, run.id, run.version, runDigest, receipt.id}
	return result, nil
}
func replacementTask(request Request, run replacementArchive) (experimentSpec, error) {
	var original struct {
		Task reference `json:"task_ref"`
	}
	if decode(run.raw, &original) != nil {
		return experimentSpec{}, trialInvalid()
	}
	var experiment experimentSpec
	if decode(request.Experiment.JSON(), &experiment) != nil {
		return experimentSpec{}, trialInvalid()
	}
	a, err := encoded(original.Task)
	if err != nil {
		return experimentSpec{}, err
	}
	b, err := encoded(experiment.Task)
	if err != nil {
		return experimentSpec{}, err
	}
	if !sameJSON(a, b) {
		return experimentSpec{}, replacementRefusal(codeReplacementParentInvalid, "replacement parent does not belong to the admitted experiment task")
	}
	return experiment, nil
}
func cleanReplacementParent(plan trialPlan, run replacementArchive, receipts []replacementReceipt) (replacementReceipt, error) {
	raw, err := encoded(plan)
	if err != nil {
		return replacementReceipt{}, err
	}
	owner, err := trialOwner()
	if err != nil {
		return replacementReceipt{}, err
	}
	admitted, err := owner.Validate("admitted-trial-plan-v1", raw, trialIngress(), nil)
	if err != nil {
		return replacementReceipt{}, err
	}
	terminal, retained, err := replacementReceiptSet(run, receipts)
	if err != nil {
		return terminal, err
	}
	if err = admission.ValidateTrialRunJSON(owner, admitted, run.raw, retained); err != nil {
		return terminal, err
	}
	var cleanup struct {
		CleanState struct {
			Mode string `json:"mode"`
		} `json:"clean_state"`
		Boundaries map[string]json.RawMessage `json:"resource_boundaries"`
		Retry      struct {
			Max int `json:"max_attempts"`
		} `json:"retry_policy"`
	}
	entry := plan.Entries[run.entry]
	if decode(plan.Cleanup[entry.Controls.CleanupRef], &cleanup) != nil || len(receipts) > cleanup.Retry.Max {
		return terminal, trialInvalid()
	}
	if terminal.status != "succeeded" || terminal.disposition == "" || terminal.disposition == "fresh-range-required" || cleanup.CleanState.Mode == "fresh-range-required" || terminal.disposition == termDeclaredReusable && cleanup.CleanState.Mode != termDeclaredReusable || len(terminal.boundaries) != len(cleanup.Boundaries) {
		return terminal, replacementRefusal("clean-state-unverified", "terminal cleanup does not establish reusable initial state")
	}
	for _, id := range terminal.boundaries {
		if _, exists := cleanup.Boundaries[id]; !exists {
			return terminal, replacementRefusal("clean-state-unverified", "terminal cleanup does not establish reusable initial state")
		}
	}
	return terminal, nil
}
func replacementReceiptSet(run replacementArchive, receipts []replacementReceipt) (replacementReceipt, [][]byte, error) {
	retained := make([][]byte, len(receipts))
	seenIDs := map[string]bool{}
	seenAttempts := map[string]bool{}
	referenced := map[string]bool{}
	for _, attempt := range run.attempts {
		referenced[attempt.Receipt] = true
	}
	var terminal replacementReceipt
	for i, receipt := range receipts {
		if seenIDs[receipt.id] || seenAttempts[receipt.attempt] || receipt.entry != run.entry || !referenced[receipt.id] {
			return terminal, nil, trialInvalid()
		}
		seenIDs[receipt.id] = true
		seenAttempts[receipt.attempt] = true
		retained[i] = receipt.raw
		if receipt.attempt == run.terminal {
			terminal = receipt
		}
	}
	if len(receipts) != len(referenced) || terminal.id == "" {
		return terminal, nil, trialInvalid()
	}
	return terminal, retained, nil
}
