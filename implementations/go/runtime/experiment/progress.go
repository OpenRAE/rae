package experiment

import (
	"context"
	"encoding/json"
	"fmt"
	"maps"
	"slices"
	"time"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

func attemptID(experimentID, entryID string, ordinal int) string {
	return admission.TrialAttemptID(experimentID, entryID, ordinal)
}
func (c *coordinator) Advance(ctx context.Context, id Identity) (Progress, error) {
	if err := c.authorize(ctx, id); err != nil {
		return Progress{}, err
	}
	release, err := c.acquire(ctx)
	if err != nil {
		return Progress{}, err
	}
	defer release()
	records, err := c.load(ctx)
	if err != nil {
		return Progress{}, err
	}
	if err = c.restoreChildren(ctx, records); err != nil {
		return Progress{}, err
	}
	cancelled := false
	for _, record := range records {
		m := decisionMap(record)
		if record.SchemaVersion() == cancelSchema && text(m, termExperimentID) == c.id {
			cancelled = true
		}
	}
	for _, slot := range c.slotSnapshot() {
		progress, active, advanceErr := c.advanceSlot(ctx, slot, records, cancelled)
		if advanceErr != nil {
			return Progress{}, advanceErr
		}
		if active {
			return progress, nil
		}
	}
	state := termCompleted
	if cancelled {
		state = termCancelled
	}
	return Progress{ExperimentID: c.id, State: state}, nil
}
func (c *coordinator) advanceSlot(ctx context.Context, s trialSlot, records []Decision, cancelled bool) (Progress, bool, error) {
	attempts := slotAttempts(records, c.id, s.entry.PlanEntryID)
	if err := validateRetainedAttempts(c.id, s, attempts); err != nil {
		return Progress{}, false, err
	}
	if len(attempts) == 0 && cancelled {
		return Progress{}, false, nil
	}
	request := s.request(nil)
	if len(attempts) > 0 {
		request = s.request(attempts[len(attempts)-1])
	} else {
		request.ExecutionAttemptID = attemptID(c.id, s.entry.PlanEntryID, 1)
		request.Attempt = 1
	}
	request.Identity = c.options.Identity
	retired, retirementErr := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (bool, error) {
		return c.options.Host.IsRetired(work, copyTrial(request))
	})
	if retirementErr != nil || retired {
		return Progress{}, false, retirementErr
	}
	var attempt map[string]any
	if len(attempts) == 0 {
		d, err := c.startAttempt(ctx, s, 1)
		if err != nil {
			return Progress{}, false, err
		}
		attempt = decisionMap(d)
	} else {
		attempt = attempts[len(attempts)-1]
	}
	t := s.request(attempt)
	t.Identity = c.options.Identity
	terminal := findAttemptDecision(records, terminalSchema, t.ExecutionAttemptID)
	if terminal != nil {
		return c.finishAttempt(ctx, s, t, records, terminal, cancelled)
	}
	state, err := c.advanceTrial(ctx, s, t, records, cancelled)
	return c.progress(state, t), true, err
}
func slotAttempts(records []Decision, experimentID, entryID string) []map[string]any {
	result := []map[string]any{}
	for _, record := range records {
		if record.SchemaVersion() != attemptSchema {
			continue
		}
		m := decisionMap(record)
		if text(m, termExperimentID) == experimentID && text(m, termPlanEntryID) == entryID {
			result = append(result, m)
		}
	}
	slices.SortFunc(result, func(a, b map[string]any) int { return integer(a["attempt"]) - integer(b["attempt"]) })
	return result
}
func findAttemptDecision(records []Decision, schema, attempt string) map[string]any {
	for _, record := range records {
		if record.SchemaVersion() == schema {
			m := decisionMap(record)
			if text(m, termExecutionAttemptID) == attempt {
				return m
			}
		}
	}
	return nil
}
func attemptObservations(records []Decision, attempt string) map[string]map[string]any {
	result := map[string]map[string]any{}
	for _, record := range records {
		if record.SchemaVersion() == observationSchema {
			m := decisionMap(record)
			if text(m, termExecutionAttemptID) == attempt {
				result[text(m, "observation", "kind")] = m
			}
		}
	}
	return result
}
func (c *coordinator) startAttempt(ctx context.Context, s trialSlot, ordinal int) (Decision, error) { //nolint:ireturn // Durable starts use the sealed journal decision.
	now := c.now()
	seconds := integer(at(s.view, "entries", s.entry.PlanEntryID, "execution_controls", "attempt_timeout_seconds"))
	if seconds < 1 || int64(seconds) > 253402300799-now.Unix() {
		return nil, integrity()
	}
	return c.claim(ctx, attemptSchema, map[string]any{termExperimentID: c.id, termPlanEntryID: s.entry.PlanEntryID, termRunID: s.entry.RunID, "attempt": ordinal, termExecutionAttemptID: attemptID(c.id, s.entry.PlanEntryID, ordinal), termStartedAt: runtimeTimestamp(now), "deadline": runtimeTimestamp(time.Unix(now.Unix()+int64(seconds), int64(now.Nanosecond())).UTC())})
}
func (c *coordinator) advanceTrial(ctx context.Context, s trialSlot, t Trial, records []Decision, cancelled bool) (string, error) {
	known := attemptObservations(records, t.ExecutionAttemptID)
	execution := at(known[termExecution], "observation")
	if execution == nil {
		return c.advanceExecution(ctx, s, t, records, known, cancelled)
	}
	if !truth(at(execution, "ceased")) {
		return termIndeterminate, nil
	}
	capture, err := c.phase(ctx, s, t, termCapture, known, func(work context.Context) (Phase, error) { return c.options.Host.Capture(work, copyTrial(t)) })
	if err != nil {
		return "", err
	}
	if phasePending(capture) {
		return capture, nil
	}
	cleanup, err := c.phase(ctx, s, t, termCleanup, known, func(work context.Context) (Phase, error) {
		return c.options.Host.Cleanup(work, copyTrial(t), text(execution, "state"))
	})
	if err != nil {
		return "", err
	}
	if phasePending(cleanup) {
		return cleanup, nil
	}
	if cleanup != termSucceeded {
		return termCleanupFailed, nil
	}
	return termProgress, c.recordTerminal(ctx, s, t, known, capture)
}
func (c *coordinator) advanceExecution(ctx context.Context, s trialSlot, t Trial, records []Decision, known map[string]map[string]any, cancelled bool) (string, error) {
	interruption, err := c.interruption(ctx, s, t, records, cancelled)
	if err != nil {
		return "", err
	}
	forced := ""
	var state string
	if interruption != nil {
		forced = interruptionOutcome(interruption)
		state, err = c.phase(ctx, s, t, "", known, func(work context.Context) (Phase, error) {
			return c.options.Host.Stop(work, copyTrial(t), text(interruption, "cause"))
		})
	} else {
		state, err = c.executeConfigured(ctx, s, t, known)
		if state != termSucceeded {
			forced = state
		}
	}
	if err != nil {
		return termIndeterminate, err
	}
	if phasePending(state) {
		return state, nil
	}

	return c.observeExecution(ctx, s, t, known, forced)
}
func (c *coordinator) executeConfigured(ctx context.Context, s trialSlot, t Trial, known map[string]map[string]any) (string, error) {
	state, configureErr := c.phase(ctx, s, t, termConfiguration, known, func(work context.Context) (Phase, error) { return c.options.Host.Configure(work, copyTrial(t)) })
	if configureErr != nil {
		return "", configureErr
	}
	if phasePending(state) {
		return state, nil
	}
	if state != termSucceeded {
		return state, nil
	}
	state, advanceErr := c.phase(ctx, s, t, "", known, func(work context.Context) (Phase, error) { return c.options.Host.Advance(work, copyTrial(t)) })
	if advanceErr != nil {
		return termIndeterminate, advanceErr
	}
	if phasePending(state) {
		return state, nil
	}
	if state != termSucceeded {
		return state, nil
	}

	return termSucceeded, nil
}
func interruptionOutcome(interruption map[string]any) string {
	if text(interruption, "disposition") == "abort" {
		return termAborted
	}
	if text(interruption, "cause") == termCancellation {
		return termCancelled
	}
	return termTimedOut
}
func (c *coordinator) observeExecution(ctx context.Context, s trialSlot, t Trial, known map[string]map[string]any, forced string) (string, error) {
	observed, err := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (Observation, error) { return c.options.Host.Observe(work, copyTrial(t)) })
	if err != nil {
		return termIndeterminate, err
	}
	verified, err := c.validateObservation(ctx, s, t, termExecution, observed)
	if err != nil {
		return "", err
	}
	if verified.value.State == termRunning || !verified.value.Ceased {
		if forced != "" {
			return termIndeterminate, nil
		}
		return termPending, nil
	}
	if forced != "" {
		verified.value.State = forced
	}
	return termProgress, c.retainVerifiedObservation(ctx, t, verified, known)
}

