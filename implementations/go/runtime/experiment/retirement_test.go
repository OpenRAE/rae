package experiment

import (
	"context"
	"errors"
	"slices"
	"testing"
)

type retirementHost struct {
	terminalHost

	retired             map[string]bool
	lostAcknowledgement bool
	retireCalls         int
	beforeRetire        func(Trial) error
}

func (h *retirementHost) IsRetired(_ context.Context, trial Trial) (bool, error) {
	return h.retired[trial.RunID], nil
}
func (h *retirementHost) Retire(_ context.Context, trial Trial) error {
	if h.beforeRetire != nil {
		if err := h.beforeRetire(trial); err != nil {
			return err
		}
	}
	h.retireCalls++
	h.retired[trial.RunID] = true
	if h.lostAcknowledgement {
		h.lostAcknowledgement = false
		return errors.New("lost retirement acknowledgement")
	}
	return nil
}
func TestRuntimeSkipsSharedRetiredRunsWithoutStartingAttempts(t *testing.T) {
	h := &retirementHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t), retired: map[string]bool{}}
	j := &testJournal{}
	runtime := newRuntime(t, h, j)
	for _, slot := range runtimeCoordinator(t, runtime).slotSnapshot() {
		h.retired[slot.entry.RunID] = true
	}
	progress, err := runtime.Advance(context.Background(), Identity{ActorID: "actor", AuthorizationScope: []string{termRun}})
	if err != nil || progress.State != termCompleted {
		t.Fatalf("retired runs: %+v %v", progress, err)
	}
	for _, record := range j.records {
		if record.SchemaVersion() == attemptSchema {
			t.Fatal("retired run started")
		}
	}
	if slices.Contains(h.events, "configure") {
		t.Fatal("retired run reconfigured")
	}
}
func TestRuntimeRecoversLostRetirementAcknowledgement(t *testing.T) {
	h := &retirementHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t), retired: map[string]bool{}, lostAcknowledgement: true}
	j := &testJournal{}
	runtime := newRuntime(t, h, j)
	identity := Identity{ActorID: "actor", AuthorizationScope: []string{termRun}}
	for range 8 {
		_, err := runtime.Advance(context.Background(), identity)
		if err != nil {
			break
		}
	}
	if h.retireCalls != 1 {
		t.Fatalf("retirement calls=%d", h.retireCalls)
	}
	runtime = newRuntime(t, h, j)
	// Re-admission during coordinator construction is an existing shared-owner reconciliation.
	progress, err := runtime.Advance(context.Background(), identity)
	if err != nil {
		t.Fatal(err)
	}
	if progress.State != termProgress && progress.State != termCompleted {
		t.Fatalf("recovery: %+v", progress)
	}
	if h.retireCalls != 1 {
		t.Fatal("retirement repeated after durable acknowledgement loss")
	}
	// The other plan slot may start; the first slot must remain retired.
	if len(h.retired) != 1 {
		t.Fatal("unexpected retirement")
	}
}
