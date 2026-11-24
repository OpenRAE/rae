package experiment

import (
	"context"
	"slices"
	"testing"
)

type pendingConfigurationHost struct {
	*testHost

	pending        bool
	configurations int
}

func (h *pendingConfigurationHost) Configure(_ context.Context, t Trial) (Phase, error) {
	h.configurations++
	state := termSucceeded
	if h.pending {
		state = termPending
	}
	return Phase{State: state, Observation: &Observation{Kind: termConfiguration, Configurations: t.Realization.ParticipantConfigurations}}, nil
}
func TestRuntimeDoesNotAdvanceAnUnsettledConfiguration(t *testing.T) {
	h := &pendingConfigurationHost{testHost: &testHost{}, pending: true}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	for range 2 {
		progress, err := c.Advance(t.Context(), c.options.Identity)
		if err != nil {
			t.Fatal(err)
		}
		if progress.State != termPending {
			t.Fatal("phase acknowledgement was mistaken for completion", progress.State)
		}
	}
	for _, event := range h.events {
		if event == "advance" || event == termCapture || event == termCleanup {
			t.Fatal("phase advanced while pending", event)
		}
	}
	if h.configurations != 2 {
		t.Fatal("phase owner was not asked to reconcile")
	}
	h.pending = false
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	attempts := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)
	if len(attempts) != 1 {
		t.Fatal("pending phase created another attempt")
	}
}

type pendingTeardownHost struct {
	terminalHost

	captureState string
	cleanupState string
	stops        string
}

func (h *pendingTeardownHost) Capture(context.Context, Trial) (Phase, error) {
	h.events = append(h.events, termCapture)
	return Phase{State: h.captureState, Observation: &Observation{Kind: termCapture, Complete: true}}, nil
}
func (h *pendingTeardownHost) Cleanup(ctx context.Context, t Trial, reason string) (Phase, error) {
	phase, err := h.terminalHost.Cleanup(ctx, t, reason)
	phase.State = h.cleanupState
	return phase, err
}
func (h *pendingTeardownHost) Stop(context.Context, Trial, string) (Phase, error) {
	h.events = append(h.events, "stop")
	return Phase{State: h.stops}, nil
}
func TestRuntimeReconcilesPendingTeardownBeforeReleasingAttempt(t *testing.T) {
	for _, state := range []string{termProgress, termPending, termIndeterminate} {
		t.Run(state, func(t *testing.T) { checkPendingTeardown(t, state) })
	}
}
func TestRuntimeDoesNotObserveCessationBeforeStopSettles(t *testing.T) {
	h := &pendingTeardownHost{testHost: &testHost{}, evidence: fixtureEvidence(t), stops: termIndeterminate}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	if err := c.Cancel(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	h.events = nil
	p, err := c.Advance(t.Context(), c.options.Identity)
	if err != nil || p.State != termIndeterminate {
		t.Fatal(p, err)
	}
	if slices.Contains(h.events, "observe") {
		t.Fatal("stop was not reconciled")
	}
	h.stops = termSucceeded
	p, err = c.Advance(t.Context(), c.options.Identity)
	if err != nil || p.State != termIndeterminate || !slices.Contains(h.events, "observe") {
		t.Fatal("stop acknowledgement inferred physical cessation", p, err)
	}
}

func checkPendingTeardown(t *testing.T, state string) {
	t.Helper()

	h := &pendingTeardownHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t), captureState: state, cleanupState: state}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	for range 2 {
		c = runtimeCoordinator(t, newRuntime(t, h, j))
		p, err := c.Advance(t.Context(), c.options.Identity)
		if err != nil || p.State != state {
			t.Fatal("capture advanced", p, err)
		}
	}
	if slices.Contains(h.events, termCleanup) {
		t.Fatal("cleanup preceded settled capture")
	}
	h.captureState = termSucceeded
	for range 2 {
		c = runtimeCoordinator(t, newRuntime(t, h, j))
		p, err := c.Advance(t.Context(), c.options.Identity)
		if err != nil || p.State != state {
			t.Fatal("cleanup advanced", p, err)
		}
	}
	attempts := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)
	if len(attempts) != 1 || findAttemptDecision(j.records, terminalSchema, text(attempts[0], termExecutionAttemptID)) != nil {
		t.Fatal("unsettled cleanup released attempt")
	}
	h.cleanupState = termSucceeded
	if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
		t.Fatal(err)
	}
	if findAttemptDecision(j.records, terminalSchema, text(attempts[0], termExecutionAttemptID)) == nil {
		t.Fatal("settled cleanup not retained")
	}
}

func TestRuntimeCaptureObservationCannotOverrideFailedPhase(t *testing.T) {
	h := &pendingTeardownHost{testHost: &testHost{ceased: true}, evidence: fixtureEvidence(t), captureState: termFailed, cleanupState: termSucceeded}
	j := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, h, j))
	for range 2 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			t.Fatal(err)
		}
	}
	attempt := slotAttempts(j.records, c.id, c.slots[0].entry.PlanEntryID)[0]
	terminal := findAttemptDecision(j.records, terminalSchema, text(attempt, termExecutionAttemptID))
	if text(terminal, termCaptureStatus) != termFailed {
		t.Fatal("complete observation promoted failed capture", terminal)
	}
}