//nolint:nilnil // No decision means that neither cancellation nor deadline expiry has occurred.
func (c *coordinator) interruption(ctx context.Context, s trialSlot, t Trial, records []Decision, cancelled bool) (map[string]any, error) {
	if retained := findAttemptDecision(records, interruptionSchema, t.ExecutionAttemptID); retained != nil {
		return retained, nil
	}
	started, err := time.Parse(time.RFC3339Nano, t.StartedAt)
	if err != nil {
		return nil, integrity()
	}
	deadline, err := time.Parse(time.RFC3339Nano, t.Deadline)
	if err != nil || !deadline.After(started) {
		return nil, integrity()
	}
	now := c.now()
	if now.Before(started) {
		return nil, fault.New(fault.Operational, "experiment-clock-discontinuity", nil)
	}
	timer := c.deadlines[t.ExecutionAttemptID]
	if timer == nil {
		timer = &attemptDeadline{timer: time.NewTimer(max(0, deadline.Sub(now)))}
		c.deadlines[t.ExecutionAttemptID] = timer
	}
	expired := timer.expired || !now.Before(deadline)
	select {
	case <-timer.timer.C:
		expired = true
		timer.expired = true
	default:
	}
	if !expired && !cancelled {
		return nil, nil
	}
	cause, field := "timeout", "on_timeout"
	if cancelled {
		cause, field = termCancellation, "on_cancellation"
	}
	d, err := c.claim(ctx, interruptionSchema, map[string]any{termExecutionAttemptID: t.ExecutionAttemptID, "cause": cause, "disposition": at(s.view, "entries", t.PlanEntryID, "execution_controls", field)})
	if err != nil {
		return nil, err
	}
	return decisionMap(d), nil
}

