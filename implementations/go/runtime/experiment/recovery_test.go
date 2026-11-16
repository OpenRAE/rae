package experiment

import (
	"context"
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/OpenRAE/rae/implementations/go/contract/admission"
	"github.com/OpenRAE/rae/implementations/go/contract/binding"
)

type retryHost struct {
	terminalHost

	pending       bool
	idempotent    bool
	effectsAbsent bool
	preparations  int
}

func (h *retryHost) Observe(_ context.Context, trial Trial) (Observation, error) {
	record, err := trialEvidence(h.evidence, trial.RunID, "evidence:execution")
	if err != nil {
		return Observation{}, err
	}
	return Observation{Kind: termExecution, State: termFailed, Ceased: true, EffectsAbsent: h.effectsAbsent, Evidence: []binding.ExperimentEvidenceRecordV1{record}}, nil
}
func (h *retryHost) Cleanup(ctx context.Context, trial Trial, reason string) (Phase, error) {
	phase, err := h.terminalHost.Cleanup(ctx, trial, reason)
	if phase.Observation != nil {
		phase.Observation.IdempotentEffects = h.idempotent
	}
	return phase, err
}
func (h *retryHost) PrepareRetry(ctx context.Context, trial Trial) (Phase, error) {
	h.preparations++
	cleanup, err := h.terminalHost.Cleanup(ctx, trial, termFailed)
	if err != nil {
		return Phase{}, err
	}
	owner, err := experimentOwner()
	if err != nil {
		return Phase{}, err
	}
	result, err := admission.AdmitFragment(owner, admission.CleanupObligationResult, map[string]any{"obligation_id": "reset", "status": termSucceeded, "evidence_refs": []any{"evidence:clean"}, "residual_state_refs": []any{}}, runtimeIngress())
	if err != nil {
		return Phase{}, err
	}
	view, err := transportView(trial.Plan)
	if err != nil {
		return Phase{}, err
	}
	plan := at(view, "cleanup_plans", text(view, "entries", trial.PlanEntryID, "execution_controls", "cleanup_plan_ref"))
	obligations := map[string]admission.Fragment{}
	if at(plan, "cleanup_obligations", "reset") != nil {
		obligations["reset"] = result
	}
	observation := &Observation{Kind: termRetry, Reusable: true, Evidence: cleanup.Observation.Evidence, ObligationResults: obligations, VerifiedCompensations: []string{"restore-state"}}
	state := termSucceeded
	if h.pending {
		state = termPending
	}
	return Phase{State: state, Observation: observation}, nil
}
func retryReferences(t *testing.T) []runtimeReferenceCompilation {
	t.Helper()
	raw, err := os.ReadFile("testdata/retry-reference.json")
	if err != nil {
		t.Fatal(err)
	}
	var ref struct {
		Cases []runtimeReferenceCompilation `json:"cases"`
	}
	if json.Unmarshal(raw, &ref) != nil {
		t.Fatal("fixture")
	}
	return ref.Cases
}
func TestRuntimeRetryRequiresSettledPreparationAfterRecovery(t *testing.T) {
	for _, ref := range retryReferences(t) {
		if ref.Name != "reset" && ref.Name != "compensate" {
			continue
		}
		t.Run(ref.Name, func(t *testing.T) { checkRetryPreparation(t, ref) })
	}
}
func checkRetryPreparation(t *testing.T, ref runtimeReferenceCompilation) {
	t.Helper()
	h := &retryHost{testHost: &testHost{}, evidence: fixtureEvidence(t), pending: true}
	j := &testJournal{}
	input := runtimeInputFixture(t, ref)
	c := runtimeCoordinator(t, newRuntimeWithInputs(t, h, j, input))
	for range 2 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	for range 2 {
		c = runtimeCoordinator(t, newRuntimeWithInputs(t, h, j, input))
		p, err := c.Advance(t.Context(), c.options.Identity)
		if err != nil || p.State != termPending {
			t.Fatal("unsettled retry advanced", p, err)
		}
		if len(slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)) != 1 {
			t.Fatal("ready observation bypassed phase completion")
		}
	}
	h.pending = false
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	if h.preparations != 3 || len(slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)) != 2 {
		t.Fatal("settled retry was not reconciled")
	}
}
func TestRuntimeRetryHonorsAuthorPolicyAndAttemptLimit(t *testing.T) {
	for _, ref := range retryReferences(t) {
		t.Run(ref.Name, func(t *testing.T) { checkRetryLimit(t, ref) })
	}
}
func checkRetryLimit(t *testing.T, ref runtimeReferenceCompilation) {
	t.Helper()
	h := &retryHost{testHost: &testHost{}, evidence: fixtureEvidence(t), idempotent: true}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntimeWithInputs(t, h, j, runtimeInputFixture(t, ref)))
	for range 20 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	want := 2
	if ref.Name == "disallow" {
		want = 1
	}
	for _, slot := range c.slots {
		if got := len(slotAttempts(j.records, c.id, slot.entry.PlanEntryID)); got != want {
			t.Fatal("author retry policy or attempt limit changed", got, want)
		}
	}
}
func TestRuntimeRecoveryKeepsDeadlineAndDetectsClockRollback(t *testing.T) {
	for _, rollback := range []bool{false, true} {
		t.Run(map[bool]string{false: "expired", true: "rollback"}[rollback], func(t *testing.T) { checkRetainedDeadline(t, rollback) })
	}
}
func checkRetainedDeadline(t *testing.T, rollback bool) {
	t.Helper()
	h := &testHost{}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	attempt := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)[0]
	c = runtimeCoordinator(t, newRuntime(t, h, j))
	field := "deadline"
	if rollback {
		field = termStartedAt
	}
	now, err := time.Parse(time.RFC3339Nano, text(attempt, field))
	if err != nil {
		t.Fatal(err)
	}
	if rollback {
		now = now.Add(-time.Second)
	}
	c.options.Clock = func() time.Time { return now }
	h.events = nil
	p, err := c.Advance(t.Context(), c.options.Identity)
	if rollback {
		if err == nil {
			t.Fatal("clock rollback admitted")
		}
		return
	}
	if err != nil || p.State != termIndeterminate {
		t.Fatal("deadline renewed after recovery", p, err)
	}
	if findAttemptDecision(j.records, interruptionSchema, text(attempt, termExecutionAttemptID)) == nil {
		t.Fatal("expiry not retained before stop")
	}
}

