package experiment

import (
	"context"
	"errors"
	"maps"
	"strings"
	"testing"

	"github.com/OpenRAE/rae/implementations/go/base/fault"
)

type phaseBoundaryHost struct {
	Host

	failed string
}

func (h phaseBoundaryHost) Authorize(ctx context.Context, id Identity, experiment string) error {
	if h.failed == "authorize" {
		return errors.New("private phase failure")
	}
	return h.Host.Authorize(ctx, id, experiment)
}
func (h phaseBoundaryHost) Admit(ctx context.Context, trial Trial) (string, error) {
	if h.failed == "admit" {
		return "", errors.New("private phase failure")
	}
	return h.Host.Admit(ctx, trial)
}
func (h phaseBoundaryHost) Configure(ctx context.Context, trial Trial) (Phase, error) {
	if h.failed == "configure" {
		return Phase{}, errors.New("private phase failure")
	}
	return h.Host.Configure(ctx, trial)
}
func (h phaseBoundaryHost) Observe(ctx context.Context, trial Trial) (Observation, error) {
	if h.failed == "observe" {
		return Observation{}, errors.New("private phase failure")
	}
	return h.Host.Observe(ctx, trial)
}
func (h phaseBoundaryHost) Capture(ctx context.Context, trial Trial) (Phase, error) {
	if h.failed == "capture" {
		return Phase{}, errors.New("private phase failure")
	}
	return h.Host.Capture(ctx, trial)
}
func (h phaseBoundaryHost) Cleanup(ctx context.Context, trial Trial, reason string) (Phase, error) {
	if h.failed == "cleanup" {
		return Phase{}, errors.New("private phase failure")
	}
	return h.Host.Cleanup(ctx, trial, reason)
}
func (h phaseBoundaryHost) Verify(ctx context.Context, trial Trial, o Observation) error {
	if h.failed == "verify" {
		return errors.New("private phase failure")
	}
	return h.Host.Verify(ctx, trial, o)
}
func (h phaseBoundaryHost) Retire(ctx context.Context, trial Trial) error {
	if h.failed == "retire" {
		return errors.New("private phase failure")
	}
	return h.Host.Retire(ctx, trial)
}
func (h phaseBoundaryHost) Records(ctx context.Context, trial Trial) (RecordSource, error) {
	if h.failed == "records" {
		return RecordSource{}, errors.New("private phase failure")
	}
	return h.Host.Records(ctx, trial)
}
func (h phaseBoundaryHost) Cancel(ctx context.Context, trial Trial) error {
	if h.failed == "cancel" {
		return errors.New("private phase failure")
	}
	return h.Host.Cancel(ctx, trial)
}
func (h phaseBoundaryHost) Stop(ctx context.Context, trial Trial, reason string) (Phase, error) {
	if h.failed == "stop" {
		return Phase{}, errors.New("private phase failure")
	}
	return h.Host.Stop(ctx, trial, reason)
}

func TestRuntimeOwnerFailuresCannotCompleteUnconfirmedPhases(t *testing.T) {
	journal := &testJournal{}
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, journal))
	initial := append([]Decision{}, journal.records...)
	for _, stage := range []string{"configure", "observe", "verify", "capture", "cleanup", "retire", "records", "cancel", "stop"} {
		t.Run(stage, func(t *testing.T) {
			checkRuntimeOwnerFailureBoundary(t, c, initial, stage)
		})
	}
	for _, stage := range []string{"authorize", "admit"} {
		c.options.Host = phaseBoundaryHost{Host: &testHost{}, failed: stage}
		if _, err := New(t.Context(), c.options); err == nil || strings.Contains(err.Error(), "private") {
			t.Fatal("construction bypassed owner failure", stage, err)
		}
	}
}