func observationDocument(o Observation) (map[string]any, error) {
	if o.Evidence == nil {
		o.Evidence = []binding.ExperimentEvidenceRecordV1{}
	}
	m := map[string]any{"kind": o.Kind, termEvidence: o.Evidence}
	switch o.Kind {
	case termConfiguration:
		if o.Configurations == nil {
			o.Configurations = []binding.ParticipantConfigurationResultV1{}
		}
		m["configurations"] = o.Configurations
	case termExecution:
		m["state"], m["ceased"], m["effects_absent"] = o.State, o.Ceased, o.EffectsAbsent
	case termCapture:
		m["complete"] = o.Complete
	case termCleanup:
		m["receipt"], m["idempotent_effects"], m["verified_compensations"] = o.CleanupReceipt, o.IdempotentEffects, nonNilStrings(o.VerifiedCompensations)
	case termRetry:
		results := map[string]any{}
		for key, result := range o.ObligationResults {
			if admission.CheckFragment(result, admission.CleanupObligationResult) != nil {
				return nil, integrity()
			}
			results[key] = result.Document()
		}
		m["ready"], m["obligation_results"], m["verified_compensations"] = o.Reusable, results, nonNilStrings(o.VerifiedCompensations)
	default:
		return nil, integrity()
	}
	return transportView(m)
}
func nonNilStrings(s []string) []string {
	if s == nil {
		return []string{}
	}
	return s
}
func (c *coordinator) validateObservation(ctx context.Context, s trialSlot, t Trial, kind string, o Observation) (verifiedObservation, error) {
	var err error
	o, err = detachObservation(o)
	if err != nil {
		return verifiedObservation{}, err
	}
	if o.Kind != kind {
		return verifiedObservation{}, integrity()
	}
	m, err := observationDocument(o)
	if err != nil {
		return verifiedObservation{}, err
	}
	if err = validateObservationMap(m); err != nil {
		return verifiedObservation{}, err
	}
	if err = c.validateObservedFacts(s, t, kind, o, m); err != nil {
		return verifiedObservation{}, err
	}
	_, err = ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (struct{}, error) {
		copyObservation, copyErr := detachObservation(o)
		if copyErr != nil {
			return struct{}{}, copyErr
		}
		return struct{}{}, c.options.Host.Verify(work, copyTrial(t), copyObservation)
	})
	if err != nil {
		return verifiedObservation{}, err
	}
	return verifiedObservation{value: o}, nil
}
func (c *coordinator) validateObservedFacts(s trialSlot, t Trial, kind string, o Observation, m map[string]any) error {
	var err error
	for _, evidence := range array(m[termEvidence]) {
		if text(evidence, "run_ref", termRefKind) != termRun || text(evidence, "run_ref", termRefID) != t.RunID {
			return integrity()
		}
	}
	switch kind {
	case termExecution:
		if o.Ceased && len(o.Evidence) == 0 {
			return integrity()
		}
	case termConfiguration:
		if !same(nonNilConfigurations(o.Configurations), nonNilConfigurations(t.Realization.ParticipantConfigurations)) || len(o.Configurations) > 0 && len(o.Evidence) == 0 {
			return integrity()
		}
	case termCleanup:
		err = c.validateCleanup(s, t, m)
	case termRetry:
		err = validateRetry(s, t, m)
	}
	if err != nil {
		return err
	}
	return validateObservationReceipts(t.RunID, o.OperationReceipts)
}
func validateObservationReceipts(runID string, receipts []binding.OperationReceiptV1) error {
	for _, receipt := range receipts {
		view, viewErr := transportView(receipt)
		if viewErr != nil || localModel("operation-receipt-v1", view) != nil || text(view, "context", "run_scope") != "run:"+runID {
			return integrity()
		}
	}
	return nil
}
func nonNilConfigurations(v []binding.ParticipantConfigurationResultV1) []binding.ParticipantConfigurationResultV1 {
	if v == nil {
		return []binding.ParticipantConfigurationResultV1{}
	}
	return v
}