func TestRuntimeRequiresEvidenceBeforeRetainingCessation(t *testing.T) {
	h := &testHost{ceased: true}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	if _, err := c.Advance(t.Context(), c.options.Identity); err == nil {
		t.Fatal("cessation accepted without observed evidence")
	}
	attempt := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)[0]
	if attemptObservations(j.records, text(attempt, termExecutionAttemptID))[termExecution] != nil {
		t.Fatal("unproved cessation persisted")
	}
}

type blockedConfigurationHost struct {
	*testHost

	entered chan struct{}
	release chan struct{}
	stopped chan struct{}
}

func (h *blockedConfigurationHost) Configure(ctx context.Context, trial Trial) (Phase, error) {
	close(h.entered)
	<-h.release
	return h.testHost.Configure(ctx, trial)
}
func (h *blockedConfigurationHost) Cancel(context.Context, Trial) error {
	close(h.stopped)
	return nil
}
func TestRuntimeCancellationRemainsAvailableDuringBlockedProgress(t *testing.T) {
	h := &blockedConfigurationHost{testHost: &testHost{}, entered: make(chan struct{}), release: make(chan struct{}), stopped: make(chan struct{})}
	c := runtimeCoordinator(t, newRuntime(t, h, &testJournal{}))
	advance := make(chan error, 1)
	go func() { _, err := c.Advance(t.Context(), c.options.Identity); advance <- err }()
	<-h.entered
	cancel := make(chan error, 1)
	go func() { cancel <- c.Cancel(t.Context(), c.options.Identity) }()
	stopped := false
	select {
	case <-h.stopped:
		stopped = true
	case <-time.After(500 * time.Millisecond):
	}
	close(h.release)
	if err := <-advance; err != nil {
		t.Fatal(err)
	}
	if err := <-cancel; err != nil {
		t.Fatal(err)
	}
	if !stopped {
		t.Fatal("blocked progress also blocked independent cancellation")
	}
}
