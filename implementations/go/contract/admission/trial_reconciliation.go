package admission

import (
	"encoding/json"
	"slices"
	"strconv"

	"github.com/OpenRAE/rae/implementations/go/base/ingress"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
	"github.com/OpenRAE/rae/implementations/go/contract/validation"
)

// TrialRunInputs separates the sealed plan, retained cleanup, and archival run.
// Task may be zero for plan-only reconciliation; task evidence has its own boundary.
type TrialRunInputs struct {
	Plan, Run, Task validation.Value
	CleanupReceipts []validation.Value
}

func (e *Validator) experimentValue(value validation.Value, id string) (any, error) {
	if e == nil || value.ContractID() != id {
		return nil, invalid()
	}
	raw := value.JSON()
	limits := ingress.Limits{MaxBytes: 32 << 20, MaxDepth: 64}
	var err error
	if id == trialPlanContract {
		raw, err = TrialPlanProjection(e, value, limits)
	} else {
		raw, err = e.experimentProjection(id, raw)
	}
	if err != nil {
		return nil, err
	}
	return ingress.Parse(raw, limits, ingress.Object)
}

// ValidateTrialRun joins exact sealed identities, retained attempts and owner results.
// It does not turn cleanup or execution observations into scientific evidence.
func ValidateTrialRun(v *Validator, inputs TrialRunInputs) error {
	plan, err := v.experimentValue(inputs.Plan, trialPlanContract)
	if err != nil {
		return err
	}
	run, err := v.experimentValue(inputs.Run, termExperimentRunV1)
	if err != nil {
		return err
	}
	receipts := make([]any, len(inputs.CleanupReceipts))
	for index, value := range inputs.CleanupReceipts {
		receipts[index], err = v.experimentValue(value, termTrialCleanupReceiptV1)
		if err != nil {
			return err
		}
		if err = cleanupReceiptLocal(receipts[index]); err != nil {
			return err
		}
	}
	if inputs.Task.ContractID() != "" {
		task, err := v.experimentValue(inputs.Task, termExperimentTaskV1)
		if err != nil {
			return err
		}
		if err = v.taskRunJoin(task, run); err != nil {
			return err
		}
	}
	return v.trialRunJoin(plan, run, receipts)
}
func (e *Validator) trialRunJoin(plan, run any, receipts []any) error {
	if stringAt(run, "record_state") == statusPartial || at(run, "execution_accounting") != nil {
		if err := trialAccountingJoin(plan, run, receipts); err != nil {
			return err
		}
		if stringAt(run, "record_state") == statusPartial {
			return nil
		}
	}
	linkage := at(run, "trial_provenance")
	if linkage == nil || !matchingFields(linkage, plan, fieldPlanID, "plan_digest") {
		return invalid()
	}
	entry := at(plan, "entries", stringAt(linkage, fieldPlanEntryID))
	if entry == nil || !matchingFields(linkage, entry, "entry_digest", "coordinate") || !equal(at(linkage, "admitted_run_id"), at(entry, termRunID)) || !equal(at(run, termRunID), at(entry, termRunID)) || !equal(at(run, "scenario_snapshot_ref", "ref_digest"), at(linkage, "instantiated_scenario_digest")) {
		return invalid()
	}
	if err := e.trialRunBindings(entry, run); err != nil {
		return err
	}
	if err := trialRunRandomness(plan, entry, run); err != nil {
		return err
	}
	terminal, err := trialAttemptEvidence(plan, entry, linkage, receipts)
	if err != nil {
		return err
	}
	return trialTerminalOutcome(run, terminal)
}
func trialTerminalOutcome(run, receipt any) error {
	status := stringAt(run, "run_status")
	if status == experimentTermInvalidated || status == statusSuperseded {
		return nil
	}
	allowed := map[string][]string{"succeeded": {statusCompleted, experimentTermSealed}, outcomeFailed: {outcomeFailed}, "cancelled": {outcomeAborted}, experimentTermTimedOut: {outcomeFailed, outcomeAborted}, outcomeAborted: {outcomeAborted}}[stringAt(receipt, "trial_outcome")]
	if slices.Contains(allowed, status) {
		return nil
	}
	return invalid()
}
func trialAttemptEvidence(plan, entry, linkage any, receipts []any) (any, error) {
	byID := map[string]any{}
	for _, receipt := range receipts {
		id := stringAt(receipt, "receipt_id")
		if byID[id] != nil {
			return nil, invalid()
		}
		byID[id] = receipt
	}
	var terminal any
	cleanup := at(plan, "cleanup_plans", stringAt(entry, "execution_controls", "cleanup_plan_ref"))
	for _, attempt := range array(at(linkage, "execution_attempts")) {
		receipt := byID[stringAt(attempt, "cleanup_receipt_ref")]
		if receipt == nil || !equal(at(receipt, "execution_attempt_id"), at(attempt, "execution_attempt_id")) {
			return nil, invalid()
		}
		if err := cleanupReceiptJoin(cleanup, receipt); err != nil {
			return nil, err
		}
		if equal(at(attempt, "execution_attempt_id"), at(linkage, "terminal_attempt_id")) {
			terminal = receipt
		}
	}
	if terminal == nil {
		return nil, invalid()
	}
	return terminal, nil
}
func trialRunRandomness(plan, entry, run any) error {
	controls := map[string]any{}
	for _, control := range array(at(run, "stochastic_controls")) {
		controls[stringAt(control, "control_id")] = control
	}
	required := map[string]bool{}
	for _, draw := range array(at(entry, "stochastic_draws")) {
		required[stringAt(draw, "control_id")] = true
	}
	if allocation := at(plan, "allocation"); allocation != nil {
		required[stringAt(allocation, termPolicy, "stochastic_control_ref")] = true
	}
	for id := range required {
		if !equal(controls[id], at(plan, "stochastic_controls", id)) {
			return invalid()
		}
	}
	draws := map[string]bool{}
	for _, draw := range array(at(run, "stochastic_draws")) {
		digest, err := jsonDigest(draw)
		if err != nil {
			return err
		}
		draws[digest] = true
	}
	for _, draw := range array(at(entry, "stochastic_draws")) {
		digest, err := jsonDigest(draw)
		if err != nil || !draws[digest] {
			return invalid()
		}
	}
	return trialRunSelections(entry, run)
}
func trialRunSelections(entry, run any) error {
	expected := map[string]string{}
	actual := map[string]string{}
	for _, record := range array(at(entry, "selections")) {
		selection := at(record, "treatment")
		if selection == nil {
			continue
		}
		digest, err := jsonDigest(selection)
		if err != nil {
			return err
		}
		expected[stringAt(selection, "selection_id")] = digest
	}
	for _, selection := range array(at(run, "realized_selections")) {
		digest, err := jsonDigest(selection)
		if err != nil {
			return err
		}
		actual[stringAt(selection, "selection_id")] = digest
	}
	return require(equal(actual, expected))
}
func (e *Validator) trialRunBindings(entry, run any) error {
	if err := trialRunSelections(entry, run); err != nil {
		return err
	}
	realized := map[string]any{}
	for _, binding := range array(at(run, "realized_bindings")) {
		realized[stringAt(binding, "descriptor", termBindingID)] = binding
	}
	configurations := map[string]any{}
	for _, result := range array(at(entry, "participant_configurations")) {
		configurations[stringAt(result, fieldParticipantAddress)] = result
	}
	for _, binding := range array(at(entry, termBindings)) {
		descriptor := at(binding, "descriptor")
		actual := realized[stringAt(descriptor, termBindingID)]
		if actual == nil || !matchingFields(actual, binding, "descriptor", termOrigin) {
			return invalid()
		}
		if stringAt(descriptor, "target", "plane") == "participant-implementation" && !equal(at(actual, termConfigurationDigest), at(configurations[stringAt(descriptor, "target", fieldParticipantAddress)], termConfigurationDigest)) {
			return invalid()
		}
	}
	return e.trialConfigurationSelections(run, configurations)
}
func (e *Validator) trialConfigurationSelections(run any, configurations map[string]any) error {
	selections := map[string]any{}
	for _, selection := range array(at(run, "participant_implementation_provenance", "participant_implementations")) {
		selections[stringAt(selection, fieldParticipantAddress)] = selection
	}
	for address, result := range configurations {
		selection := selections[address]
		if selection == nil {
			return invalid()
		}
		fragment, err := AdmitFragment(e, ParticipantImplementationSelection, selection, ingress.Limits{MaxBytes: 8 << 20, MaxDepth: 64})
		if err != nil {
			return err
		}
		raw, err := json.Marshal(result)
		if err != nil {
			return invalid()
		}
		var value binding.ParticipantConfigurationResultV1
		if json.Unmarshal(raw, &value) != nil {
			return invalid()
		}
		if err := ValidateParticipantConfigurationSelection(fragment, value); err != nil {
			return err
		}
	}
	return nil
}
func trialAccountingJoin(plan, run any, receipts []any) error {
	accounting := at(run, "execution_accounting")
	if accounting == nil || !matchingFields(accounting, plan, fieldPlanID, "plan_digest") {
		return invalid()
	}
	entry := at(plan, "entries", stringAt(accounting, fieldPlanEntryID))
	if entry == nil || !equal(at(entry, "entry_digest"), at(accounting, "entry_digest")) || !equal(at(entry, termRunID), at(run, termRunID)) || !equal(array(at(accounting, "participant_configurations")), array(at(entry, "participant_configurations"))) {
		return invalid()
	}
	if err := trialRunRandomness(plan, entry, run); err != nil {
		return err
	}
	cleanup := at(plan, "cleanup_plans", stringAt(entry, "execution_controls", "cleanup_plan_ref"))
	if numericGreater(json.Number(strconv.Itoa(len(array(at(accounting, "attempts"))))), at(cleanup, "retry_policy", termMaxAttempts)) {
		return invalid()
	}
	expected := map[string]any{}
	supplied := map[string]any{}
	for _, attempt := range array(at(accounting, "attempts")) {
		receipt := at(attempt, "cleanup_receipt")
		if receipt == nil {
			continue
		}
		expected[stringAt(receipt, "receipt_id")] = receipt
		if err := cleanupReceiptJoin(cleanup, receipt); err != nil {
			return err
		}
	}
	for _, receipt := range receipts {
		id := stringAt(receipt, "receipt_id")
		if supplied[id] != nil {
			return invalid()
		}
		supplied[id] = receipt
	}
	return require(equal(supplied, expected))
}

// ValidateTrialRunJSON reconciles locally reconstructed archival bytes and all receipts.
// It does not assert task or content-backed evidence admission.
func ValidateTrialRunJSON(v *Validator, plan validation.Value, run []byte, cleanupReceipts [][]byte) error {
	document, err := v.experimentValue(plan, trialPlanContract)
	if err != nil {
		return err
	}
	runRaw, err := ExperimentModelProjection(v, termExperimentRunV1, run)
	if err != nil {
		return err
	}
	var runView any
	if decodeExact(runRaw, &runView) != nil {
		return invalid()
	}
	receipts := make([]any, len(cleanupReceipts))
	for index, raw := range cleanupReceipts {
		raw, err = ExperimentModelProjection(v, termTrialCleanupReceiptV1, raw)
		if err != nil {
			return err
		}
		if decodeExact(raw, &receipts[index]) != nil {
			return invalid()
		}
		if err = cleanupReceiptLocal(receipts[index]); err != nil {
			return err
		}
	}
	return v.trialRunJoin(document, runView, receipts)
}