type cleanupContext struct{ raw []byte }

func (c cleanupContext) CleanupPlan() []byte { return slices.Clone(c.raw) }
func cleanupPlan(s trialSlot, t Trial) map[string]any {
	return object(at(s.view, "cleanup_plans", text(s.view, "entries", t.PlanEntryID, "execution_controls", "cleanup_plan_ref")))
}
func (c *coordinator) validateCleanup(s trialSlot, t Trial, m map[string]any) error {
	receipt := object(m["receipt"])
	if text(receipt, termExecutionAttemptID) != t.ExecutionAttemptID {
		return integrity()
	}
	owner, err := experimentOwner()
	if err != nil {
		return err
	}
	planRaw, err := json.Marshal(cleanupPlan(s, t))
	if err != nil {
		return integrity()
	}
	raw, err := json.Marshal(receipt)
	if err != nil {
		return integrity()
	}
	if _, err = owner.Validate("trial-cleanup-receipt-v1", raw, runtimeIngress(), cleanupContext{planRaw}); err != nil {
		return err
	}
	refs := map[string]bool{}
	for _, record := range array(m[termEvidence]) {
		refs[text(record, "evidence_record_id")] = true
	}
	for _, result := range object(receipt["obligation_results"]) {
		for _, ref := range array(at(result, "evidence_refs")) {
			if !refs[fmt.Sprint(ref)] {
				return integrity()
			}
		}
	}
	for _, ref := range array(at(receipt, "clean_state_claim", "evidence_refs")) {
		if !refs[fmt.Sprint(ref)] {
			return integrity()
		}
	}
	return nil
}
func validateRetry(s trialSlot, t Trial, m map[string]any) error {
	plan := cleanupPlan(s, t)
	evidence := map[string]bool{}
	for _, item := range array(m[termEvidence]) {
		evidence[text(item, "evidence_record_id")] = true
	}
	if err := retryResultEvidence(plan, m, evidence); err != nil {
		return err
	}
	if !truth(m["ready"]) {
		return nil
	}
	if len(evidence) == 0 {
		return integrity()
	}
	for key, obligation := range object(plan["cleanup_obligations"]) {
		if text(obligation, "requirement") == "required" && slices.Contains(array(at(obligation, "triggers")), any(termRetry)) && text(m, "obligation_results", key, "status") != termSucceeded {
			return integrity()
		}
	}
	for _, ref := range array(at(plan, "retry_policy", "compensation_refs")) {
		if !slices.Contains(array(m["verified_compensations"]), ref) {
			return integrity()
		}
	}
	return nil
}
func retryResultEvidence(plan, m map[string]any, evidence map[string]bool) error {
	for key, result := range object(m["obligation_results"]) {
		obligation := at(plan, "cleanup_obligations", key)
		if obligation == nil || text(result, "obligation_id") != key || !slices.Contains(array(at(obligation, "triggers")), any(termRetry)) {
			return integrity()
		}
		for _, ref := range array(at(result, "evidence_refs")) {
			if !evidence[fmt.Sprint(ref)] {
				return integrity()
			}
		}
	}
	return nil
}
func reusable(s trialSlot, t Trial, receipt any) bool {
	plan := cleanupPlan(s, t)
	claim := at(receipt, "clean_state_claim")
	if text(receipt, "cleanup_status") != termSucceeded || claim == nil || text(claim, "disposition") == "fresh-range-required" || text(plan, "clean_state", "mode") == "fresh-range-required" {
		return false
	}
	if text(claim, "disposition") == "declared-reusable" && text(plan, "clean_state", "mode") != "declared-reusable" {
		return false
	}
	boundaries := slices.Sorted(maps.Keys(object(plan["resource_boundaries"])))
	actual := []string{}
	for _, ref := range array(at(claim, "boundary_refs")) {
		actual = append(actual, fmt.Sprint(ref))
	}
	slices.Sort(actual)
	return slices.Equal(boundaries, actual)
}
func (c *coordinator) recordTerminal(ctx context.Context, s trialSlot, t Trial, observed map[string]map[string]any, captureState string) error {
	cleanup := at(observed[termCleanup], "observation", "receipt")
	state := text(observed[termExecution], "observation", "state")
	if text(cleanup, "trial_outcome") != state {
		return integrity()
	}
	capture := termFailed
	if captureState == termSucceeded && truth(at(observed[termCapture], "observation", "complete")) {
		capture = termSucceeded
	}
	result, readErr := c.terminalResult(ctx, s, t, capture, reusable(s, t, cleanup))
	if readErr != nil {
		return readErr
	}
	operationRefs := make([]string, 0, len(result.OperationReceipts))
	for _, operation := range result.OperationReceipts {
		view, viewErr := transportView(operation)
		if viewErr != nil {
			return viewErr
		}
		operationRefs = append(operationRefs, text(view, "operation_id"))
	}
	slices.Sort(operationRefs)
	receipt := map[string]any{"schema_version": "batch-execution-receipt/v1", "receipt_id": "batch:" + t.ExecutionAttemptID, termPlanID: at(s.view, termPlanID), termPlanDigest: at(s.view, termPlanDigest), termPlanEntryID: t.PlanEntryID, termRunID: t.RunID, termExecutionAttemptID: t.ExecutionAttemptID, "dispatch_ordinal": s.entry.DispatchOrdinal, "scheduling_policy_id": c.schedule.SchedulingPolicyID, "effective_parallelism": 1, "attempt_deadline": t.Deadline, "trial_outcome": state, termOperationRefs: operationRefs, "cleanup_receipt_ref": at(cleanup, "receipt_id")}
	_, err := c.claim(ctx, terminalSchema, map[string]any{termExecutionAttemptID: t.ExecutionAttemptID, "receipt": receipt, termCaptureStatus: capture, "reusable": reusable(s, t, cleanup)})
	if timer := c.deadlines[t.ExecutionAttemptID]; timer != nil {
		timer.timer.Stop()
		delete(c.deadlines, t.ExecutionAttemptID)
	}
	return err
}
func (c *coordinator) finishAttempt(ctx context.Context, s trialSlot, t Trial, records []Decision, terminal map[string]any, cancelled bool) (Progress, bool, error) {
	if !truth(terminal["reusable"]) {
		return c.progress(termCleanupFailed, t), true, nil
	}
	if !cancelled {
		ready, state, err := c.retry(ctx, s, t, records, terminal)
		if err != nil {
			return Progress{}, true, err
		}
		if ready {
			return c.restartAttempt(ctx, s, t)
		}
		if state != "" {
			return c.progress(state, t), true, nil
		}
	}
	allocated, err := c.replace(ctx, s, t, records, !cancelled)
	if err != nil {
		return Progress{}, true, err
	}
	_, err = ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (struct{}, error) {
		return struct{}{}, c.options.Host.Retire(work, copyTrial(t))
	})
	if err != nil {
		return Progress{}, true, err
	}
	if allocated {
		return c.progress(termProgress, t), true, nil
	}
	return Progress{}, false, nil
}
func (c *coordinator) retry(ctx context.Context, s trialSlot, t Trial, records []Decision, terminal map[string]any) (bool, string, error) {
	policy := at(cleanupPlan(s, t), "retry_policy")
	if text(terminal, "receipt", "trial_outcome") != termFailed || t.Attempt >= integer(at(policy, "max_attempts")) {
		return false, "", nil
	}
	observed := attemptObservations(records, t.ExecutionAttemptID)
	execution := at(observed[termExecution], "observation")
	if !truth(at(execution, "ceased")) {
		return false, "", nil
	}
	if truth(at(execution, "effects_absent")) {
		return true, "", nil
	}
	switch text(policy, "after_effect_policy") {
	case "idempotent":
		return truth(at(observed[termCleanup], "observation", "idempotent_effects")), "", nil
	case "reset", "compensate":
		state, err := c.phase(ctx, s, t, termRetry, observed, func(work context.Context) (Phase, error) { return c.options.Host.PrepareRetry(work, copyTrial(t)) })
		if err != nil {
			return false, "", err
		}
		if phasePending(state) {
			return false, state, nil
		}
		if state != termSucceeded {
			return false, termCleanupFailed, nil
		}
		if truth(at(observed[termRetry], "observation", "ready")) {
			return true, "", nil
		}
		return false, termCleanupFailed, nil
	default:
		return false, "", nil
	}
}
func (c *coordinator) Cancel(ctx context.Context, id Identity) error {
	if err := c.authorize(ctx, id); err != nil {
		return err
	}
	_, err := c.claim(ctx, cancelSchema, map[string]any{termExperimentID: c.id, "actor_id": id.ActorID})
	if err != nil {
		return err
	}
	records, err := c.load(ctx)
	if err != nil {
		return err
	}
	if err = c.restoreChildren(ctx, records); err != nil {
		return err
	}
	for _, slot := range c.slotSnapshot() {
		for _, attempt := range slotAttempts(records, c.id, slot.entry.PlanEntryID) {
			t := slot.request(attempt)
			t.Identity = c.options.Identity
			if findAttemptDecision(records, terminalSchema, t.ExecutionAttemptID) != nil {
				continue
			}
			if err = c.cancelAttempt(ctx, t); err != nil {
				return err
			}
		}
	}
	return nil
}
func (c *coordinator) cancelAttempt(ctx context.Context, t Trial) error {
	_, stopErr := ownerCall(ctx, c, "control", c.options.ExecutionBudget, func(work context.Context) (struct{}, error) {
		return struct{}{}, c.options.Host.Cancel(work, copyTrial(t))
	})
	if stopErr != nil {
		category, known := fault.CategoryOf(stopErr)
		if !known || category != fault.Conflict && category != fault.InvalidInput {
			return stopErr
		}
	}
	return nil
}
func (c *coordinator) Results(ctx context.Context, id Identity) ([]Observation, error) {
	if err := c.authorize(ctx, id); err != nil {
		return nil, err
	}
	release, err := c.acquire(ctx)
	if err != nil {
		return nil, err
	}
	defer release()
	records, err := c.load(ctx)
	if err != nil {
		return nil, err
	}
	if err = c.restoreChildren(ctx, records); err != nil {
		return nil, err
	}
	result := []Observation{}
	for _, slot := range c.slotSnapshot() {
		observed, readErr := c.slotResults(ctx, slot, records)
		if readErr != nil {
			return nil, readErr
		}
		result = append(result, observed...)
	}
	return result, nil
}
func observationFromMap(m map[string]any) (Observation, error) {
	o := Observation{Kind: text(m, "kind"), State: text(m, "state"), Ceased: truth(m["ceased"]), EffectsAbsent: truth(m["effects_absent"]), Complete: truth(m["complete"]), Reusable: truth(m["ready"]), IdempotentEffects: truth(m["idempotent_effects"])}
	for key, target := range map[string]any{"configurations": &o.Configurations, termEvidence: &o.Evidence, "receipt": &o.CleanupReceipt, "verified_compensations": &o.VerifiedCompensations} {
		if value, exists := m[key]; exists {
			raw, err := json.Marshal(value)
			if err != nil || json.Unmarshal(raw, target) != nil {
				return Observation{}, integrity()
			}
		}
	}
	return o, nil
}