func TestRuntimePhaseObservationsRemainImmutableAcrossReplay(t *testing.T) {
	c := runtimeCoordinator(t, newRuntime(t, &testHost{}, &testJournal{}))
	slot := c.slotSnapshot()[0]
	start, err := c.startAttempt(t.Context(), slot, 1)
	if err != nil {
		t.Fatal(err)
	}
	trial := slot.request(decisionMap(start))
	initial := Observation{Kind: termCapture, Complete: true}
	payload, snapshot, err := observationPayload(initial)
	if err != nil {
		t.Fatal(err)
	}
	known := map[string]map[string]any{termCapture: {"observation": payload, "snapshot_json": snapshot}}
	if err := c.phaseObservation(t.Context(), slot, trial, termCapture, initial, known); err != nil {
		t.Fatal("exact phase replay refused", err)
	}
	if err := c.retainVerifiedObservation(t.Context(), trial, verifiedObservation{initial}, known); err != nil {
		t.Fatal("exact retained fact refused", err)
	}
	changed := initial
	changed.Complete = false
	if err := c.phaseObservation(t.Context(), slot, trial, termCapture, changed, known); err == nil {
		t.Fatal("changed phase fact replayed")
	}
	if err := c.retainVerifiedObservation(t.Context(), trial, verifiedObservation{changed}, known); err == nil {
		t.Fatal("changed retained fact replayed")
	}
	for _, test := range []struct {
		name, kind string
		phase      Phase
	}{
		{"unknown-state", termCapture, Phase{State: "foreign"}},
		{"missing-proof", termCapture, Phase{State: termSucceeded}},
		{"wrong-kind", termCapture, Phase{State: termPending, Observation: &Observation{Kind: termExecution}}},
		{"unscoped-proof", "", Phase{State: termPending, Observation: &initial}},
	} {
		t.Run(test.name, func(t *testing.T) {
			if _, err := c.phase(t.Context(), slot, trial, test.kind, map[string]map[string]any{}, func(context.Context) (Phase, error) { return test.phase, nil }); err == nil {
				t.Fatal("unconfirmed phase admitted")
			}
		})
	}
	if _, err := c.validateObservation(t.Context(), slot, trial, termCapture, Observation{Kind: termExecution}); err == nil {
		t.Fatal("observation changed requested phase")
	}
	if _, err := c.validateObservation(t.Context(), slot, trial, termExecution, Observation{Kind: termExecution, State: "foreign"}); err == nil {
		t.Fatal("unknown execution state admitted")
	}
	if _, _, err := observationPayload(Observation{Kind: "foreign"}); err == nil {
		t.Fatal("unknown observation kind admitted")
	}
	bad := maps.Clone(payload)
	bad["evidence"] = []any{map[string]any{"run_ref": map[string]any{"ref_kind": termRun, "ref_id": "foreign"}}}
	if err := c.validateObservedFacts(slot, trial, termCapture, initial, bad); err == nil {
		t.Fatal("cross-run proof admitted")
	}
}

func checkRuntimeOwnerFailureBoundary(t *testing.T, c *coordinator, initial []Decision, stage string) {
	t.Helper()

	for _, deadline := range c.deadlines {
		deadline.timer.Stop()
	}
	c.deadlines = map[string]*attemptDeadline{}
	journal := &testJournal{records: append([]Decision{}, initial...)}
	c.options.Journal = journal
	host := phaseBoundaryHost{Host: terminalHost{testHost: &testHost{ceased: stage != "stop"}, evidence: fixtureEvidence(t)}, failed: stage}
	c.options.Host = host
	failure := advanceBoundaryUntilFailure(t, c, stage)
	category, known := fault.CategoryOf(failure)
	if !known || category != fault.Operational || strings.Contains(failure.Error(), "private") {
		t.Fatal("owner failure was lost or disclosed", failure)
	}
	if stage == "configure" || stage == "observe" || stage == "verify" || stage == "capture" || stage == "cleanup" {
		for _, record := range journal.records {
			if record.SchemaVersion() == terminalSchema {
				t.Fatal("owner failure became a completed trial")
			}
		}
	}
}

func advanceBoundaryUntilFailure(t *testing.T, c *coordinator, stage string) error {
	t.Helper()
	for range 6 {
		if _, err := c.Advance(t.Context(), c.options.Identity); err != nil {
			return err
		}
		switch stage {
		case "records":
			_, err := c.Records(t.Context(), c.options.Identity, RecordOptions{})
			return err
		case "cancel":
			return c.Cancel(t.Context(), c.options.Identity)
		case "stop":
			if err := c.Cancel(t.Context(), c.options.Identity); err != nil {
				t.Fatal(err)
			}
		}
	}
	return nil
}