func validateRetainedAttempts(id string, s trialSlot, attempts []map[string]any) error {
	for index, a := range attempts {
		ordinal := integer(a["attempt"])
		if ordinal != index+1 || ordinal > integer(at(cleanupPlan(s, s.request(a)), "retry_policy", "max_attempts")) || text(a, termRunID) != s.entry.RunID || text(a, termExecutionAttemptID) != attemptID(id, s.entry.PlanEntryID, ordinal) {
			return integrity()
		}
		started, se := time.Parse(time.RFC3339Nano, text(a, termStartedAt))
		deadline, de := time.Parse(time.RFC3339Nano, text(a, "deadline"))
		seconds := integer(at(s.view, "entries", s.entry.PlanEntryID, "execution_controls", "attempt_timeout_seconds"))
		if se != nil || de != nil || deadline.Unix()-started.Unix() != int64(seconds) || deadline.Nanosecond() != started.Nanosecond() {
			return integrity()
		}
	}
	return nil
}
func detachObservation(o Observation) (Observation, error) {
	var err error
	o.Configurations, err = copyDTO(o.Configurations)
	if err != nil {
		return Observation{}, err
	}
	o.CleanupEvidence, err = copyDTO(o.CleanupEvidence)
	if err != nil {
		return Observation{}, err
	}
	o.Evidence, err = copyDTO(o.Evidence)
	if err != nil {
		return Observation{}, err
	}
	if o.CleanupReceipt != nil {
		receipt, copyErr := copyDTO(*o.CleanupReceipt)
		if copyErr != nil {
			return Observation{}, copyErr
		}
		o.CleanupReceipt = &receipt
	}
	o.VerifiedCompensations = slices.Clone(o.VerifiedCompensations)
	o.ObligationResults = maps.Clone(o.ObligationResults)
	o.Snapshot, err = copyDTO(o.Snapshot)
	if err != nil {
		return Observation{}, err
	}
	o.OperationReceipts, err = copyDTO(o.OperationReceipts)
	return o, err
}

func runtimeTimestamp(instant time.Time) string {
	instant = instant.UTC()
	text := instant.Format("2006-01-02T15:04:05")
	if micros := instant.Nanosecond() / 1000; micros != 0 {
		text += fmt.Sprintf(".%06d", micros)
	}
	return text + "+00:00"
}

func (c *coordinator) restartAttempt(ctx context.Context, s trialSlot, t Trial) (Progress, bool, error) {
	attempt, err := c.startAttempt(ctx, s, t.Attempt+1)
	if err != nil {
		return Progress{}, true, err
	}
	return c.progress(termProgress, s.request(decisionMap(attempt))), true, nil
}
